"""Local accounts, roles and server-side sessions.

Passwords use stdlib scrypt with a per-user salt. Session tokens are random, sent only in an
HttpOnly cookie and stored as SHA-256 hashes, so a database copy cannot replay sessions.
"""
from base64 import b64decode, b64encode
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import re
import secrets
import uuid

from smartarchive.domain.documents import ArchiveError
from smartarchive.persistence.database import Database, now

ROLES = ('admin', 'archivist', 'reviewer', 'viewer')
PERMISSIONS = {
    'documents.read': {'admin', 'archivist', 'reviewer', 'viewer'},
    'documents.upload': {'admin', 'archivist'},
    'ocr.run': {'admin', 'archivist'},
    'review.write': {'admin', 'archivist', 'reviewer'},
    'users.manage': {'admin'},
}
USERNAME = re.compile(r'[A-Za-z0-9_.-]{3,40}')
MAX_FAILED_LOGINS, LOCK_MINUTES = 5, 15
SCRYPT = {'n': 2 ** 14, 'r': 8, 'p': 1}


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, dklen=32, **SCRYPT)
    return f"scrypt${SCRYPT['n']}${SCRYPT['r']}${SCRYPT['p']}${b64encode(salt).decode()}${b64encode(digest).decode()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt, digest = stored.split('$')
        if scheme != 'scrypt':
            return False
        actual = hashlib.scrypt(password.encode(), salt=b64decode(salt), n=int(n), r=int(r), p=int(p),
                                dklen=len(b64decode(digest)))
        return hmac.compare_digest(actual, b64decode(digest))
    except (ValueError, TypeError):
        return False


def can(user: dict | None, permission: str) -> bool:
    return bool(user) and user['role'] in PERMISSIONS[permission]


def public_user(row: dict) -> dict:
    return {'id': row['id'], 'username': row['username'], 'display_name': row['display_name'],
            'role': row['role'], 'active': bool(row['active']), 'created_at': row['created_at'],
            'permissions': sorted(name for name, roles in PERMISSIONS.items() if row['role'] in roles)}


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class Accounts:
    def __init__(self, db: Database, session_hours: int):
        self.db, self.session_hours = db, session_hours

    # -- validation ---------------------------------------------------------------------------
    @staticmethod
    def _validate(username: str, password: str | None, display_name: str, role: str):
        if not USERNAME.fullmatch(username or ''):
            raise ArchiveError('invalid_username', 'اسم المستخدم من 3 إلى 40 حرفًا لاتينيًا أو أرقامًا أو . _ -', 422)
        if password is not None and not 8 <= len(password) <= 200:
            raise ArchiveError('weak_password', 'كلمة المرور يجب أن تكون 8 أحرف على الأقل.', 422)
        if not 1 <= len((display_name or '').strip()) <= 80:
            raise ArchiveError('invalid_name', 'الاسم الظاهر مطلوب (حتى 80 حرفًا).', 422)
        if role not in ROLES:
            raise ArchiveError('invalid_role', 'الدور غير معروف.', 422)

    def security_event(self, db, actor: str, action: str, subject: str, details: dict | None = None):
        db.execute('INSERT INTO security_events(actor,action,subject,timestamp,details) VALUES (?,?,?,?,?)',
                   (actor, action, subject, now(), json.dumps(details or {}, ensure_ascii=False)))

    # -- accounts -----------------------------------------------------------------------------
    def setup_required(self) -> bool:
        with self.db.connect() as db:
            return db.execute('SELECT COUNT(*) FROM users').fetchone()[0] == 0

    def create(self, username: str, password: str, display_name: str, role: str, actor: str,
               only_if_empty: bool = False) -> dict:
        self._validate(username, password, display_name, role)
        time = now()
        row = {'id': str(uuid.uuid4()), 'username': username, 'display_name': display_name.strip(),
               'role': role, 'password_hash': hash_password(password), 'active': 1, 'failed_logins': 0,
               'locked_until': None, 'created_at': time, 'updated_at': time}
        with self.db.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if only_if_empty and db.execute('SELECT COUNT(*) FROM users').fetchone()[0]:
                raise ArchiveError('setup_complete', 'تم إعداد النظام مسبقًا. سجّل الدخول.', 409)
            if db.execute('SELECT 1 FROM users WHERE username=?', (username,)).fetchone():
                raise ArchiveError('username_taken', 'اسم المستخدم مستخدم مسبقًا.', 409)
            db.execute(f"INSERT INTO users ({','.join(row)}) VALUES ({','.join('?' for _ in row)})", list(row.values()))
            self.security_event(db, actor, 'user.created', row['id'], {'username': username, 'role': role})
        return public_user(row)

    def list(self) -> list[dict]:
        with self.db.connect() as db:
            return [public_user(dict(row)) for row in db.execute('SELECT * FROM users ORDER BY created_at')]

    def update(self, user_id: str, actor: dict, role: str | None = None, active: bool | None = None,
               display_name: str | None = None, password: str | None = None) -> dict:
        with self.db.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM users WHERE id=?', (user_id,)).fetchone()
            if not row:
                raise ArchiveError('not_found', 'المستخدم غير موجود.', 404)
            row = dict(row)
            changes = {}
            if role is not None and role != row['role']:
                changes['role'] = role
            if active is not None and int(active) != row['active']:
                changes['active'] = int(active)
            if display_name is not None and display_name.strip() != row['display_name']:
                changes['display_name'] = display_name.strip()
            self._validate(row['username'], password, changes.get('display_name', row['display_name']),
                           changes.get('role', row['role']))
            demoting = changes.get('role', 'admin') != 'admin' or changes.get('active', 1) == 0
            if row['role'] == 'admin' and demoting:
                admins = db.execute("SELECT COUNT(*) FROM users WHERE role='admin' AND active=1").fetchone()[0]
                if admins <= 1:
                    raise ArchiveError('last_admin', 'لا يمكن إزالة صلاحية آخر مدير نشط.', 409)
            if password is not None:
                changes['password_hash'] = hash_password(password)
                changes['failed_logins'], changes['locked_until'] = 0, None
            if changes:
                changes['updated_at'] = now()
                db.execute(f"UPDATE users SET {','.join(f'{key}=?' for key in changes)} WHERE id=?",
                           [*changes.values(), user_id])
                if 'active' in changes or 'password_hash' in changes or 'role' in changes:
                    db.execute('DELETE FROM sessions WHERE user_id=?', (user_id,))
                logged = {key: value for key, value in changes.items()
                          if key not in ('password_hash', 'updated_at', 'failed_logins', 'locked_until')}
                if 'password_hash' in changes:
                    logged['password_changed'] = True
                self.security_event(db, actor['username'], 'user.updated', user_id, logged)
            row.update(changes)
            return public_user(row)

    # -- sessions -----------------------------------------------------------------------------
    def login(self, username: str, password: str) -> tuple[str, dict]:
        failure = ArchiveError('invalid_credentials', 'اسم المستخدم أو كلمة المرور غير صحيحة.', 401)
        with self.db.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM users WHERE username=?', (username or '',)).fetchone()
            if not row:
                hash_password(password or 'x')  # comparable work for unknown users
                self.security_event(db, (username or '?')[:80], 'login.failed', '-', {'reason': 'unknown_user'})
                db.commit()
                raise failure
            row = dict(row)
            current = datetime.now(timezone.utc)
            if row['locked_until'] and datetime.fromisoformat(row['locked_until']) > current:
                raise ArchiveError('locked', 'الحساب مقفل مؤقتًا بسبب محاولات فاشلة. حاول بعد 15 دقيقة.', 429)
            if not verify_password(password or '', row['password_hash']):
                failed = row['failed_logins'] + 1
                locked = (current + timedelta(minutes=LOCK_MINUTES)).isoformat() if failed >= MAX_FAILED_LOGINS else None
                db.execute('UPDATE users SET failed_logins=?,locked_until=? WHERE id=?',
                           (0 if locked else failed, locked, row['id']))
                self.security_event(db, row['username'], 'login.failed', row['id'], {'locked': bool(locked)})
                db.commit()
                raise failure
            if not row['active']:
                raise ArchiveError('inactive', 'هذا الحساب معطّل. تواصل مع مدير النظام.', 403)
            token = secrets.token_urlsafe(32)
            expires = current + timedelta(hours=self.session_hours)
            db.execute('UPDATE users SET failed_logins=0,locked_until=NULL WHERE id=?', (row['id'],))
            db.execute('DELETE FROM sessions WHERE expires_at<?', (current.isoformat(),))
            db.execute('INSERT INTO sessions(token_hash,user_id,created_at,expires_at) VALUES (?,?,?,?)',
                       (_token_hash(token), row['id'], current.isoformat(), expires.isoformat()))
            self.security_event(db, row['username'], 'login.succeeded', row['id'])
            return token, public_user(row)

    def user_for(self, token: str | None) -> dict | None:
        if not token or len(token) > 200:
            return None
        with self.db.connect() as db:
            row = db.execute('''SELECT users.* , sessions.expires_at FROM sessions JOIN users ON users.id=sessions.user_id
                                WHERE token_hash=?''', (_token_hash(token),)).fetchone()
            if not row or not row['active'] or datetime.fromisoformat(row['expires_at']) <= datetime.now(timezone.utc):
                return None
            return public_user(dict(row))

    def logout(self, token: str | None, actor: str):
        if not token:
            return
        with self.db.connect() as db:
            db.execute('DELETE FROM sessions WHERE token_hash=?', (_token_hash(token),))
            self.security_event(db, actor, 'logout', actor)
