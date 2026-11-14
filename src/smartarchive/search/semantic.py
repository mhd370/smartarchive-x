"""Dense (semantic) page retrieval (`dense-e5-small-v1`), an optional fourth ranking for ranked search.

A page is split into overlapping windows of about 120 words. Each window is embedded with multilingual-e5-small,
run with ONNX Runtime on the CPU with no PyTorch, and stored as float16 per page in `page_vectors`. A query is
embedded the same way. A page scores as its best window by cosine similarity, and the pages above
MIN_SIMILARITY join the reciprocal rank fusion in ranked.py. This finds pages that say the same thing in other
words, for example «اتفاقية توريد» for «عقد شراء», which the word and trigram indexes cannot.

The model is optional. tools/fetch_semantic_model.py downloads it, hash-checked, into
models/semantic/multilingual-e5-small, and SMARTARCHIVE_SEMANTIC_MODEL points elsewhere. Without it, or
without onnxruntime and tokenizers, ranked search runs as before (`hybrid-rrf-v1`).
Vectors are derived data. They are rebuilt whenever a page's text changes (OCR or review) and never replace it.
"""
from __future__ import annotations

import hashlib
import logging
from pathlib import Path
import threading

import numpy as np

from .arabic import normalize

log = logging.getLogger(__name__)
METHOD = 'dense-e5-small-v1'
WINDOW, STRIDE, MAX_TOKENS = 120, 90, 256
CANDIDATES = 50
MIN_SIMILARITY = 0.84  # e5 cosine similarities sit high (0.85–0.91); chosen on the development set (ADR 0013)


def windows(text: str) -> list[str]:
    words = text.split()
    if not words:
        return []
    out = [' '.join(words[i:i + WINDOW]) for i in range(0, max(1, len(words) - WINDOW + STRIDE), STRIDE)]
    return [w for w in out if w]


def text_hash(text: str) -> str:
    return hashlib.sha1(text.encode('utf-8')).hexdigest()


class Encoder:
    """multilingual-e5-small with mean pooling and L2 normalization; e5 expects "query:"/"passage:" prefixes."""
    name = METHOD

    def __init__(self, folder: Path):
        import onnxruntime
        from tokenizers import Tokenizer
        model = next((p for p in (folder / 'onnx' / 'model_quantized.onnx', folder / 'onnx' / 'model.onnx',
                                  folder / 'model.onnx') if p.is_file()), None)
        if model is None:
            raise FileNotFoundError(f'no ONNX model in {folder}')
        self.tokenizer = Tokenizer.from_file(str(folder / 'tokenizer.json'))
        self.tokenizer.enable_truncation(MAX_TOKENS)
        self.tokenizer.enable_padding()
        options = onnxruntime.SessionOptions()
        options.intra_op_num_threads = 2
        self.session = onnxruntime.InferenceSession(str(model), options, providers=['CPUExecutionProvider'])
        self.inputs = {i.name for i in self.session.get_inputs()}
        self._lock = threading.Lock()

    def encode(self, texts: list[str], kind: str = 'passage', batch: int = 16) -> np.ndarray:
        out = []
        for start in range(0, len(texts), batch):
            encoded = self.tokenizer.encode_batch([f'{kind}: {t}' for t in texts[start:start + batch]])
            ids = np.array([e.ids for e in encoded], dtype=np.int64)
            mask = np.array([e.attention_mask for e in encoded], dtype=np.int64)
            feed = {'input_ids': ids, 'attention_mask': mask}
            if 'token_type_ids' in self.inputs:
                feed['token_type_ids'] = np.zeros_like(ids)
            with self._lock:
                hidden = self.session.run(None, feed)[0]
            summed = (hidden * mask[..., None]).sum(axis=1) / np.maximum(mask.sum(axis=1, keepdims=True), 1)
            out.append(summed / np.maximum(np.linalg.norm(summed, axis=1, keepdims=True), 1e-9))
        return np.vstack(out).astype(np.float32) if out else np.zeros((0, 0), np.float32)


def load(folder: Path | None):
    """The encoder, or None (logged once) when the model or its runtime is missing."""
    if not folder or not (folder / 'tokenizer.json').is_file():
        return None
    try:
        return Encoder(folder)
    except Exception as exc:  # optional feature: never stop the archive over it
        log.warning('semantic search disabled: %s', exc)
        return None


class SemanticIndex:
    def __init__(self, encoder):
        self.encoder = encoder
        self._lock = threading.Lock()

    def refresh(self, db) -> int:
        """Embed pages whose text changed since their vectors were made. Returns pages embedded."""
        with self._lock:
            rows = db.execute(
                'SELECT t.document_id, t.page_no, t.text, v.text_hash FROM page_texts t LEFT JOIN page_vectors v'
                ' ON v.document_id=t.document_id AND v.page_no=t.page_no').fetchall()
            done = 0
            for row in rows:
                digest = text_hash(row['text'])
                if row['text_hash'] == digest:
                    continue
                parts = windows(normalize(row['text']))
                vectors = self.encoder.encode(parts) if parts else np.zeros((0, 1), np.float32)
                db.execute('INSERT OR REPLACE INTO page_vectors VALUES (?,?,?,?,?,?)',
                           (row['document_id'], row['page_no'], digest, self.encoder.name,
                            int(vectors.shape[1]) if len(parts) else 0, vectors.astype(np.float16).tobytes()))
                done += 1
            return done

    def search(self, db, query: str) -> list[tuple[str, int]]:
        """Pages ranked by their best window's cosine similarity to the query, above MIN_SIMILARITY."""
        if not normalize(query).strip():
            return []
        q = self.encoder.encode([normalize(query)], 'query')[0]
        scored = []
        for row in db.execute('SELECT document_id, page_no, dim, vectors FROM page_vectors WHERE dim > 0'):
            vectors = np.frombuffer(row['vectors'], dtype=np.float16).reshape(-1, row['dim']).astype(np.float32)
            best = float((vectors @ q).max())
            if best >= getattr(self.encoder, 'min_similarity', MIN_SIMILARITY):
                scored.append((best, row['document_id'], row['page_no']))
        scored.sort(reverse=True)
        return [(d, p) for _, d, p in scored[:CANDIDATES]]


class Indexer:
    """Background thread that embeds changed pages, woken after OCR or a review and every minute otherwise."""
    def __init__(self, db, index: SemanticIndex):
        self.db, self.index = db, index
        self._wake, self._stop = threading.Event(), threading.Event()
        self._thread: threading.Thread | None = None

    def wake(self):
        self._wake.set()

    def start(self):
        if not self._thread:
            self._thread = threading.Thread(target=self._run, name='semantic-indexer', daemon=True)
            self._thread.start()

    def stop(self):
        self._stop.set()
        self._wake.set()

    def _run(self):
        while not self._stop.is_set():
            try:
                with self.db.connect() as db:
                    self.index.refresh(db)
            except Exception:  # never take the archive down; try again on the next wake-up
                log.exception('semantic indexing failed')
            self._wake.wait(60)
            self._wake.clear()
