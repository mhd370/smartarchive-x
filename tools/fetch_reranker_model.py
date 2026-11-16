r"""Download the cross-encoder re-ranker (multilingual MiniLM trained on mMARCO, ONNX) for search re-ranking.

  .\.venv\Scripts\python.exe -m pip install -r requirements-semantic.txt
  .\.venv\Scripts\python.exe tools/fetch_reranker_model.py

Files go to models/reranker/mmarco-mMiniLMv2-L12 (Apache-2.0). The first repository in REPOS that publishes an
ONNX export and a tokenizer.json is used; a CPU-friendly int8 export is preferred over the full-precision one.
The resolved repository, commit and each file's SHA-256 are written to SOURCE.json. Without the model, search runs
without re-ranking (ADR 0014).
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
REPOS = ('cross-encoder/mmarco-mMiniLMv2-L12-H384-v1', 'Xenova/mmarco-mMiniLMv2-L12-H384-v1')
# int8 exports that run on any x86-64 CPU first; avx512 builds can fail on laptop CPUs, so they come last.
PREFERRED = ('onnx/model_quint8_avx2.onnx', 'onnx/model_quantized.onnx', 'onnx/model_int8.onnx', 'onnx/model.onnx',
             'onnx/model_qint8_avx512.onnx')
EXTRA = ('config.json', 'tokenizer.json', 'tokenizer_config.json', 'special_tokens_map.json')


def fetch(url: str, attempts: int = 8) -> bytes:
    """Download in 1 MB chunks; after a timeout or a dropped connection, resume where it stopped (HTTP Range)."""
    data = bytearray()
    for attempt in range(1, attempts + 1):
        headers = {'User-Agent': 'smartarchive-x-model-fetch'}
        if data:
            headers['Range'] = f'bytes={len(data)}-'
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=60) as response:
                if data and response.status != 206:  # the server ignored the range: start again
                    data.clear()
                while chunk := response.read(1 << 20):
                    data += chunk
            return bytes(data)
        except (TimeoutError, OSError) as exc:
            print(f'  attempt {attempt}: {exc}; {len(data):,} bytes so far, resuming', flush=True)
            time.sleep(min(30, 3 * attempt))
    raise SystemExit(f'download failed after {attempts} attempts: {url}')


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--out', type=Path, default=ROOT / 'models' / 'reranker' / 'mmarco-mMiniLMv2-L12')
    args = parser.parse_args(argv)
    for repo in REPOS:
        try:
            info = json.loads(fetch(f'https://huggingface.co/api/models/{repo}'))
        except Exception as exc:
            print(f'{repo}: not reachable ({exc})')
            continue
        names = {s['rfilename'] for s in info.get('siblings', [])}
        model = next((name for name in PREFERRED if name in names), None)
        if not model or 'tokenizer.json' not in names:
            print(f'{repo}: no ONNX export or tokenizer.json, trying the next one')
            continue
        revision = info['sha']
        out = args.out.resolve()
        record = {'repository': repo, 'revision': revision, 'licence': 'Apache-2.0', 'files': {}}
        for name in [n for n in EXTRA if n in names] + [model]:
            data = fetch(f'https://huggingface.co/{repo}/resolve/{revision}/{name}')
            target = out / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            record['files'][name] = {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
            print(f'{name}: {len(data):,} bytes', flush=True)
        (out / 'SOURCE.json').write_text(json.dumps(record, indent=1), encoding='utf-8')
        print(f'{repo} @ {revision} -> {out}')
        return 0
    print('no usable re-ranker found')
    return 1


if __name__ == '__main__':
    sys.exit(main())
