"""SQLite repositories with transactional upload/audit and append-only events.

Schema changes are versioned with PRAGMA user_version; migrations only add tables.
"""
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
            version = db.execute('PRAGMA user_version').fetchone()[0]
            for target, script in MIGRATIONS:
                if version < target:
                    db.executescript(script)
                    db.execute(f'PRAGMA user_version={target}')

    def insert(self, record: dict, actor: str = 'local'):
        with self.connect() as db:
            keys = list(record)
            db.execute(f"INSERT INTO documents ({','.join(keys)}) VALUES ({','.join('?' for _ in keys)})",
                       list(record.values()))
            self._event(db, record['id'], 'document.uploaded', {'sha256': record['sha256'],
                                                               'size_bytes': record['size_bytes']}, actor)

    @staticmethod
    def _event(db, document_id: str, action: str, details: dict, actor: str = 'local'):
        db.execute('INSERT INTO audit_events(document_id,action,actor,timestamp,details) VALUES (?,?,?,?,?)',
                   (document_id, action, actor, now(), json.dumps(details, ensure_ascii=False)))

    def event(self, document_id: str, action: str, details: dict | None = None, actor: str = 'local'):
        with self.connect() as db:
            self._event(db, document_id, action, details or {}, actor)

    def set_status(self, db, document_id: str, status: str, reason: str):
        db.execute('UPDATE documents SET status=?,status_reason=?,updated_at=? WHERE id=?',
                   (status, reason, now(), document_id))

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


MIGRATIONS = [(2, '''
    CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY, username TEXT NOT NULL UNIQUE COLLATE NOCASE, display_name TEXT NOT NULL,
        role TEXT NOT NULL CHECK(role IN ('admin','archivist','reviewer','viewer')),
        password_hash TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
        failed_logins INTEGER NOT NULL DEFAULT 0, locked_until TEXT,
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS sessions (
        token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id),
        created_at TEXT NOT NULL, expires_at TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS sessions_user ON sessions(user_id);
    CREATE TABLE IF NOT EXISTS security_events (
        sequence INTEGER PRIMARY KEY AUTOINCREMENT, actor TEXT NOT NULL, action TEXT NOT NULL,
        subject TEXT NOT NULL, timestamp TEXT NOT NULL, details TEXT NOT NULL
    );
    CREATE TRIGGER IF NOT EXISTS security_no_update BEFORE UPDATE ON security_events
        BEGIN SELECT RAISE(ABORT,'security events are append-only'); END;
    CREATE TRIGGER IF NOT EXISTS security_no_delete BEFORE DELETE ON security_events
        BEGIN SELECT RAISE(ABORT,'security events are append-only'); END;
    CREATE TABLE IF NOT EXISTS ocr_runs (
        id TEXT PRIMARY KEY, document_id TEXT NOT NULL REFERENCES documents(id),
        status TEXT NOT NULL CHECK(status IN ('queued','processing','ready','failed')),
        engine TEXT NOT NULL, engine_version TEXT, languages TEXT NOT NULL, params TEXT NOT NULL,
        created_by TEXT NOT NULL, created_at TEXT NOT NULL, started_at TEXT, finished_at TEXT,
        error TEXT, pages_total INTEGER NOT NULL, pages_done INTEGER NOT NULL DEFAULT 0,
        mean_confidence REAL, review_required INTEGER
    );
    CREATE INDEX IF NOT EXISTS ocr_runs_document ON ocr_runs(document_id, created_at DESC);
    CREATE INDEX IF NOT EXISTS ocr_runs_status ON ocr_runs(status, created_at);
    CREATE TABLE IF NOT EXISTS page_analyses (
        run_id TEXT NOT NULL REFERENCES ocr_runs(id), page_no INTEGER NOT NULL,
        width INTEGER NOT NULL, height INTEGER NOT NULL, dpi REAL, dpi_source TEXT NOT NULL,
        metrics TEXT NOT NULL, quality_score REAL NOT NULL, suggested_route TEXT NOT NULL,
        blank INTEGER NOT NULL, preprocessing TEXT NOT NULL, mean_confidence REAL,
        review_required INTEGER NOT NULL, text_length INTEGER NOT NULL,
        PRIMARY KEY(run_id, page_no)
    );
    CREATE TABLE IF NOT EXISTS ocr_lines (
        run_id TEXT NOT NULL REFERENCES ocr_runs(id), page_no INTEGER NOT NULL, line_no INTEGER NOT NULL,
        text TEXT NOT NULL, confidence REAL, x0 REAL NOT NULL, y0 REAL NOT NULL, x1 REAL NOT NULL,
        y1 REAL NOT NULL, words TEXT NOT NULL, PRIMARY KEY(run_id, page_no, line_no)
    );
'''),
    # Sprint 2: human page revisions (append-only) and the derived, searchable page text.
    (3, '''
    CREATE TABLE IF NOT EXISTS page_revisions (
        id TEXT PRIMARY KEY, document_id TEXT NOT NULL REFERENCES documents(id), page_no INTEGER NOT NULL,
        version INTEGER NOT NULL CHECK(version>0), base_source TEXT NOT NULL CHECK(base_source IN ('ocr','review')),
        base_run_id TEXT REFERENCES ocr_runs(id), text TEXT NOT NULL, note TEXT NOT NULL,
        author TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(document_id, page_no, version)
    );
    CREATE TRIGGER IF NOT EXISTS revisions_no_update BEFORE UPDATE ON page_revisions
        BEGIN SELECT RAISE(ABORT,'page revisions are append-only'); END;
    CREATE TRIGGER IF NOT EXISTS revisions_no_delete BEFORE DELETE ON page_revisions
        BEGIN SELECT RAISE(ABORT,'page revisions are append-only'); END;
    CREATE TABLE IF NOT EXISTS page_texts (
        document_id TEXT NOT NULL REFERENCES documents(id), page_no INTEGER NOT NULL,
        source TEXT NOT NULL CHECK(source IN ('ocr','review')), run_id TEXT REFERENCES ocr_runs(id),
        revision INTEGER, text TEXT NOT NULL, normalized TEXT NOT NULL, updated_at TEXT NOT NULL,
        PRIMARY KEY(document_id, page_no)
    );
''')]
