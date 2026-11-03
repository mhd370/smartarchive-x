"""Controlled reclassification (reclass-delta-v1): proposals only on strong new evidence, never automatic."""
from pathlib import Path
import sys
import tempfile
import unittest
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from smartarchive.classification import reclassify  # noqa: E402
from smartarchive.classification.service import Classifications  # noqa: E402
from smartarchive.domain.documents import ArchiveError  # noqa: E402
from smartarchive.persistence.database import Database  # noqa: E402
from smartarchive.search.pages import PageTexts  # noqa: E402

INVOICE = 'فاتورة رقم ٤٥ الإجمالي ٩٠٠ دينار ضريبة المبيعات سعر الوحدة الكمية فاتورة توريد'


class RuleTests(unittest.TestCase):
    def test_gates(self):
        strong = {'invoice': 0.8, 'minutes': 0.1, 'report': 0.1}
        found = reclassify.proposal('minutes', 'invoice', 'suggested', strong)
        self.assertEqual((found['to_category_id'], found['delta']), ('invoice', 0.7))
        self.assertIsNone(reclassify.proposal('invoice', 'invoice', 'suggested', strong))  # agrees
        self.assertIsNone(reclassify.proposal('minutes', 'invoice', 'ambiguous', strong))  # classifier abstained
        self.assertIsNone(reclassify.proposal('minutes', 'invoice', 'suggested', {'invoice': 0.55, 'minutes': 0.45}))
        self.assertIsNone(reclassify.proposal('minutes', 'invoice', 'suggested', {'invoice': 0.62, 'minutes': 0.38}))
        # Raw keyword scores are normalized: 8 vs 2 is a share of 0.8 vs 0.2.
        self.assertIsNotNone(reclassify.proposal('minutes', 'invoice', 'suggested', {'invoice': 8, 'minutes': 2}))
        self.assertEqual(reclassify.shares({}), {})


class ServiceTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.db = Database(Path(temp.name) / 'archive.sqlite3')
        self.db.initialize()
        self.classes = Classifications(self.db, models_dir=Path(temp.name) / 'models')
        self.classes.seed()
        self.doc = str(uuid.uuid4())
        with self.db.connect() as db:
            db.execute('INSERT INTO documents VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                       (self.doc, 'scan.png', 10, 'image/png', uuid.uuid4().hex * 2, self.doc + '/o.png', 2, 'ready',
                        'OCR_COMPLETED', '2026-01-01T00:00:00', '2026-01-01T00:00:00'))
            PageTexts._upsert(db, self.doc, 1, 'ocr', None, None, INVOICE)

    def page(self, page_no: int, text: str):
        with self.db.connect() as db:
            PageTexts._upsert(db, self.doc, page_no, 'review', None, None, text)
        self.classes.suggest(self.doc)

    def test_proposal_needs_new_evidence_and_a_person(self):
        self.assertEqual(self.classes.suggest(self.doc)['category_id'], 'invoice')
        state = self.classes.get(self.doc)
        self.classes.decide(self.doc, 'minutes', '', state['sequence'], 'reviewer')  # a (wrong) human decision
        self.classes.suggest(self.doc, force=True)  # same evidence again: the person already decided against it
        self.assertIsNone(self.classes.get(self.doc)['reclassification'])

        self.page(2, INVOICE + ' المجموع النهائي')  # new evidence: a corrected second page
        state = self.classes.get(self.doc)
        proposal = state['reclassification']
        self.assertEqual((state['category_id'], state['state']), ('minutes', 'confirmed'))  # never automatic
        self.assertEqual((proposal['from_category_id'], proposal['to_category_id']), ('minutes', 'invoice'))
        queue = self.classes.reclassification_queue(10, 0)
        self.assertEqual([item['document_id'] for item in queue['items']], [self.doc])

        with self.assertRaises(ArchiveError):
            self.classes.dismiss(self.doc, 'not-the-suggestion', '', 'reviewer')
        self.classes.dismiss(self.doc, proposal['suggestion_id'], 'الملف محضر مرفقة به فاتورة', 'reviewer')
        self.assertIsNone(self.classes.get(self.doc)['reclassification'])
        self.assertEqual(self.classes.reclassification_queue(10, 0)['total'], 0)

        self.page(2, INVOICE + ' فاتورة نهائية مصححة')  # newer evidence reopens it
        state = self.classes.get(self.doc)
        self.assertIsNotNone(state['reclassification'])
        with self.assertRaises(ArchiveError):  # accepting is a reclassification: a reason is required
            self.classes.decide(self.doc, 'invoice', '', state['sequence'], 'reviewer')
        state = self.classes.decide(self.doc, 'invoice', 'قبول اقتراح إعادة التصنيف', state['sequence'], 'reviewer')
        self.assertEqual((state['category_id'], state['reclassification']), ('invoice', None))
        self.assertTrue(state['decision']['basis']['accepted_reclassification'])
        with self.db.connect() as db:
            actions = [row[0] for row in db.execute('SELECT action FROM audit_events WHERE document_id=?'
                                                    ' ORDER BY rowid', (self.doc,))]
            self.assertIn('reclassification.dismissed', actions)
            with self.assertRaises(Exception):
                db.execute('DELETE FROM reclassification_reviews')


if __name__ == '__main__':
    unittest.main()
