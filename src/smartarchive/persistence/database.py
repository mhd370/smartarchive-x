"""SQLite repositories with transactional upload/audit and append-only events."""
from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3

from smartarchive.domain.documents import ProcessingStatus


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Database:
    def __init__(self, path: Path):
        self.path = path

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.path, timeout=15)
        connection.row_factory = sqlite3.Row
        connection.execute('PRAGMA foreign_keys=ON')
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def initialize(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.executescript('''
                CREATE TABLE IF NOT EXISTS documents (
                    id TEXT PRIMARY KEY, filename TEXT NOT NULL, size_bytes INTEGER NOT NULL CHECK(size_bytes>0),
                    mime_type TEXT NOT NULL, sha256 TEXT NOT NULL, storage_key TEXT NOT NULL UNIQUE,
                    page_count INTEGER NOT NULL, status TEXT NOT NULL
                    CHECK(status IN ('stored','queued','processing','ready','failed')),
                    status_reason TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS documents_created ON documents(created_at DESC,id DESC);
                CREATE TABLE IF NOT EXISTS audit_events (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT, document_id TEXT NOT NULL REFERENCES documents(id),
                    action TEXT NOT NULL, actor TEXT NOT NULL, timestamp TEXT NOT NULL, details TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS audit_document ON audit_events(document_id,sequence);
                CREATE TRIGGER IF NOT EXISTS audit_no_update BEFORE UPDATE ON audit_events
                    BEGIN SELECT RAISE(ABORT,'audit events are append-only'); END;
                CREATE TRIGGER IF NOT EXISTS audit_no_delete BEFORE DELETE ON audit_events
                    BEGIN SELECT RAISE(ABORT,'audit events are append-only'); END;
                CREATE TRIGGER IF NOT EXISTS original_metadata_immutable
                    BEFORE UPDATE OF filename,size_bytes,mime_type,sha256,storage_key,page_count,created_at ON documents
                    BEGIN SELECT RAISE(ABORT,'original metadata is immutable'); END;
            ''')

    def insert(self, record: dict):
        with self.connect() as db:
            keys = list(record)
            db.execute(f"INSERT INTO documents ({','.join(keys)}) VALUES ({','.join('?' for _ in keys)})",
                       list(record.values()))
            self._event(db, record['id'], 'document.uploaded', {'sha256': record['sha256'],
                                                               'size_bytes': record['size_bytes']})

    @staticmethod
    def _event(db, document_id: str, action: str, details: dict):
        db.execute('INSERT INTO audit_events(document_id,action,actor,timestamp,details) VALUES (?,?,?,?,?)',
                   (document_id, action, 'local', now(), json.dumps(details, ensure_ascii=False)))

    def event(self, document_id: str, action: str, details: dict | None = None):
        with self.connect() as db:
            self._event(db, document_id, action, details or {})

    def get(self, document_id: str) -> dict | None:
        with self.connect() as db:
            row = db.execute('SELECT * FROM documents WHERE id=?', (document_id,)).fetchone()
            return dict(row) if row else None

    def list(self, query: str, status: str | None, kind: str | None, limit: int, offset: int):
        clauses, values = [], []
        if query:
            literal = query.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
            clauses.append("filename LIKE ? ESCAPE '\\'")
            values.append('%' + literal + '%')
        if status:
            clauses.append('status=?')
            values.append(status)
        if kind:
            clauses.append("mime_type='application/pdf'" if kind == 'pdf' else "mime_type LIKE 'image/%'")
        where = ' WHERE ' + ' AND '.join(clauses) if clauses else ''
        with self.connect() as db:
            total = db.execute('SELECT COUNT(*) FROM documents' + where, values).fetchone()[0]
            rows = db.execute('SELECT * FROM documents' + where + ' ORDER BY created_at DESC,id DESC LIMIT ? OFFSET ?',
                              [*values, limit, offset]).fetchall()
            return {'items': [dict(row) for row in rows], 'total': total, 'limit': limit, 'offset': offset}

    def statistics(self):
        with self.connect() as db:
            total, size = db.execute('SELECT COUNT(*),COALESCE(SUM(size_bytes),0) FROM documents').fetchone()
            counts = {status.value: 0 for status in ProcessingStatus}
            counts.update({row['status']: row['count'] for row in db.execute(
                'SELECT status,COUNT(*) AS count FROM documents GROUP BY status')})
            return {'total_documents': total, 'total_bytes': size, 'by_status': counts}

    def events(self, document_id: str):
        with self.connect() as db:
            rows = db.execute('SELECT * FROM audit_events WHERE document_id=? ORDER BY sequence',
                              (document_id,)).fetchall()
            return [{**dict(row), 'details': json.loads(row['details'])} for row in rows]
