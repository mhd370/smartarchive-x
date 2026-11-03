"""Classification through the HTTP API: automatic suggestion after OCR, roles, reclassification (Sprint 3)."""
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


class ClassificationApiTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.app = create_app(Settings(storage_dir=Path(temp.name), ocr_worker=False),
                              engine_factory=lambda: FakeEngine(confidence=0.95))
        self.admin = self.enterContext(TestClient(self.app))
        self.assertEqual(self.admin.post('/api/auth/setup', json=ADMIN).status_code, 201)

    def user(self, username, role):
        response = self.admin.post('/api/users', json={'username': username, 'password': 'user-password-1',
                                                       'display_name': username, 'role': role})
        self.assertEqual(response.status_code, 201, response.text)
        client = self.enterContext(TestClient(self.app))
        self.assertEqual(client.post('/api/auth/login', json={'username': username,
                                                              'password': 'user-password-1'}).status_code, 200)
        return client

    def processed(self, name='قرار.png'):
        response = self.admin.post('/api/documents', files={'file': (name, encoded(text_page()), 'image/png')})
        self.assertEqual(response.status_code, 201, response.text)
        self.assertTrue(self.app.state.ocr.run_next())
        return response.json()['id']

    def test_ocr_completion_suggests_and_reviewer_confirms_then_reclassifies(self):
        doc_id = self.processed()
        viewer, reviewer = self.user('viewer1', 'viewer'), self.user('reviewer1', 'reviewer')
        state = viewer.get(f'/api/documents/{doc_id}/classification').json()
        self.assertEqual((state['state'], state['category_id'], state['category_name']), ('suggested', 'decision', 'قرار إداري'))
        self.assertIn('قرار', [hit['keyword'] for hit in state['suggestion']['evidence']['decision']])
        self.assertEqual(reviewer.get('/api/classification/queue').json()['total'], 1)
        self.assertEqual(viewer.get('/api/classification/queue').status_code, 403)

        body = {'category_id': 'decision', 'expected_sequence': state['sequence']}
        self.assertEqual(viewer.post(f'/api/documents/{doc_id}/classification', json=body).status_code, 403)
        confirmed = reviewer.post(f'/api/documents/{doc_id}/classification', json=body)
        self.assertEqual(confirmed.status_code, 200, confirmed.text)
        self.assertEqual(confirmed.json()['state'], 'confirmed')
        listed = viewer.get('/api/documents', params={'category': 'decision'}).json()
        self.assertEqual((listed['total'], listed['items'][0]['category_state']), (1, 'confirmed'))
        self.assertEqual(viewer.get('/api/documents', params={'category': 'outgoing_letter'}).json()['total'], 0)

        change = {'category_id': 'outgoing_letter', 'expected_sequence': confirmed.json()['sequence']}
        refused = reviewer.post(f'/api/documents/{doc_id}/classification', json=change)
        self.assertEqual((refused.status_code, refused.json()['code']), (422, 'reason_required'))
        changed = reviewer.post(f'/api/documents/{doc_id}/classification', json={**change, 'reason': 'كتاب مرافق'})
        self.assertEqual(changed.json()['category_id'], 'outgoing_letter')
        stale = reviewer.post(f'/api/documents/{doc_id}/classification', json={**change, 'reason': 'x'})
        self.assertEqual((stale.status_code, stale.json()['code']), (409, 'stale_classification'))
        actions = [e['action'] for e in self.admin.get(f'/api/documents/{doc_id}/audit').json()['items']]
        self.assertEqual([a for a in actions if a.startswith('classification.')],
                         ['classification.confirmed', 'classification.changed'])

        self.assertEqual(viewer.get('/api/search', params={'q': 'قرار', 'category': 'outgoing_letter'}).json()['total'], 1)
        self.assertEqual(viewer.get('/api/search', params={'q': 'قرار', 'category': 'decision'}).json()['total'], 0)
        stats = viewer.get('/api/statistics').json()
        self.assertEqual(stats['classification']['confirmed'], 1)
        self.assertEqual(next(c for c in stats['categories'] if c['id'] == 'outgoing_letter')['confirmed'], 1)

        # Sprint 9: a corrected page is new evidence; the strong disagreement is proposed, never applied.
        self.assertEqual(reviewer.get('/api/classification/reclassification').json()['total'], 0)
        page = viewer.get(f'/api/documents/{doc_id}/pages/1/text').json()
        revised = reviewer.post(f'/api/documents/{doc_id}/pages/1/text', json={
            'text': 'قرار إداري رقم ١٢ بشأن تشكيل لجنة. قررنا ما يلي: يُعمل بهذا القرار من تاريخه.',
            'expected_version': page['version'], 'note': 'تصحيح'})
        self.assertEqual(revised.status_code, 200, revised.text)
        state = viewer.get(f'/api/documents/{doc_id}/classification').json()
        self.assertEqual((state['category_id'], state['state']), ('outgoing_letter', 'confirmed'))
        proposal = state['reclassification']
        self.assertEqual((proposal['from_category_id'], proposal['to_category_id']), ('outgoing_letter', 'decision'))
        self.assertEqual(viewer.get('/api/classification/reclassification').status_code, 403)
        listed = reviewer.get('/api/classification/reclassification').json()
        self.assertEqual([item['document_id'] for item in listed['items']], [doc_id])
        dismiss = f'/api/documents/{doc_id}/classification/reclassification/dismiss'
        self.assertEqual(viewer.post(dismiss, json={'suggestion_id': proposal['suggestion_id']}).status_code, 403)
        kept = reviewer.post(dismiss, json={'suggestion_id': proposal['suggestion_id'], 'reason': 'كتاب يحيل القرار'})
        self.assertEqual((kept.status_code, kept.json()['reclassification']), (200, None))
        again = reviewer.post(dismiss, json={'suggestion_id': proposal['suggestion_id']})
        self.assertEqual((again.status_code, again.json()['code']), (409, 'no_open_proposal'))

    def test_manual_suggestion_and_category_administration(self):
        doc_id = self.processed('مستند.png')
        reviewer, viewer = self.user('reviewer1', 'reviewer'), self.user('viewer1', 'viewer')
        self.assertEqual(viewer.get(f'/api/documents/{doc_id}/classification').json()['state'], 'uncertain')
        self.assertEqual(viewer.post(f'/api/documents/{doc_id}/classification/suggest').status_code, 403)

        self.assertEqual(len(viewer.get('/api/categories').json()['items']), 8)
        body = {'id': 'admin-note', 'name': 'مذكرة إدارية', 'keywords': ['قرار', 'إداري', 'مذكرة']}
        self.assertEqual(viewer.post('/api/categories', json=body).status_code, 403)
        self.assertEqual(self.admin.post('/api/categories', json=body).status_code, 201)
        self.assertEqual(self.admin.post('/api/categories', json=body).status_code, 409)
        self.assertEqual(self.admin.post('/api/categories', json={**body, 'id': 'x y'}).status_code, 422)
        resuggested = reviewer.post(f'/api/documents/{doc_id}/classification/suggest').json()
        self.assertEqual((resuggested['state'], resuggested['category_id']), ('suggested', 'admin-note'))
        self.assertEqual(self.admin.patch('/api/categories/admin-note', json={'active': False}).status_code, 200)
        self.assertEqual(self.admin.patch('/api/categories/missing', json={'active': False}).status_code, 404)
        refused = reviewer.post(f'/api/documents/{doc_id}/classification',
                                json={'category_id': 'admin-note', 'expected_sequence': resuggested['sequence']})
        self.assertEqual(refused.status_code, 422)


if __name__ == '__main__':
    unittest.main()
