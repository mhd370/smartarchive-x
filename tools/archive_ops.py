r"""Archive operations from the command line (no web server needed).

  .\.venv\Scripts\python.exe tools/archive_ops.py backup                       # new verified backup
  .\.venv\Scripts\python.exe tools/archive_ops.py verify BACKUP.zip
  .\.venv\Scripts\python.exe tools/archive_ops.py restore BACKUP.zip D:\restored-storage
  .\.venv\Scripts\python.exe tools/archive_ops.py integrity
  .\.venv\Scripts\python.exe tools/archive_ops.py evaluate                     # JSON + CSV in results/evaluation/

--storage defaults to SMARTARCHIVE_STORAGE_DIR or ./storage. Restore only writes into a new or empty
folder; point SMARTARCHIVE_STORAGE_DIR at it afterwards. Nothing here deletes or overwrites data.
"""
import argparse
import csv
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from smartarchive.domain.documents import ArchiveError  # noqa: E402
from smartarchive.operations import evaluation  # noqa: E402
from smartarchive.operations.backup import Backups, integrity, restore, verify_file  # noqa: E402
from smartarchive.persistence.database import Database  # noqa: E402

ACTOR = 'cli:' + (os.getenv('USERNAME') or os.getenv('USER') or 'local')


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8', errors='replace')
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--storage', type=Path, default=Path(os.getenv('SMARTARCHIVE_STORAGE_DIR', ROOT / 'storage')))
    parser.add_argument('--backup-dir', type=Path, default=Path(os.environ['SMARTARCHIVE_BACKUP_DIR'])
                        if os.getenv('SMARTARCHIVE_BACKUP_DIR') else None)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('backup')
    commands.add_parser('verify').add_argument('backup', type=Path)
    restore_parser = commands.add_parser('restore')
    restore_parser.add_argument('backup', type=Path)
    restore_parser.add_argument('target', type=Path)
    commands.add_parser('integrity')
    commands.add_parser('evaluate').add_argument('--out', type=Path, default=ROOT / 'results' / 'evaluation')
    args = parser.parse_args(argv)
    storage = args.storage.resolve()
    try:
        if args.command == 'backup':
            backups = Backups(storage, args.backup_dir)
            created = backups.create(ACTOR)
            report = backups.verify(created['name'], ACTOR)
            print(json.dumps({'backup': str(backups.dir / created['name']), **created, 'verified': report['ok']},
                             ensure_ascii=False, indent=2))
            return 0 if report['ok'] else 1
        if args.command == 'verify':
            report = verify_file(args.backup)
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 0 if report['ok'] else 1
        if args.command == 'restore':
            print(json.dumps(restore(args.backup, args.target), ensure_ascii=False, indent=2))
            print('Restored. Set SMARTARCHIVE_STORAGE_DIR to the target folder to use it.')
            return 0
        if args.command == 'integrity':
            report = integrity(storage, ACTOR)
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 0 if report['ok'] else 1
        if args.command == 'evaluate':
            report = evaluation.report(Database(storage / 'archive.sqlite3'))
            args.out.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
            json_path = args.out / f'evaluation_{stamp}.json'
            json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
            csv_path = args.out / f'ocr_pages_{stamp}.csv'
            with csv_path.open('w', newline='', encoding='utf-8-sig') as handle:
                fields = ['document_id', 'filename', 'page_no', 'run_id', 'ocr_confidence', 'cer', 'wer', 'char_errors',
                          'chars', 'word_errors', 'words', 'substitutions', 'deletions', 'insertions']
                writer = csv.DictWriter(handle, fields)
                writer.writeheader()
                writer.writerows(report['ocr']['pages'])
            print(json.dumps({'ocr': report['ocr']['summary'], 'classification': report['classification']['summary'],
                              'json': str(json_path), 'csv': str(csv_path)}, ensure_ascii=False, indent=2))
            return 0
    except ArchiveError as exc:
        print(f'ERROR {exc.code}: {exc.message}', file=sys.stderr)
        return 2
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
