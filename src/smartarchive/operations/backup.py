"""Backups, restore and integrity reconciliation.

A backup is one zip file:
  archive.sqlite3   consistent online snapshot (SQLite backup API, safe while the API is running)
  originals/<key>   every original referenced by the snapshot, byte for byte
  manifest.json     SHA-256 and size of every member, document count, schema version, creator

Restoring never touches the live storage: it extracts into a new, empty directory after verifying the
backup, re-verifies what it wrote, and the operator then points SMARTARCHIVE_STORAGE_DIR at it.
"""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import tempfile
import uuid
import zipfile

from smartarchive.domain.documents import ArchiveError

NAME = re.compile(r'smartarchive-backup-\d{8}T\d{6}Z-[0-9a-f]{8}\.zip')
KEY = re.compile(r'[0-9a-f-]{36}/original\.(pdf|png|jpe?g|webp|tiff?)')
FORMAT = 'smartarchive-backup-v1'
CHUNK = 1024 * 1024


def _sha256_file(path: Path) -> str:
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def _sha256_member(archive: zipfile.ZipFile, name: str) -> tuple[str, int]:
    digest, size = hashlib.sha256(), 0
    with archive.open(name) as member:
        while chunk := member.read(CHUNK):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def _security(db_path: Path, actor: str, action: str, subject: str, details: dict):
    connection = sqlite3.connect(db_path, timeout=15)
    try:
        with connection:
            connection.execute('INSERT INTO security_events(actor,action,subject,timestamp,details) VALUES (?,?,?,?,?)',
                               (actor, action, subject, datetime.now(timezone.utc).isoformat(),
                                json.dumps(details, ensure_ascii=False)))
    finally:
        connection.close()


def verify_file(path: Path) -> dict:
    """Check every member against the manifest, the database's integrity and every document's original."""
    problems: list[str] = []
    try:
        archive = zipfile.ZipFile(path)
    except (OSError, zipfile.BadZipFile) as exc:
        return {'ok': False, 'problems': [f'unreadable: {exc}'], 'manifest': None}
    with archive, tempfile.TemporaryDirectory() as temp:
        try:
            manifest = json.loads(archive.read('manifest.json'))
        except (KeyError, ValueError):
            return {'ok': False, 'problems': ['manifest.json missing or invalid'], 'manifest': None}
        if manifest.get('format') != FORMAT:
            problems.append(f"unknown format {manifest.get('format')!r}")
        listed = {entry['path']: entry for entry in manifest.get('files', [])}
        names = {name for name in archive.namelist() if name != 'manifest.json'}
        problems += [f'not in manifest: {name}' for name in sorted(names - listed.keys())]
        problems += [f'missing from backup: {name}' for name in sorted(listed.keys() - names)]
        for name in sorted(names & listed.keys()):
            digest, size = _sha256_member(archive, name)
            if digest != listed[name]['sha256'] or size != listed[name]['size']:
                problems.append(f'checksum mismatch: {name}')
        documents = 0
        if 'archive.sqlite3' in names:
            database = Path(temp) / 'archive.sqlite3'
            with archive.open('archive.sqlite3') as source, database.open('wb') as target:
                shutil.copyfileobj(source, target, CHUNK)
            connection = sqlite3.connect(database)
            try:
                result = connection.execute('PRAGMA integrity_check').fetchone()[0]
                if result != 'ok':
                    problems.append(f'database integrity: {result}')
                rows = connection.execute('SELECT id, storage_key, sha256, size_bytes FROM documents').fetchall()
            finally:
                connection.close()
            documents = len(rows)
            for doc_id, key, sha, size in rows:
                entry = listed.get('originals/' + key)
                if not entry:
                    problems.append(f'original missing for document {doc_id}')
                elif entry['sha256'] != sha or entry['size'] != size:
                    problems.append(f'original does not match database for document {doc_id}')
            if documents != manifest.get('document_count'):
                problems.append('document count differs from manifest')
        else:
            problems.append('archive.sqlite3 missing')
    return {'ok': not problems, 'problems': problems[:200], 'problem_count': len(problems),
            'documents': documents, 'manifest': {k: v for k, v in manifest.items() if k != 'files'}}


def restore(backup: Path, target: Path) -> dict:
    """Extract a verified backup into a new or empty directory; never overwrites anything."""
    report = verify_file(backup)
    if not report['ok']:
        raise ArchiveError('backup_invalid', 'النسخة الاحتياطية لم تجتز التحقق؛ لم تُستعد.', 422)
    target = target.resolve()
    if target.exists() and any(target.iterdir()):
        raise ArchiveError('target_not_empty', 'مجلد الاستعادة يجب أن يكون جديدًا أو فارغًا.', 409)
    target.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(backup) as archive:
        manifest = json.loads(archive.read('manifest.json'))
        for entry in manifest['files']:
            name = entry['path']
            if name != 'archive.sqlite3' and not (name.startswith('originals/') and KEY.fullmatch(name[10:])):
                raise ArchiveError('backup_invalid', f'مسار غير متوقع داخل النسخة: {name}', 422)
            destination = target / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(name) as source, destination.open('xb') as out:
                shutil.copyfileobj(source, out, CHUNK)
            if _sha256_file(destination) != entry['sha256']:
                raise ArchiveError('restore_failed', f'فشل التحقق بعد الاستعادة: {name}', 500)
    (target / 'RESTORED_FROM.txt').write_text(
        f'{backup.name}\nrestored_at={datetime.now(timezone.utc).isoformat()}\n'
        f"created_at={manifest.get('created_at')}\ndocuments={manifest.get('document_count')}\n", encoding='utf-8')
    return {'target': str(target), 'documents': manifest.get('document_count'), 'files': len(manifest['files'])}


class Backups:
    def __init__(self, storage_dir: Path, backup_dir: Path | None = None, app_version: str = ''):
        self.storage = storage_dir.resolve()
        self.database = self.storage / 'archive.sqlite3'
        self.originals = self.storage / 'originals'
        self.dir = (backup_dir or self.storage / 'backups').resolve()
        self.app_version = app_version

    def path(self, name: str) -> Path:
        if not NAME.fullmatch(name or ''):
            raise ArchiveError('backup_not_found', 'النسخة الاحتياطية غير موجودة.', 404)
        path = self.dir / name
        if not path.is_file():
            raise ArchiveError('backup_not_found', 'النسخة الاحتياطية غير موجودة.', 404)
        return path

    def create(self, actor: str) -> dict:
        self.dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc)
        name = f"smartarchive-backup-{stamp.strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}.zip"
        part = self.dir / (name + '.part')
        with tempfile.TemporaryDirectory(dir=self.dir) as temp:
            snapshot = Path(temp) / 'archive.sqlite3'
            source, copy = sqlite3.connect(self.database, timeout=15), sqlite3.connect(snapshot)
            try:
                source.backup(copy)
                rows = copy.execute('SELECT id, storage_key, sha256, size_bytes FROM documents ORDER BY created_at, id').fetchall()
                schema = copy.execute('PRAGMA user_version').fetchone()[0]
            finally:
                copy.close()
                source.close()
            files = [{'path': 'archive.sqlite3', 'sha256': _sha256_file(snapshot), 'size': snapshot.stat().st_size}]
            problems = []
            try:
                with zipfile.ZipFile(part, 'x', zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
                    archive.write(snapshot, 'archive.sqlite3')
                    for doc_id, key, sha, size in rows:
                        original = self.originals / key
                        if not KEY.fullmatch(key) or not original.is_file():
                            problems.append({'document_id': doc_id, 'problem': 'original_missing'})
                            continue
                        actual = _sha256_file(original)
                        if actual != sha:
                            problems.append({'document_id': doc_id, 'problem': 'checksum_mismatch'})
                            continue
                        # Originals are already compressed formats; store them as they are.
                        archive.write(original, 'originals/' + key, compress_type=zipfile.ZIP_STORED)
                        files.append({'path': 'originals/' + key, 'sha256': actual, 'size': size})
                    manifest = {'format': FORMAT, 'name': name, 'created_at': stamp.isoformat(), 'created_by': actor,
                                'app_version': self.app_version, 'schema_version': schema,
                                'document_count': len(rows), 'original_bytes': sum(f['size'] for f in files[1:]),
                                'problems': problems, 'files': files}
                    archive.writestr('manifest.json', json.dumps(manifest, ensure_ascii=False, indent=1))
                if problems:
                    raise ArchiveError('backup_integrity', 'توجد أصول مفقودة أو تالفة؛ شغّل فحص السلامة قبل النسخ الاحتياطي.', 409)
                os.replace(part, self.dir / name)
            finally:
                if part.exists():
                    part.unlink()
        _security(self.database, actor, 'backup.created', name,
                  {'documents': len(rows), 'bytes': (self.dir / name).stat().st_size})
        return self.describe(self.dir / name)

    def describe(self, path: Path) -> dict:
        item = {'name': path.name, 'size_bytes': path.stat().st_size,
                'modified_at': datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()}
        try:
            with zipfile.ZipFile(path) as archive:
                manifest = json.loads(archive.read('manifest.json'))
            item.update({key: manifest.get(key) for key in
                         ('created_at', 'created_by', 'app_version', 'schema_version', 'document_count', 'original_bytes')})
        except (OSError, KeyError, ValueError, zipfile.BadZipFile):
            item['unreadable'] = True
        return item

    def list(self) -> list[dict]:
        if not self.dir.is_dir():
            return []
        paths = [path for path in self.dir.iterdir() if path.is_file() and NAME.fullmatch(path.name)]
        return [self.describe(path) for path in sorted(paths, key=lambda p: p.name, reverse=True)]

    def verify(self, name: str, actor: str) -> dict:
        report = verify_file(self.path(name))
        _security(self.database, actor, 'backup.verified', name, {'ok': report['ok'], 'problems': report['problem_count']
                                                                   if 'problem_count' in report else len(report['problems'])})
        return {'name': name, **report}


def integrity(storage_dir: Path, actor: str) -> dict:
    """Reconcile the database with the originals on disk. Reports; never deletes or repairs anything."""
    storage = storage_dir.resolve()
    database, originals = storage / 'archive.sqlite3', storage / 'originals'
    connection = sqlite3.connect(database, timeout=15)
    connection.row_factory = sqlite3.Row
    try:
        db_check = connection.execute('PRAGMA integrity_check').fetchone()[0]
        foreign = connection.execute('PRAGMA foreign_key_check').fetchall()
        rows = connection.execute('SELECT id, filename, storage_key, sha256, size_bytes FROM documents').fetchall()
        triggers = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='trigger'")}
        unindexed = connection.execute(
            "SELECT COUNT(*) FROM ocr_runs r WHERE r.status='ready' AND r.id=(SELECT id FROM ocr_runs WHERE"
            " document_id=r.document_id AND status='ready' ORDER BY created_at DESC, id LIMIT 1) AND NOT EXISTS"
            " (SELECT 1 FROM page_texts t WHERE t.document_id=r.document_id)").fetchone()[0]
    finally:
        connection.close()
    documents, referenced = [], set()
    for row in rows:
        key = row['storage_key']
        referenced.add(key.split('/')[0])
        path = originals / key
        if not KEY.fullmatch(key) or not path.is_file():
            documents.append({'document_id': row['id'], 'filename': row['filename'], 'problem': 'original_missing'})
        elif path.stat().st_size != row['size_bytes'] or _sha256_file(path) != row['sha256']:
            documents.append({'document_id': row['id'], 'filename': row['filename'], 'problem': 'checksum_mismatch'})
    orphans, partial = [], []
    if originals.is_dir():
        for folder in sorted(originals.iterdir()):
            if folder.is_dir() and folder.name not in referenced:
                orphans.append(folder.name)
            if folder.is_dir() and (folder / 'upload.part').exists():
                partial.append(folder.name)
    expected = {'audit_no_update', 'audit_no_delete', 'original_metadata_immutable', 'security_no_update',
                'security_no_delete', 'revisions_no_update', 'revisions_no_delete', 'classifications_no_update',
                'classifications_no_delete'}
    missing_triggers = sorted(expected - triggers)
    report = {'checked_at': datetime.now(timezone.utc).isoformat(), 'checked_by': actor,
              'documents_checked': len(rows), 'database': db_check, 'foreign_key_violations': len(foreign),
              'document_problems': documents, 'orphan_folders': orphans, 'partial_uploads': partial,
              'missing_triggers': missing_triggers, 'unindexed_documents': unindexed}
    report['ok'] = (db_check == 'ok' and not foreign and not documents and not missing_triggers)
    report['warnings'] = len(orphans) + len(partial) + (1 if unindexed else 0)
    _security(database, actor, 'integrity.checked', 'archive',
              {'ok': report['ok'], 'document_problems': len(documents), 'orphans': len(orphans)})
    return report
