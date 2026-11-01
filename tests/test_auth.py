"""Accounts, roles, sessions and audit identity (Task 006)."""
from io import BytesIO
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from fastapi.testclient import TestClient
from PIL import Image
from smartarchive.api.app import create_app
from smartarchive.config import Settings
from smartarchive.services.auth import hash_password, verify_password

ADMIN = {'username': 'admin', 'password': 'admin-password-1', 'display_name': 'مدير النظام'}


def png() -> bytes:
    buffer = BytesIO()
    Image.new('RGB', (40, 50), 'white').save(buffer, format='PNG')
    return buffer.getvalue()


class AuthTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.settings = Settings(storage_dir=Path(self.temp.name), ocr_auto=False, ocr_worker=False)
        self.app = create_app(self.settings)
        self.client = self.enterContext(TestClient(self.app))

    def new_client(self):
        return self.enterContext(TestClient(self.app))

    def setup_admin(self):
        response = self.client.post('/api/auth/setup', json=ADMIN)
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def add_user(self, username, role, password='user-password-1'):
        response = self.client.post('/api/users', json={'username': username, 'password': password,
                                                         'display_name': username, 'role': role})
        self.assertEqual(response.status_code, 201, response.text)
        client = self.new_client()
        self.assertEqual(client.post('/api/auth/login', json={'username': username, 'password': password}).status_code, 200)
        return response.json(), client

    def test_password_hash_is_salted_and_verifiable(self):
        first, second = hash_password('correct horse'), hash_password('correct horse')
        self.assertNotEqual(first, second)
        self.assertTrue(verify_password('correct horse', first))
        self.assertFalse(verify_password('wrong horse', first))
        self.assertFalse(verify_password('x', 'not-a-hash'))

    def test_everything_requires_a_session_except_status_and_health(self):
        self.assertTrue(self.client.get('/api/auth/status').json()['setup_required'])
        self.assertEqual(self.client.get('/api/health').status_code, 200)
        for path in ('/api/statistics', '/api/documents', '/api/auth/me', '/api/users'):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 401)
                self.assertEqual(response.json()['code'], 'unauthenticated')
        upload = self.client.post('/api/documents', files={'file': ('a.png', png(), 'image/png')})
        self.assertEqual(upload.status_code, 401)

    def test_setup_once_creates_admin_and_session(self):
        user = self.setup_admin()
        self.assertEqual(user['role'], 'admin')
        self.assertNotIn('password_hash', user)
        self.assertEqual(self.client.get('/api/auth/me').json()['username'], 'admin')
        cookie = self.client.cookies.get('sa_session')
        self.assertTrue(cookie)
        again = self.new_client().post('/api/auth/setup', json={**ADMIN, 'username': 'second'})
        self.assertEqual(again.status_code, 409)
        with self.app.state.accounts.db.connect() as db:
            stored = db.execute('SELECT token_hash FROM sessions').fetchone()[0]
        self.assertNotEqual(stored, cookie)

    def test_login_rejects_bad_credentials_and_locks_after_repeated_failures(self):
        self.setup_admin()
        anonymous = self.new_client()
        for _ in range(5):
            self.assertEqual(anonymous.post('/api/auth/login', json={'username': 'admin', 'password': 'nope-nope'}).status_code, 401)
        locked = anonymous.post('/api/auth/login', json=ADMIN)
        self.assertEqual(locked.status_code, 429)
        self.assertEqual(anonymous.post('/api/auth/login', json={'username': 'ghost', 'password': 'whatever1'}).status_code, 401)

    def test_logout_ends_the_server_session(self):
        self.setup_admin()
        self.assertEqual(self.client.post('/api/auth/logout').status_code, 204)
        self.assertEqual(self.client.get('/api/auth/me').status_code, 401)

    def test_roles_limit_actions(self):
        self.setup_admin()
        _, viewer = self.add_user('viewer1', 'viewer')
        _, archivist = self.add_user('archivist1', 'archivist')
        self.assertEqual(viewer.post('/api/documents', files={'file': ('a.png', png(), 'image/png')}).status_code, 403)
        self.assertEqual(viewer.get('/api/users').status_code, 403)
        created = archivist.post('/api/documents', files={'file': ('a.png', png(), 'image/png')})
        self.assertEqual(created.status_code, 201, created.text)
        self.assertEqual(viewer.get(f"/api/documents/{created.json()['id']}").status_code, 200)
        self.assertEqual(archivist.post('/api/users', json={'username': 'x1x', 'password': 'pass-word-1',
                                                          'display_name': 'x', 'role': 'admin'}).status_code, 403)

    def test_audit_records_the_acting_user(self):
        self.setup_admin()
        _, archivist = self.add_user('archivist1', 'archivist')
        document = archivist.post('/api/documents', files={'file': ('a.png', png(), 'image/png')}).json()
        self.client.get(f"/api/documents/{document['id']}/download")
        events = self.client.get(f"/api/documents/{document['id']}/audit").json()['items']
        self.assertEqual([(e['action'], e['actor']) for e in events],
                         [('document.uploaded', 'archivist1'), ('document.downloaded', 'admin')])

    def test_deactivation_and_role_change_revoke_sessions_and_last_admin_is_protected(self):
        admin = self.setup_admin()
        user, client = self.add_user('reviewer1', 'reviewer')
        self.assertEqual(self.client.patch(f"/api/users/{user['id']}", json={'active': False}).status_code, 200)
        self.assertEqual(client.get('/api/auth/me').status_code, 401)
        self.assertEqual(client.post('/api/auth/login', json={'username': 'reviewer1', 'password': 'user-password-1'}).status_code, 403)
        demote = self.client.patch(f"/api/users/{admin['id']}", json={'role': 'viewer'})
        self.assertEqual(demote.status_code, 409)
        self.assertEqual(demote.json()['code'], 'last_admin')

    def test_validation_and_duplicates(self):
        self.setup_admin()
        bad = [{'username': 'a', 'password': 'long-enough', 'display_name': 'x', 'role': 'viewer'},
               {'username': 'valid_name', 'password': 'short', 'display_name': 'x', 'role': 'viewer'},
               {'username': 'valid_name', 'password': 'long-enough', 'display_name': 'x', 'role': 'owner'}]
        for body in bad:
            with self.subTest(body=body):
                self.assertEqual(self.client.post('/api/users', json=body).status_code, 422)
        self.add_user('Same.User', 'viewer')
        duplicate = self.client.post('/api/users', json={'username': 'same.user', 'password': 'long-enough',
                                                          'display_name': 'x', 'role': 'viewer'})
        self.assertEqual(duplicate.status_code, 409)

    def test_security_events_are_append_only(self):
        self.setup_admin()
        with self.app.state.accounts.db.connect() as db:
            actions = [row[0] for row in db.execute('SELECT action FROM security_events ORDER BY sequence')]
            self.assertEqual(actions, ['user.created', 'login.succeeded'])
            for sql in ('UPDATE security_events SET actor="x"', 'DELETE FROM security_events'):
                with self.assertRaises(sqlite3.IntegrityError):
                    db.execute(sql)


if __name__ == '__main__':
    unittest.main()
