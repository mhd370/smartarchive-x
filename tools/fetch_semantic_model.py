r"""Download the dense retrieval model (multilingual-e5-small, ONNX) for semantic search.

  .\.venv\Scripts\python.exe -m pip install -r requirements-semantic.txt
  .\.venv\Scripts\python.exe tools/fetch_semantic_model.py [--revision COMMIT]

Files go to models/semantic/multilingual-e5-small, from the Xenova ONNX export of intfloat/multilingual-e5-small
(MIT licence). The resolved commit and each file's SHA-256 are written to SOURCE.json. A second run with
--revision checks the files against that commit. Without the model, ranked search runs without the dense
ranking (ADR 0013).
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
REPO = 'Xenova/multilingual-e5-small'
FILES = ('config.json', 'tokenizer.json', 'tokenizer_config.json', 'onnx/model_quantized.onnx')


def fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={'User-Agent': 'smartarchive-x-model-fetch'})
    with urllib.request.urlopen(request, timeout=120) as response:
        return response.read()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--revision', help='commit to download (default: the current main, recorded)')
    parser.add_argument('--out', type=Path, default=ROOT / 'models' / 'semantic' / 'multilingual-e5-small')
    args = parser.parse_args(argv)
    revision = args.revision or json.loads(fetch(f'https://huggingface.co/api/models/{REPO}/revision/main'))['sha']
    out = args.out.resolve()
    record = {'repository': REPO, 'revision': revision, 'licence': 'MIT (intfloat/multilingual-e5-small)', 'files': {}}
    for name in FILES:
        data = fetch(f'https://huggingface.co/{REPO}/resolve/{revision}/{name}')
        target = out / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        record['files'][name] = {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
        print(f'{name}: {len(data):,} bytes', flush=True)
    (out / 'SOURCE.json').write_text(json.dumps(record, indent=1), encoding='utf-8')
    print(f'revision {revision} -> {out}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
