r"""Download pinned Tesseract models into models/tessdata and verify their SHA-256.

  .\.venv\Scripts\python.exe tools/fetch_ocr_models.py

Why: Tesseract's `ara` model knows only two of the ten Arabic-Indic digits (٠ and ١), so reference numbers,
dates and amounts written as ٢٠٢٤ cannot be read. The `script/Arabic` model has all of them. The files come
from tesseract-ocr/tessdata_fast (Apache-2.0) at a fixed commit; a file whose hash differs is rejected.
Then set SMARTARCHIVE_TESSDATA_DIR to the printed folder and choose the languages with
SMARTARCHIVE_OCR_LANGUAGES (for example `script/Arabic+ara`). Existing files with the right hash are kept.
"""
import hashlib
from pathlib import Path
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
COMMIT = '87416418657359cb625c412a48b6e1d6d41c29bd'
BASE = f'https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/{COMMIT}/'
MODELS = {
    'ara.traineddata': 'e3206d3dc87fd50c24a0fb9f01838615911d25168f4e64415244b67d2bb3e729',
    'eng.traineddata': '7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2',
    'script/Arabic.traineddata': '47c262ac4e843c024df87ffa1363b77a821a843c069c71ef7650f4d2ecfea1e8',
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def fetch(target: Path = ROOT / 'models' / 'tessdata') -> Path:
    for name, expected in MODELS.items():
        path = target / name
        if path.is_file() and sha256(path) == expected:
            print(f'ok      {name}')
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        partial = path.with_suffix('.part')
        with urllib.request.urlopen(BASE + name, timeout=120) as response, partial.open('wb') as out:
            while block := response.read(1 << 20):
                out.write(block)
        actual = sha256(partial)
        if actual != expected:
            partial.unlink()
            raise SystemExit(f'{name}: SHA-256 {actual} does not match the pinned {expected}; nothing installed')
        partial.replace(path)
        print(f'fetched {name}')
    (target / 'SOURCE.txt').write_text(f'tesseract-ocr/tessdata_fast @ {COMMIT} (Apache-2.0)\n'
                                       + ''.join(f'{h}  {n}\n' for n, h in MODELS.items()), encoding='utf-8')
    return target


if __name__ == '__main__':
    folder = fetch()
    print(f'\nSMARTARCHIVE_TESSDATA_DIR={folder}')
    sys.exit(0)
