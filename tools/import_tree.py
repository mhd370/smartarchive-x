r"""Import a folder tree of PDFs/images into the archive, keeping the folder structure as archive folders.

  .\.venv\Scripts\python.exe tools/import_tree.py D:\scans --into "وارد 2026" [--no-ocr] [--dry-run]

Every file goes through the same validation as a web upload (type, size, pages; unchanged original with
SHA-256). Sub-folders become archive folders under --into. Unsupported or invalid files are skipped and
listed in the report; nothing in the source folder is modified. Exact duplicates are still stored (they
may be filed twice on purpose) and linked as duplicates. With OCR available, documents are queued and the
running API's worker processes them. A JSON report is written to results/imports/.

Run it while the API is stopped or running; SQLite handles both. Uses SMARTARCHIVE_STORAGE_DIR.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from smartarchive.config import Settings  # noqa: E402
from smartarchive.domain.documents import ArchiveError  # noqa: E402
from smartarchive.enrichment.duplicates import Relations  # noqa: E402
from smartarchive.persistence.database import Database  # noqa: E402
from smartarchive.persistence.storage import EXTENSIONS, OriginalStore  # noqa: E402
from smartarchive.processing.pipeline import OcrService  # noqa: E402
from smartarchive.search.pages import PageTexts  # noqa: E402
from smartarchive.services.documents import Documents  # noqa: E402
from smartarchive.services.folders import Folders  # noqa: E402

MIME = {'.pdf': 'application/pdf', '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
        '.webp': 'image/webp', '.tif': 'image/tiff', '.tiff': 'image/tiff'}


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8', errors='replace')
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('source', type=Path)
    parser.add_argument('--into', default='', help='archive folder path to import under (created if missing)')
    parser.add_argument('--no-ocr', action='store_true', help='store only; do not queue OCR')
    parser.add_argument('--dry-run', action='store_true', help='list what would be imported')
    parser.add_argument('--actor', default='import:' + (os.getenv('USERNAME') or os.getenv('USER') or 'local'))
    args = parser.parse_args(argv)
    source = args.source.resolve()
    if not source.is_dir():
        parser.error(f'not a folder: {source}')
    files = sorted(path for path in source.rglob('*') if path.is_file())
    candidates = [path for path in files if path.suffix.lower() in EXTENSIONS]
    if args.dry_run:
        for path in candidates:
            print(path.relative_to(source))
        print(f'{len(candidates)} supported files, {len(files) - len(candidates)} other files would be skipped')
        return 0

    settings = Settings.from_env()
    db = Database(settings.storage_dir / 'archive.sqlite3')
    store = OriginalStore(settings)
    store.initialize()
    db.initialize()
    documents, folders = Documents(db, store), Folders(db)
    relations = Relations(db)
    ocr = OcrService(db, store, settings, texts=PageTexts(db))
    queue = (not args.no_ocr) and ocr.info()['configured']
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    report = {'source': str(source), 'into': args.into, 'actor': args.actor, 'started_at': stamp,
              'ocr_queued': queue, 'imported': [], 'skipped': []}
    for path in files:
        relative = path.relative_to(source)
        if path.suffix.lower() not in EXTENSIONS:
            report['skipped'].append({'file': str(relative), 'reason': 'unsupported_type'})
            continue
        parts = [part for part in [args.into, *relative.parent.parts] if part]
        try:
            folder = folders.ensure_path('/'.join(parts), args.actor) if parts else None
            with path.open('rb') as stream:
                record = documents.ingest(stream, path.name, MIME[path.suffix.lower()], args.actor, 'OCR_NOT_REQUESTED')
            if folder:
                folders.file(record['id'], folder['id'], args.actor)
            relations.detect_quietly(record['id'])
            if queue:
                ocr.enqueue(documents.get(record['id']), args.actor, 'import')
            report['imported'].append({'file': str(relative), 'document_id': record['id'], 'sha256': record['sha256'],
                                       'pages': record['page_count'], 'folder': folder['path'] if folder else None})
            print(f"OK   {relative}  ->  {folder['path'] if folder else '(no folder)'}")
        except ArchiveError as exc:
            report['skipped'].append({'file': str(relative), 'reason': exc.code, 'message': exc.message})
            print(f'SKIP {relative}: {exc.code}')
    out = ROOT / 'results' / 'imports'
    out.mkdir(parents=True, exist_ok=True)
    path = out / f'import_{stamp}.json'
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"\nImported {len(report['imported'])}, skipped {len(report['skipped'])}. "
          f"OCR {'queued (start the API to process)' if queue else 'not queued'}. Report: {path.relative_to(ROOT)}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
