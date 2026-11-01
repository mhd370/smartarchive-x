"""Search and page review through the HTTP API, with roles and the OCR worker (Sprint 2)."""
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


class ReviewApiTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.engine = FakeEngine(confidence=0.42)
        self.app = create_app(Settings(storage_dir=Path(temp.name), ocr_worker=False),
                              engine_factory=lambda: self.engine)
        self.admin = self.enterContext(TestClient(self.app))
        self.assertEqual(self.admin.post('/api/auth/setup', json=ADMIN).status_code, 201)

    def user(self, username, role):
        response = self.admin.post('/api/users', json={'username': username, 'password': 'user-password-1',
                                                       'display_name': username, 'role': role})
        self.assertEqual(response.status_code, 201, response.text)
        client = self.enterContext(TestClient(self.app))
        login = client.post('/api/auth/login', json={'username': username, 'password': 'user-password-1'})
        self.assertEqual(login.status_code, 200)
        return client

    def processed_document(self):
        response = self.admin.post('/api/documents', files={'file': ('قرار.png', encoded(text_page()), 'image/png')})
        self.assertEqual(response.status_code, 201, response.text)
        self.assertTrue(self.app.state.ocr.run_next())
        return response.json()['id']

    def test_completed_run_is_searchable_with_highlighted_snippets(self):
        doc_id = self.processed_document()
        viewer = self.user('viewer1', 'viewer')
        result = viewer.get('/api/search', params={'q': 'اداري'}).json()
        self.assertEqual(result['total'], 1)
        hit = result['items'][0]
        self.assertEqual((hit['document']['id'], hit['pages'][0]['page_no'], hit['pages'][0]['source']), (doc_id, 1, 'ocr'))
        self.assertEqual([p['text'] for p in hit['pages'][0]['snippets'][0] if p['match']], ['إداري'])
        self.assertEqual(viewer.get('/api/search', params={'q': ''}).status_code, 422)
        self.assertEqual(TestClient(self.app).get('/api/search', params={'q': 'قرار'}).status_code, 401)

    def test_reviewer_corrects_low_confidence_page_and_viewer_cannot(self):
        doc_id = self.processed_document()
        stats = self.admin.get('/api/statistics').json()
        self.assertEqual((stats['pages_pending_review'], stats['pages_reviewed']), (1, 0))
        status = self.admin.get(f'/api/documents/{doc_id}/status').json()
        self.assertEqual((status['reason'], status['pending_review_pages']), ('REVIEW_REQUIRED', 1))

        viewer, reviewer = self.user('viewer1', 'viewer'), self.user('reviewer1', 'reviewer')
        self.assertEqual(viewer.get('/api/review/queue').status_code, 403)
        queue = reviewer.get('/api/review/queue').json()
        self.assertEqual([(i['document_id'], i['page_no']) for i in queue['items']], [(doc_id, 1)])
        page = viewer.get(f'/api/documents/{doc_id}/pages/1/text').json()
        self.assertEqual((page['text'], page['version'], page['source']), ('قرار إداري', 0, 'ocr'))

        body = {'text': 'قرار إداري رقم ٧', 'expected_version': 0, 'note': 'إضافة الرقم'}
        self.assertEqual(viewer.post(f'/api/documents/{doc_id}/pages/1/text', json=body).status_code, 403)
        saved = reviewer.post(f'/api/documents/{doc_id}/pages/1/text', json=body)
        self.assertEqual(saved.status_code, 200, saved.text)
        self.assertEqual((saved.json()['version'], saved.json()['revisions'][0]['author']), (1, 'reviewer1'))
        stale = reviewer.post(f'/api/documents/{doc_id}/pages/1/text', json={**body, 'text': 'آخر'})
        self.assertEqual((stale.status_code, stale.json()['code']), (409, 'stale_version'))

        self.assertEqual(self.admin.get(f'/api/documents/{doc_id}').json()['status_reason'], 'REVIEW_COMPLETED')
        self.assertEqual(reviewer.get('/api/review/queue').json()['total'], 0)
        self.assertEqual(self.admin.get('/api/statistics').json()['pages_reviewed'], 1)
        self.assertEqual(viewer.get('/api/search', params={'q': '7'}).json()['items'][0]['pages'][0]['source'], 'review')
        old = viewer.get(f'/api/documents/{doc_id}/pages/1/revisions/1').json()
        self.assertEqual(old['text'], 'قرار إداري رقم ٧')
        actions = [e['action'] for e in self.admin.get(f'/api/documents/{doc_id}/audit').json()['items']]
        self.assertIn('page.reviewed', actions)

    def test_review_rejects_bad_pages_and_unprocessed_documents(self):
        doc_id = self.processed_document()
        reviewer = self.user('reviewer1', 'reviewer')
        body = {'text': 'x', 'expected_version': 0}
        self.assertEqual(reviewer.post(f'/api/documents/{doc_id}/pages/9/text', json=body).status_code, 404)
        self.assertEqual(reviewer.get(f'/api/documents/{doc_id}/pages/0/text').status_code, 404)
        self.assertEqual(reviewer.post(f'/api/documents/{doc_id}/pages/1/text', json={'text': 'x'}).status_code, 422)
        self.assertEqual(self.admin.post(f'/api/documents/{doc_id}/ocr').status_code, 201)  # re-run queued
        busy = reviewer.post(f'/api/documents/{doc_id}/pages/1/text', json=body)
        self.assertEqual((busy.status_code, busy.json()['code']), (409, 'not_ready'))


if __name__ == '__main__':
    unittest.main()
