"""Folder knowledge graph (services/graph.py): folder–category links and cross-folder relations."""
from pathlib import Path
import sys
import tempfile
import unittest
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from smartarchive.classification.service import Classifications  # noqa: E402
from smartarchive.persistence.database import Database, now  # noqa: E402
from smartarchive.search.pages import PageTexts  # noqa: E402
from smartarchive.services import graph  # noqa: E402
from smartarchive.services.folders import Folders  # noqa: E402


class GraphTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.db = Database(Path(temp.name) / 'archive.sqlite3')
        self.db.initialize()
        self.classes = Classifications(self.db, models_dir=Path(temp.name) / 'models')
        self.classes.seed()
        self.folders = Folders(self.db)

    def document(self, text: str) -> str:
        doc = str(uuid.uuid4())
        with self.db.connect() as db:
            db.execute('INSERT INTO documents VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                       (doc, 'scan.png', 10, 'image/png', uuid.uuid4().hex * 2, doc + '/o.png', 1, 'ready',
                        'OCR_COMPLETED', '2026-01-01T00:00:00', '2026-01-01T00:00:00'))
            PageTexts._upsert(db, doc, 1, 'ocr', None, None, text)
        self.classes.suggest(doc)
        return doc

    def test_links_count_documents_and_confirmations_and_cross_folder_relations(self):
        finance = self.folders.create('المالية', None, 'admin')['id']
        projects = self.folders.create('المشاريع', None, 'admin')['id']
        invoices = [self.document('فاتورة رقم ١ الإجمالي ٥٠٠ دينار ضريبة المبيعات') for _ in range(3)]
        for doc in invoices:
            self.folders.file(doc, finance, 'admin')
        state = self.classes.get(invoices[0])
        self.classes.decide(invoices[0], 'invoice', '', state['sequence'], 'reviewer')
        stray = self.document('فاتورة رقم ٢ الإجمالي ٧٠٠ دينار')
        self.folders.file(stray, projects, 'admin')
        loose = self.document('محضر اجتماع اللجنة')  # not filed anywhere
        with self.db.connect() as db:
            db.execute('INSERT INTO document_relations (id, source_id, target_id, kind, score, method, evidence, status,'
                       ' created_at) VALUES (?,?,?,?,?,?,?,?,?)',
                       (str(uuid.uuid4()), stray, invoices[1], 'version_of', 0.9, 'test', '{}', 'suggested', now()))
        result = graph.build(self.db)
        link = next(l for l in result['folder_category'] if l['folder_id'] == finance and l['category_id'] == 'invoice')
        self.assertEqual((link['documents'], link['confirmed']), (3, 1))
        self.assertIn({'a': min(finance, projects), 'b': max(finance, projects), 'kind': 'version_of', 'count': 1},
                      result['folder_relations'])
        unfiled = next(f for f in result['folders'] if f['id'] is None)
        self.assertEqual(unfiled['documents'], 1)
        self.assertEqual(result['categories'][0], {'id': 'invoice', 'name': result['categories'][0]['name'], 'documents': 4})
        self.assertIsNotNone(loose)


if __name__ == '__main__':
    unittest.main()
