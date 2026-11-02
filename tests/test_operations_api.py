"""Backups, integrity and evaluation through the HTTP API, with roles (Sprint 4)."""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from fastapi.testclient import TestClient

from smartarchive.api.app import create_app
from smartarchive.config import Settings
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_ocr_pipeline import ADMIN, FakeEngine, encoded  # noqa: E402
from test_processing import text_page  # noqa: E402


class OperationsApiTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.app = create_app(Settings(storage_dir=Path(temp.name) / 'storage', ocr_worker=False),
                              engine_factory=lambda: FakeEngine(confidence=0.4))
        self.admin = self.enterContext(TestClient(self.app))
        self.assertEqual(self.admin.post('/api/auth/setup', json=ADMIN).status_code, 201)
        response = self.admin.post('/api/documents', files={'file': ('قرار.png', encoded(text_page()), 'image/png')})
        self.doc_id = response.json()['id']
        self.assertTrue(self.app.state.ocr.run_next())

    def user(self, username, role):
        self.assertEqual(self.admin.post('/api/users', json={'username': username, 'password': 'user-password-1',
                                                             'display_name': username, 'role': role}).status_code, 201)
        client = self.enterContext(TestClient(self.app))
        client.post('/api/auth/login', json={'username': username, 'password': 'user-password-1'})
        return client

    def test_admin_creates_verifies_and_downloads_backups_others_cannot(self):
        archivist = self.user('archivist1', 'archivist')
        for method, path in (('get', '/api/admin/backups'), ('post', '/api/admin/backups'), ('post', '/api/admin/integrity')):
            self.assertEqual(getattr(archivist, method)(path).status_code, 403)
        created = self.admin.post('/api/admin/backups')
        self.assertEqual(created.status_code, 201, created.text)
        name = created.json()['name']
        self.assertEqual(created.json()['document_count'], 1)
        self.assertEqual([item['name'] for item in self.admin.get('/api/admin/backups').json()['items']], [name])
        self.assertTrue(self.admin.post(f'/api/admin/backups/{name}/verify').json()['ok'])
        download = self.admin.get(f'/api/admin/backups/{name}/download')
        self.assertEqual((download.status_code, download.content[:2]), (200, b'PK'))
        self.assertEqual(self.admin.get('/api/admin/backups/..%2Farchive.sqlite3/download').status_code, 404)
        self.assertEqual(self.admin.post('/api/admin/backups/missing.zip/verify').status_code, 404)

    def test_integrity_report_and_evaluation_after_review_and_classification(self):
        report = self.admin.post('/api/admin/integrity').json()
        self.assertTrue(report['ok'])
        self.assertEqual(report['documents_checked'], 1)
        reviewer, viewer = self.user('reviewer1', 'reviewer'), self.user('viewer1', 'viewer')
        self.assertEqual(viewer.get('/api/evaluation').status_code, 403)
        saved = reviewer.post(f'/api/documents/{self.doc_id}/pages/1/text',
                              json={'text': 'قرار إداري رقم ٣', 'expected_version': 0})
        self.assertEqual(saved.status_code, 200, saved.text)
        state = reviewer.get(f'/api/documents/{self.doc_id}/classification').json()
        reviewer.post(f'/api/documents/{self.doc_id}/classification',
                      json={'category_id': 'decision', 'expected_sequence': state['sequence']})
        result = reviewer.get('/api/evaluation').json()
        self.assertEqual(result['ocr']['summary']['pages'], 1)
        self.assertGreater(result['ocr']['summary']['micro_cer'], 0)
        self.assertEqual(result['classification']['summary']['labelled'], 1)


if __name__ == '__main__':
    unittest.main()
