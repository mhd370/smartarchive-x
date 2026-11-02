"""Folders, metadata and relations through the HTTP API, with roles and hooks after OCR (Sprint 5)."""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from fastapi.testclient import TestClient

from smartarchive.api.app import create_app
from smartarchive.config import Settings
from smartarchive.processing.ocr import Line, Word
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_ocr_pipeline import ADMIN, encoded  # noqa: E402
from test_processing import text_page  # noqa: E402

LINES = ['الرقم: ص/١٢٣/٢٠٢٦', 'التاريخ: ١٥/٠٣/٢٠٢٦', 'من: دائرة الشؤون الإدارية',
         'الموضوع: تمديد مدة المشروع', 'فاتورة رقم الفاتورة: 77 المبلغ ١٠٠ دينار المجموع الكمية']


class LetterEngine:
    name, languages, missing = 'fake', 'ara', []

    def version(self):
        return 'test'

    def recognize(self, image):
        return [Line(text, 0.95, (0, i * 50, 500, i * 50 + 40), [Word(text, 0.95, (0, i * 50, 500, i * 50 + 40))])
                for i, text in enumerate(LINES)]


class EnrichmentApiTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.app = create_app(Settings(storage_dir=Path(temp.name), ocr_worker=False), engine_factory=LetterEngine)
        self.admin = self.enterContext(TestClient(self.app))
        self.assertEqual(self.admin.post('/api/auth/setup', json=ADMIN).status_code, 201)

    def user(self, username, role):
        self.admin.post('/api/users', json={'username': username, 'password': 'user-password-1',
                                            'display_name': username, 'role': role})
        client = self.enterContext(TestClient(self.app))
        client.post('/api/auth/login', json={'username': username, 'password': 'user-password-1'})
        return client

    def upload(self, client, folder_id=None, seed=3):
        data = {'folder_id': folder_id} if folder_id else None
        response = client.post('/api/documents', data=data,
                               files={'file': ('scan.png', encoded(text_page(seed=seed)), 'image/png')})
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def test_folders_upload_into_folder_move_and_filter(self):
        viewer = self.user('viewer1', 'viewer')
        self.assertEqual(viewer.post('/api/folders', json={'name': 'x'}).status_code, 403)
        root = self.admin.post('/api/folders', json={'name': 'المالية'}).json()
        child = self.admin.post('/api/folders', json={'name': 'فواتير', 'parent_id': root['id']}).json()
        self.assertEqual(child['path'], 'المالية/فواتير')
        self.assertEqual(self.admin.post('/api/folders', json={'name': 'a/b'}).status_code, 422)
        self.assertEqual(self.admin.post('/api/documents', data={'folder_id': 'missing'},
                                         files={'file': ('a.png', encoded(text_page()), 'image/png')}).status_code, 404)
        doc = self.upload(self.admin, child['id'])
        self.assertEqual(doc['folder_path'], 'المالية/فواتير')
        self.assertEqual(viewer.get('/api/documents', params={'folder': root['id']}).json()['total'], 1)
        tree = {item['path']: item for item in viewer.get('/api/folders').json()['items']}
        self.assertEqual(tree['المالية']['total_documents'], 1)
        moved = self.admin.patch(f"/api/documents/{doc['id']}/folder", json={'folder_id': root['id']}).json()
        self.assertEqual(moved['folder_path'], 'المالية')
        self.assertEqual(viewer.get(f"/api/documents/{doc['id']}").json()['folder_path'], 'المالية')
        self.assertEqual(viewer.patch(f"/api/documents/{doc['id']}/folder", json={'folder_id': None}).status_code, 403)

    def test_ocr_completion_extracts_metadata_classifies_hierarchically_and_reviewer_edits(self):
        doc = self.upload(self.admin)
        self.assertTrue(self.app.state.ocr.run_next())
        reviewer, viewer = self.user('reviewer1', 'reviewer'), self.user('viewer1', 'viewer')
        fields = viewer.get(f"/api/documents/{doc['id']}/metadata").json()['fields']
        self.assertEqual(fields['date']['normalized'], '2026-03-15')
        self.assertEqual(fields['subject']['value'], 'تمديد مدة المشروع')
        self.assertEqual(fields['reference_number']['source'], 'extracted')
        self.assertEqual(viewer.put(f"/api/documents/{doc['id']}/metadata/subject", json={'value': 'x'}).status_code, 403)
        edited = reviewer.put(f"/api/documents/{doc['id']}/metadata/subject", json={'value': 'تمديد مشروع الصيانة'})
        self.assertEqual(edited.status_code, 200, edited.text)
        self.assertEqual(edited.json()['fields']['subject']['source'], 'human')
        suggestion = viewer.get(f"/api/documents/{doc['id']}/classification").json()['suggestion']
        self.assertEqual(suggestion['basis']['group_id'], 'financial')
        groups = [g['id'] for g in viewer.get('/api/category-groups').json()['items']]
        self.assertEqual(groups, ['administrative', 'financial', 'legal', 'technical'])
        self.assertEqual(len(viewer.get('/api/categories').json()['items']), 8)

    def test_identical_uploads_are_linked_and_a_reviewer_confirms(self):
        first, second = self.upload(self.admin), self.upload(self.admin)
        reviewer = self.user('reviewer1', 'reviewer')
        items = reviewer.get(f"/api/documents/{first['id']}/relations").json()['items']
        self.assertEqual([(i['kind'], i['other_id']) for i in items], [('exact_duplicate', second['id'])])
        response = reviewer.post(f"/api/relations/{items[0]['id']}/review", json={'status': 'confirmed'})
        self.assertEqual(response.json()['status'], 'confirmed')
        self.assertEqual(reviewer.post(f"/api/relations/{items[0]['id']}/review", json={'status': 'maybe'}).status_code, 422)
        stats = self.admin.get('/api/statistics').json()
        self.assertEqual(stats['relations'], {'exact_duplicate': {'confirmed': 1}})


if __name__ == '__main__':
    unittest.main()
