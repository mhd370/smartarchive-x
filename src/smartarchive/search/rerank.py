"""Cross-encoder re-ranking (`ce-mminilm-v1`) of the top ranked-search results.

A cross-encoder reads the query and a passage together and scores how well the passage answers the query. It is
far slower than the indexes, so it only re-orders the first DEPTH documents that hybrid-rrf already found. For
each document the passage is a window of its best page around the first matched words (the evidence the user
sees), otherwise the start of the page.

Model: cross-encoder/mmarco-mMiniLMv2-L12-H384-v1, a multilingual MiniLM trained on mMARCO (MS MARCO machine-
translated into more than ten languages, Arabic among them), run as ONNX on the CPU with no PyTorch.
tools/fetch_reranker_model.py downloads it, hash-checked, into models/reranker/mmarco-mMiniLMv2-L12.

Two ways to use the scores (tools/search_experiments.py measures both, ADR 0014):
- `replace`: the top DEPTH documents are re-ordered by the cross-encoder alone;
- `fuse`: reciprocal rank fusion of the hybrid rank and the cross-encoder rank, so a confident lexical match
  is not thrown away when the model misreads OCR noise.
The feature is optional and off by default (SMARTARCHIVE_RERANK=1 turns it on when the model is present).
"""
from __future__ import annotations

import logging
from pathlib import Path
import threading

import numpy as np

log = logging.getLogger(__name__)
METHOD = 'ce-mminilm-v1'
DEPTH = 20
MAX_TOKENS = 256
PASSAGE_CHARS = 700
RRF_K = 60


def passage(text: str, spans: list[tuple[int, int]], size: int = PASSAGE_CHARS) -> str:
    """A window of the page text around the first matched span (or its start), cut at word boundaries."""
    if not text:
        return ''
    start = max(0, (spans[0][0] if spans else 0) - size // 3)
    end = min(len(text), start + size)
    start = max(0, min(start, end - size))
    if start > 0:
        space = text.find(' ', start)
        start = space + 1 if 0 <= space < start + 40 else start
    return ' '.join(text[start:end].split())


def reorder(keys: list, scores: list[float], mode: str = 'fuse') -> list:
    """The keys (already in hybrid order) re-ordered by cross-encoder `scores`, alone or fused with their rank."""
    if mode not in ('fuse', 'replace'):
        raise ValueError(mode)
    by_model = sorted(range(len(keys)), key=lambda i: -scores[i])
    model_rank = {i: rank for rank, i in enumerate(by_model)}
    if mode == 'replace':
        return [keys[i] for i in by_model]
    fused = {i: 1.0 / (RRF_K + i + 1) + 1.0 / (RRF_K + model_rank[i] + 1) for i in range(len(keys))}
    return [keys[i] for i in sorted(range(len(keys)), key=lambda i: (-fused[i], i))]


class Reranker:
    name = METHOD

    def __init__(self, folder: Path, mode: str = 'fuse'):
        import onnxruntime
        from tokenizers import Tokenizer
        model = next((p for p in sorted((folder / 'onnx').glob('*.onnx')) if 'quint8' in p.name or 'quantized' in p.name),
                     None) or next(iter(sorted((folder / 'onnx').glob('*.onnx'))), None)
        if model is None:
            raise FileNotFoundError(f'no ONNX model in {folder}')
        self.tokenizer = Tokenizer.from_file(str(folder / 'tokenizer.json'))
        self.tokenizer.enable_truncation(MAX_TOKENS)
        self.tokenizer.enable_padding()
        options = onnxruntime.SessionOptions()
        options.intra_op_num_threads = 2
        self.session = onnxruntime.InferenceSession(str(model), options, providers=['CPUExecutionProvider'])
        self.inputs = {i.name for i in self.session.get_inputs()}
        self.mode = mode
        self._lock = threading.Lock()

    def score(self, query: str, passages: list[str], batch: int = 10) -> list[float]:
        out: list[float] = []
        for start in range(0, len(passages), batch):
            encoded = self.tokenizer.encode_batch([(query, p or ' ') for p in passages[start:start + batch]])
            ids = np.array([e.ids for e in encoded], dtype=np.int64)
            mask = np.array([e.attention_mask for e in encoded], dtype=np.int64)
            feed = {'input_ids': ids, 'attention_mask': mask}
            if 'token_type_ids' in self.inputs:
                feed['token_type_ids'] = np.array([e.type_ids for e in encoded], dtype=np.int64)
            with self._lock:
                logits = self.session.run(None, feed)[0]
            out += [float(v) for v in np.asarray(logits).reshape(len(encoded), -1)[:, 0]]
        return out


def load(folder: Path | None, mode: str = 'fuse'):
    """The reranker, or None (logged once) when the model or its runtime is missing."""
    if not folder or not (folder / 'tokenizer.json').is_file():
        return None
    try:
        return Reranker(folder, mode)
    except Exception as exc:  # optional feature: never stop the archive over it
        log.warning('re-ranking disabled: %s', exc)
        return None
