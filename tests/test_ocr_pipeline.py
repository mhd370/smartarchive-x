"""Persisted OCR runs through the API: queue, process, provenance, review flags (Task 006)."""
from io import BytesIO
from pathlib import Path
import sys
import tempfile
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from fastapi.testclient import TestClient
from PIL import Image

from smartarchive.api.app import create_app
from smartarchive.config import Settings, find_tesseract
from smartarchive.processing.ocr import Line, Word
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_processing import WORDS, text_page  # noqa: E402

ADMIN = {'username': 'admin', 'password': 'admin-password-1', 'display_name': 'مدير'}


class FakeEngine:
    """Deterministic engine: one line per call with configurable confidence."""
    name, languages, missing = 'fake', 'ara+eng', []

    def __init__(self, confidence=0.93, fail=False):
        self.confidence, self.fail, self.calls = confidence, fail, 0

    def version(self):
        return '1.0-test'

    def recognize(self, image):
        self.calls += 1
        if self.fail:
            raise RuntimeError('synthetic engine failure')
        words = [Word('قرار', self.confidence, (100, 100, 300, 160)), Word('إداري', self.confidence, (320, 100, 600, 160))]
        return [Line('قرار إداري', self.confidence, (100, 100, 600, 160), words)]


def encoded(image: Image.Image, fmt='PNG') -> bytes:
    buffer = BytesIO()
    image.save(buffer, format=fmt, dpi=(300, 300))
    return buffer.getvalue()


class PipelineTests(unittest.TestCase):
    def make(self, engine=None, factory=None, **overrides):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        settings = Settings(storage_dir=Path(temp.name), ocr_worker=False, **overrides)
        app = create_app(settings, engine_factory=factory or ((lambda: engine) if engine else None))
        client = self.enterContext(TestClient(app))
        self.assertEqual(client.post('/api/auth/setup', json=ADMIN).status_code, 201)
        return app, client

    def upload(self, client, image=None, name='قرار.png'):
        response = client.post('/api/documents', files={'file': (name, encoded(image or text_page()), 'image/png')})
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def test_upload_queues_then_run_records_quality_text_boxes_and_audit(self):
        engine = FakeEngine()
        app, client = self.make(engine)
        document = self.upload(client)
        self.assertEqual((document['status'], document['status_reason']), ('queued', 'OCR_QUEUED'))
        self.assertTrue(app.state.ocr.run_next())
        self.assertFalse(app.state.ocr.run_next())
        status = client.get(f"/api/documents/{document['id']}/status").json()
        self.assertEqual((status['status'], status['reason']), ('ready', 'OCR_COMPLETED'))
        self.assertEqual(status['extracted_text'], 'قرار إداري')
        self.assertAlmostEqual(status['ocr_confidence'], 0.93)
        self.assertFalse(status['review_required'])
        summary = client.get(f"/api/documents/{document['id']}/ocr").json()
        self.assertEqual(summary['run']['engine'], 'fake')
        self.assertEqual(summary['run']['created_by'], 'admin')
        self.assertEqual(summary['run']['params']['trigger'], 'upload')
        page = summary['pages'][0]
        self.assertEqual((page['page_no'], page['dpi'], page['dpi_source']), (1, 300.0, 'metadata'))
        self.assertTrue(0 <= page['quality_score'] <= 1)
        self.assertIn('sharpness', page['metrics'])
        steps = {s['step']: s for s in page['preprocessing']}
        self.assertEqual([s['step'] for s in page['preprocessing']][-4:], ['binarization', 'layout', 'ocr_paths', 'regions'])
        self.assertEqual(steps['layout']['method'], 'none')  # the fake engine reads no blocks
        self.assertEqual(steps['ocr_paths']['chosen'], 'standard')  # same text on every path: the first wins
        self.assertEqual(set(steps['ocr_paths']['tried']), {'standard', 'binarized', 'upscaled'})
        lines = client.get(f"/api/documents/{document['id']}/ocr/pages/1").json()['lines']
        self.assertEqual(lines[0]['text'], 'قرار إداري')
        x0, y0, x1, y1 = lines[0]['box']
        self.assertTrue(0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1)
        self.assertAlmostEqual(x0, 100 / 1654, places=3)
        actions = [e['action'] for e in client.get(f"/api/documents/{document['id']}/audit").json()['items']]
        self.assertEqual(actions, ['document.uploaded', 'ocr.queued', 'ocr.started', 'ocr.completed'])
        events = client.get(f"/api/documents/{document['id']}/audit").json()['items']
        self.assertEqual(events[2]['actor'], 'system:ocr')

    def test_low_confidence_marks_review_required(self):
        app, client = self.make(FakeEngine(confidence=0.4))
        document = self.upload(client)
        app.state.ocr.run_next()
        status = client.get(f"/api/documents/{document['id']}/status").json()
        self.assertEqual((status['status'], status['reason'], status['review_required']), ('ready', 'REVIEW_REQUIRED', True))
        page = client.get(f"/api/documents/{document['id']}/ocr").json()['pages'][0]
        self.assertTrue(page['review_required'])

    def test_blank_page_skips_engine_and_flags_review(self):
        engine = FakeEngine()
        app, client = self.make(engine)
        document = self.upload(client, Image.new('RGB', (1654, 2339), 'white'))
        app.state.ocr.run_next()
        self.assertEqual(engine.calls, 0)
        page = client.get(f"/api/documents/{document['id']}/ocr").json()['pages'][0]
        self.assertTrue(page['blank'])
        self.assertEqual(client.get(f"/api/documents/{document['id']}/status").json()['reason'], 'REVIEW_REQUIRED')

    def test_engine_failure_is_recorded_not_hidden(self):
        app, client = self.make(FakeEngine(fail=True))
        document = self.upload(client)
        with self.assertLogs('smartarchive.processing.pipeline', level='ERROR'):
            app.state.ocr.run_next()
        status = client.get(f"/api/documents/{document['id']}/status").json()
        self.assertEqual((status['status'], status['reason']), ('failed', 'OCR_FAILED'))
        self.assertIsNone(status['extracted_text'])
        self.assertIn('synthetic engine failure', status['latest_run']['error'])
        self.assertEqual(client.get(f"/api/documents/{document['id']}/ocr/pages/1").status_code, 404)

    def test_manual_rerun_creates_new_version_and_blocks_duplicates(self):
        app, client = self.make(FakeEngine(), ocr_auto=False)
        document = self.upload(client)
        self.assertEqual(document['status_reason'], 'OCR_NOT_REQUESTED')
        first = client.post(f"/api/documents/{document['id']}/ocr")
        self.assertEqual(first.status_code, 201)
        self.assertEqual(client.post(f"/api/documents/{document['id']}/ocr").status_code, 409)
        app.state.ocr.run_next()
        second = client.post(f"/api/documents/{document['id']}/ocr").json()
        app.state.ocr.run_next()
        runs = client.get(f"/api/documents/{document['id']}/ocr").json()['runs']
        self.assertEqual({run['id'] for run in runs}, {first.json()['id'], second['id']})
        old = client.get(f"/api/documents/{document['id']}/ocr/pages/1", params={'run_id': first.json()['id']})
        self.assertEqual(old.status_code, 200)

    def test_viewer_cannot_start_ocr_and_interrupted_runs_are_requeued(self):
        app, client = self.make(FakeEngine(), ocr_auto=False)
        document = self.upload(client)
        client.post('/api/users', json={'username': 'viewer1', 'password': 'viewer-pass-1', 'display_name': 'v', 'role': 'viewer'})
        viewer = self.enterContext(TestClient(app))
        viewer.post('/api/auth/login', json={'username': 'viewer1', 'password': 'viewer-pass-1'})
        self.assertEqual(viewer.post(f"/api/documents/{document['id']}/ocr").status_code, 403)
        client.post(f"/api/documents/{document['id']}/ocr")
        app.state.ocr._claim()  # simulate a crash after claiming
        app.state.ocr.recover()
        self.assertEqual(client.get(f"/api/documents/{document['id']}").json()['status_reason'], 'OCR_REQUEUED')
        self.assertTrue(app.state.ocr.run_next())
        self.assertEqual(client.get(f"/api/documents/{document['id']}").json()['status'], 'ready')

    def test_unconfigured_engine_is_reported_honestly(self):
        def missing():
            raise RuntimeError('none of the OCR languages are installed')
        app, client = self.make(factory=missing)
        self.assertIn('none of the OCR languages', app.state.ocr.info()['error'])
        document = self.upload(client)
        self.assertEqual((document['status'], document['status_reason']), ('stored', 'OCR_NOT_CONFIGURED'))
        self.assertEqual(client.post(f"/api/documents/{document['id']}/ocr").status_code, 503)
        self.assertFalse(client.get('/api/health').json()['ocr_configured'])

    @unittest.skipUnless(find_tesseract(), 'Tesseract is not installed')
    def test_background_worker_with_real_tesseract(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        app = create_app(Settings(storage_dir=Path(temp.name), ocr_languages='eng'))
        with TestClient(app) as client:
            client.post('/api/auth/setup', json=ADMIN)
            document = self.upload(client, text_page(size=40).crop((0, 0, 1654, 900)), 'english.png')
            deadline = time.time() + 120
            while time.time() < deadline:
                status = client.get(f"/api/documents/{document['id']}/status").json()
                if status['status'] in ('ready', 'failed'):
                    break
                time.sleep(0.5)
            self.assertEqual(status['status'], 'ready', status)
            self.assertGreaterEqual(sum(word in status['extracted_text'].lower() for word in WORDS), 5)
            self.assertEqual(status['latest_run']['engine'], 'tesseract')
            self.assertEqual(status['latest_run']['languages'], 'eng')


if __name__ == '__main__':
    unittest.main()
