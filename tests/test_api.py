"""API contract and actual original-byte persistence, using isolated storage."""
from dataclasses import replace
from io import BytesIO
from pathlib import Path
import hashlib
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from fastapi.testclient import TestClient
from PIL import Image
import pymupdf
from smartarchive.api.app import create_app
from smartarchive.config import Settings


class APITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.settings = Settings(storage_dir=Path(self.temp.name))
        self.app = create_app(self.settings)
        self.client = self.enterContext(TestClient(self.app))
        buffer = BytesIO()
        Image.new('RGB', (20, 30), 'white').save(buffer, format='PNG')
        self.png = buffer.getvalue()
        with pymupdf.open() as pdf:
            pdf.new_page()
            pdf.new_page()
            self.pdf = pdf.tobytes()

    def upload(self, data=None, name='وثيقة.png', mime='image/png', client=None):
        return (client or self.client).post('/api/documents', files={
            'file': (name, self.png if data is None else data, mime)})

    def test_upload_metadata_and_original_roundtrip(self):
        response = self.upload()
        self.assertEqual(response.status_code, 201, response.text)
        document = response.json()
        self.assertEqual(document['sha256'], hashlib.sha256(self.png).hexdigest())
        self.assertEqual(document['size_bytes'], len(self.png))
        self.assertEqual(document['mime_type'], 'image/png')
        self.assertEqual(document['status'], 'stored')
        self.assertNotIn('storage_key', document)
        download = self.client.get(f"/api/documents/{document['id']}/download")
        self.assertEqual(download.content, self.png)
        self.assertIn('attachment', download.headers['content-disposition'])
        self.assertEqual(download.headers['x-content-type-options'], 'nosniff')
        status = self.client.get(f"/api/documents/{document['id']}/status").json()
        self.assertFalse(status['ocr_configured'])
        self.assertIsNone(status['extracted_text'])
        self.assertIsNone(status['ocr_confidence'])

    def test_pdf_page_count_inline_preview_and_ranges(self):
        response = self.upload(self.pdf, 'محضر.pdf', 'application/pdf')
        self.assertEqual(response.status_code, 201, response.text)
        document = response.json()
        self.assertEqual(document['page_count'], 2)
        original = self.client.get(f"/api/documents/{document['id']}/content")
        self.assertEqual(original.content, self.pdf)
        self.assertIn('inline', original.headers['content-disposition'])
        ranged = self.client.get(f"/api/documents/{document['id']}/content", headers={'Range': 'bytes=0-9'})
        self.assertEqual(ranged.status_code, 206)
        self.assertEqual(ranged.content, self.pdf[:10])

    def test_image_preview_is_separate_and_original_unchanged(self):
        document = self.upload().json()
        preview = self.client.get(f"/api/documents/{document['id']}/preview")
        self.assertEqual(preview.status_code, 200)
        self.assertEqual(preview.headers['content-type'], 'image/png')
        Image.open(BytesIO(preview.content)).verify()
        self.assertEqual(self.client.get(f"/api/documents/{document['id']}/download").content, self.png)

    def test_pdf_preview_pages_are_bounded_derivatives(self):
        record = self.upload(self.pdf, 'preview.pdf', 'application/pdf').json()
        for page in (1, 2):
            response = self.client.get(f"/api/documents/{record['id']}/preview?page={page}")
            self.assertEqual(response.status_code, 200)
            with Image.open(BytesIO(response.content)) as image:
                self.assertLessEqual(image.width, 1800)
                self.assertLessEqual(image.height, 2400)
        self.assertEqual(self.client.get(f"/api/documents/{record['id']}/preview?page=3").status_code, 404)
        self.assertEqual(self.client.get(f"/api/documents/{record['id']}/preview?page=0").status_code, 422)
        self.assertEqual(self.client.get(f"/api/documents/{record['id']}/download").content, self.pdf)

    def test_supported_image_formats_and_multiframe_tiff(self):
        first, second = Image.new('RGB', (20, 30), 'white'), Image.new('RGB', (20, 30), 'black')
        for format_name, suffix, mime in [('JPEG', 'jpg', 'image/jpeg'), ('WEBP', 'webp', 'image/webp'),
                                          ('TIFF', 'tiff', 'image/tiff')]:
            buffer = BytesIO()
            first.save(buffer, format=format_name, **({'save_all': True, 'append_images': [second]} if format_name == 'TIFF' else {}))
            raw = buffer.getvalue()
            with self.subTest(format=format_name):
                response = self.upload(raw, 'image.' + suffix, mime)
                self.assertEqual(response.status_code, 201, response.text)
                record = response.json()
                self.assertEqual(record['page_count'], 2 if format_name == 'TIFF' else 1)
                self.assertEqual(self.client.get(f"/api/documents/{record['id']}/download").content, raw)

    def test_persistence_after_app_restart_and_real_statistics(self):
        self.upload()
        self.upload(self.pdf, 'record.pdf', 'application/pdf')
        with TestClient(create_app(self.settings)) as restarted:
            stats = restarted.get('/api/statistics').json()
            self.assertEqual(stats['total_documents'], 2)
            self.assertEqual(stats['total_bytes'], len(self.png) + len(self.pdf))
            self.assertEqual(stats['by_status']['stored'], 2)
            self.assertEqual(stats['by_status']['ready'], 0)
            self.assertEqual(restarted.get('/api/documents').json()['total'], 2)

    def test_search_filters_and_pagination(self):
        self.upload(name='إدارة.png')
        self.upload(self.pdf, 'اجتماع.pdf', 'application/pdf')
        self.assertEqual(self.client.get('/api/documents', params={'q': 'إدارة'}).json()['total'], 1)
        self.assertEqual(self.client.get('/api/documents?kind=pdf').json()['total'], 1)
        self.assertEqual(self.client.get('/api/documents?kind=image').json()['total'], 1)
        self.assertEqual(self.client.get('/api/documents?status=ready').json()['total'], 0)
        self.assertEqual(len(self.client.get('/api/documents?limit=1&offset=1').json()['items']), 1)
        self.assertEqual(self.client.get('/api/documents', params={'q': '%'}).json()['total'], 0)
        self.assertEqual(self.client.get('/api/documents', params={'q': "' OR 1=1 --"}).json()['total'], 0)

    def test_duplicate_bytes_have_separate_records_and_no_overwrite(self):
        first, second = self.upload().json(), self.upload().json()
        self.assertNotEqual(first['id'], second['id'])
        self.assertEqual(first['sha256'], second['sha256'])
        self.assertEqual(len(list((self.settings.storage_dir / 'originals').glob('*/original.png'))), 2)

    def test_path_filename_is_metadata_only(self):
        document = self.upload(name='..\\..\\وثيقة.png').json()
        self.assertEqual(document['filename'], 'وثيقة.png')
        files = list((self.settings.storage_dir / 'originals').glob('*/original.png'))
        self.assertEqual(len(files), 1)
        self.assertNotIn('وثيقة', str(files[0]))

    def test_reject_empty_corrupt_and_unsupported(self):
        for data, name, mime, code in [(b'', 'empty.png', 'image/png', 422),
                                      (b'not an image', 'bad.png', 'image/png', 422),
                                      (b'<svg></svg>', 'bad.svg', 'image/svg+xml', 415),
                                      (b'<html></html>', 'bad.pdf', 'application/pdf', 422)]:
            with self.subTest(name=name):
                self.assertEqual(self.upload(data, name, mime).status_code, code)
        self.assertEqual(self.client.get('/api/statistics').json()['total_documents'], 0)
        self.assertEqual(list((self.settings.storage_dir / 'originals').rglob('upload.part')), [])

    def test_mime_and_extension_spoof_rejected(self):
        self.assertEqual(self.upload(self.png, 'fake.pdf', 'application/pdf').status_code, 422)
        self.assertEqual(self.upload(self.png, 'fake.png', 'application/pdf').status_code, 415)

    def test_file_and_chunked_request_limits(self):
        with TestClient(create_app(replace(self.settings, max_upload_bytes=1024))) as small:
            self.assertEqual(self.upload(b'x' * 2048, client=small).status_code, 413)
            body = iter([b'x' * 600_000, b'x' * 600_000])
            response = small.post('/api/documents', content=body,
                                  headers={'Content-Type': 'multipart/form-data; boundary=test'})
            self.assertEqual(response.status_code, 413)

    def test_image_and_pdf_resource_limits(self):
        with TestClient(create_app(replace(self.settings, max_image_pixels=10, max_pages=1))) as bounded:
            self.assertEqual(self.upload(client=bounded).status_code, 422)
            self.assertEqual(self.upload(self.pdf, 'large.pdf', 'application/pdf', client=bounded).status_code, 422)

    def test_password_protected_pdf_rejected(self):
        with pymupdf.open(stream=self.pdf, filetype='pdf') as pdf:
            encrypted = pdf.tobytes(encryption=pymupdf.PDF_ENCRYPT_AES_256,
                                   owner_pw='owner', user_pw='secret')
        self.assertEqual(self.upload(encrypted, 'encrypted.pdf', 'application/pdf').status_code, 422)

    def test_cors_and_untrusted_origin_mutation_blocked(self):
        response = self.client.options('/api/documents', headers={
            'Origin': 'http://localhost:3000', 'Access-Control-Request-Method': 'POST'})
        self.assertEqual(response.headers.get('access-control-allow-origin'), 'http://localhost:3000')
        blocked = self.client.post('/api/documents', files={'file': ('page.png', self.png, 'image/png')},
                                   headers={'Origin': 'https://untrusted.invalid'})
        self.assertEqual(blocked.status_code, 403)
        self.assertEqual(self.client.get('/api/statistics').json()['total_documents'], 0)

    def test_audit_is_ordered_and_database_append_only(self):
        document = self.upload().json()
        self.client.get(f"/api/documents/{document['id']}")
        self.client.get(f"/api/documents/{document['id']}/download")
        events = self.client.get(f"/api/documents/{document['id']}/audit").json()['items']
        self.assertEqual([event['action'] for event in events],
                         ['document.uploaded', 'document.viewed', 'document.downloaded'])
        with self.app.state.documents.db.connect() as db:
            for sql in ('UPDATE audit_events SET actor="changed"', 'DELETE FROM audit_events',
                        'UPDATE documents SET sha256="changed"'):
                with self.assertRaises(sqlite3.IntegrityError):
                    db.execute(sql)

    def test_audit_failure_rolls_back_document_and_retains_original_for_reconciliation(self):
        with self.assertLogs('smartarchive.services.documents', level='ERROR'), patch.object(
                self.app.state.documents.db, '_event', side_effect=sqlite3.OperationalError('synthetic')):
            response = self.upload()
        self.assertEqual(response.status_code, 503)
        self.assertEqual(self.client.get('/api/statistics').json()['total_documents'], 0)
        self.assertEqual(len(list((self.settings.storage_dir / 'originals').glob('*/original.png'))), 1)

    def test_integrity_failure_prevents_serving_changed_original(self):
        document = self.upload().json()
        path = next((self.settings.storage_dir / 'originals').glob('*/original.png'))
        path.write_bytes(b'corrupted')
        self.assertEqual(self.client.get(f"/api/documents/{document['id']}/download").status_code, 409)

    def test_invalid_queries_missing_file_and_unknown_ids(self):
        for url in ('/api/documents?limit=0', '/api/documents?offset=-1', '/api/documents?status=bogus',
                    '/api/documents/not-a-uuid'):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 422)
        self.assertEqual(self.client.post('/api/documents').status_code, 422)
        self.assertEqual(self.client.get('/api/documents/00000000-0000-0000-0000-000000000001').status_code, 404)


if __name__ == '__main__':
    unittest.main()
