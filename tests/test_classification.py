"""Keyword classifier, categories and the append-only classification history (Sprint 3)."""
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from smartarchive.classification.classifier import Category, classify
from smartarchive.classification.service import Classifications
from smartarchive.domain.documents import ArchiveError
from smartarchive.persistence.database import Database
from smartarchive.search.pages import PageTexts

CATEGORIES = [Category('decision', 'قرار إداري', ['قرار', 'يقرر', 'المادة', 'يعمل به']),
              Category('letter', 'مراسلة', ['المحترم', 'تحية طيبة', 'وبعد', 'نرجو']),
              Category('financial', 'مالي', ['فاتورة', 'المبلغ', 'دينار'])]

DECISION = 'قرار إداري رقم ١٢\nإن المدير العام، بناءً على الصلاحيات، يقرر ما يلي:\nالمادة الأولى: ...\nالمادة الثانية: يُعمل به من تاريخه.'
LETTER = 'السيد مدير الموارد البشرية المحترم\nتحية طيبة وبعد،\nنرجو التكرم بالموافقة على المرفق.\nمع الشكر'


class ClassifierTests(unittest.TestCase):
    def test_clear_decision_is_suggested_with_evidence(self):
        result = classify(DECISION, 'scan.png', CATEGORIES)
        self.assertEqual(result.category_id, 'decision')
        self.assertGreaterEqual(result.confidence, 0.5)
        words = {hit['keyword'] for hit in result.evidence['decision']}
        self.assertTrue({'قرار', 'يقرر', 'المادة', 'يعمل به'} <= words)
        self.assertTrue(next(h for h in result.evidence['decision'] if h['keyword'] == 'قرار')['heading'])

    def test_letter_and_clitics_match_whole_words_only(self):
        self.assertEqual(classify(LETTER, 'x.pdf', CATEGORIES).category_id, 'letter')
        self.assertEqual(classify('والقرار نافذ بالقرار', '', CATEGORIES).evidence['decision'][0]['count'], 2)
        self.assertNotIn('decision', classify('استقرار الأسعار وتقرير', '', CATEGORIES).evidence)

    def test_abstains_on_no_text_weak_or_ambiguous_evidence(self):
        self.assertEqual(classify('', '', CATEGORIES).reason, 'no_text')
        self.assertEqual(classify('قصيدة عن البحر والمطر', 'poem.png', CATEGORIES).reason, 'no_keywords')
        for text in ('كلام ' * 80 + 'ورد فيه قرار', 'قرار\nنص عادي بلا كلمات أخرى'):
            weak = classify(text, '', CATEGORIES)
            self.assertEqual((weak.category_id, weak.reason), (None, 'weak_evidence'))
        mixed = classify('قرار قرار فاتورة فاتورة', '', CATEGORIES)
        self.assertEqual((mixed.category_id, mixed.reason), (None, 'ambiguous'))

    def test_filename_counts_as_evidence(self):
        self.assertEqual(classify('', 'فاتورة كهرباء.pdf', CATEGORIES).category_id, 'financial')


class ServiceTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.db = Database(Path(temp.name) / 'archive.sqlite3')
        self.db.initialize()
        self.texts = PageTexts(self.db)
        self.service = Classifications(self.db)
        self.service.seed()

    def document(self, text: str, name='scan.png', doc_id='doc-1'):
        with self.db.connect() as db:
            db.execute('INSERT INTO documents VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                       (doc_id, name, 10, 'image/png', 'x' * 64, 'key-' + doc_id, 1, 'ready', 'OCR_COMPLETED',
                        '2026-01-01T00:00:00', '2026-01-01T00:00:00'))
            if text:
                PageTexts._upsert(db, doc_id, 1, 'ocr', None, None, text)
        return doc_id

    def test_default_categories_are_seeded_once(self):
        self.service.seed()
        ids = [item['id'] for item in self.service.categories()]
        self.assertEqual(len(ids), 10)
        self.assertIn('decision', ids)

    def test_suggestion_then_confirmation_then_reclassification_with_reason(self):
        doc = self.document(DECISION)
        record = self.service.suggest(doc)
        self.assertEqual(record['category_id'], 'decision')
        self.assertIsNone(self.service.suggest(doc))  # same text and categories: no duplicate suggestion
        state = self.service.get(doc)
        self.assertEqual((state['state'], state['category_id']), ('suggested', 'decision'))
        self.assertEqual(self.service.queue(10, 0)['total'], 1)
        listed = self.db.list('', None, None, 10, 0)['items'][0]
        self.assertEqual((listed['category_id'], listed['category_state']), ('decision', 'suggested'))

        confirmed = self.service.decide(doc, 'decision', '', state['sequence'], 'reviewer1')
        self.assertEqual((confirmed['state'], confirmed['decision']['actor']), ('confirmed', 'reviewer1'))
        self.assertTrue(confirmed['decision']['basis']['agrees_with_suggestion'])
        self.assertEqual(self.service.queue(10, 0)['total'], 0)
        self.assertEqual(self.service.summary()['confirmed'], 1)

        with self.assertRaises(ArchiveError) as same:
            self.service.decide(doc, 'decision', 'x', confirmed['sequence'], 'r2')
        self.assertEqual(same.exception.code, 'unchanged')
        with self.assertRaises(ArchiveError) as no_reason:
            self.service.decide(doc, 'letter', '', confirmed['sequence'], 'r2')
        self.assertEqual(no_reason.exception.code, 'reason_required')
        with self.assertRaises(ArchiveError) as stale:
            self.service.decide(doc, 'letter', 'سبب', confirmed['sequence'] - 1, 'r2')
        self.assertEqual((stale.exception.code, stale.exception.status), ('stale_classification', 409))
        changed = self.service.decide(doc, 'letter', 'الوثيقة كتاب مرفق بالقرار', confirmed['sequence'], 'r2')
        self.assertEqual((changed['category_id'], changed['decision']['basis']['previous_category_id']), ('letter', 'decision'))
        self.assertEqual(self.db.list('', None, None, 10, 0, category='letter')['total'], 1)
        self.assertEqual(self.db.list('', None, None, 10, 0, category='decision')['total'], 0)
        actions = [e['action'] for e in self.db.events(doc)]
        self.assertEqual(actions, ['classification.confirmed', 'classification.changed'])

    def test_uncertain_documents_need_a_person_and_can_be_classified_without_reason(self):
        doc = self.document('قصيدة عن البحر')
        self.service.suggest(doc)
        state = self.service.get(doc)
        self.assertEqual((state['state'], state['category_id']), ('uncertain', None))
        self.assertEqual(self.db.list('', None, None, 10, 0, category='none')['total'], 1)
        result = self.service.decide(doc, 'report', '', state['sequence'], 'r')
        self.assertEqual(result['state'], 'confirmed')
        self.assertFalse(result['decision']['basis']['agrees_with_suggestion'])

    def test_text_change_produces_a_new_suggestion_and_history_is_append_only(self):
        doc = self.document('قصيدة')
        self.service.suggest(doc)
        with self.db.connect() as db:
            PageTexts._upsert(db, doc, 1, 'review', None, 1, LETTER)
        self.assertEqual(self.service.suggest(doc)['category_id'], 'letter')
        self.assertEqual(len(self.service.get(doc)['history']), 2)
        with self.db.connect() as db, self.assertRaises(sqlite3.IntegrityError):
            db.execute("UPDATE classifications SET category_id='report'")
        with self.db.connect() as db, self.assertRaises(sqlite3.IntegrityError):
            db.execute('DELETE FROM classifications')

    def test_category_admin_validates_and_changes_trigger_reclassification(self):
        with self.assertRaises(ArchiveError):
            self.service.create_category('Bad Id', 'اسم', '', ['كلمة'], 'admin')
        with self.assertRaises(ArchiveError):
            self.service.create_category('memo', 'مذكرة', '', ['  '], 'admin')
        with self.assertRaises(ArchiveError):
            self.service.create_category('memo2', 'قرار إداري', '', ['مذكرة'], 'admin')
        created = self.service.create_category('memo', 'مذكرة داخلية', 'وصف', ['مذكرة', 'مذكرة', 'داخلية'], 'admin')
        self.assertEqual(created['keywords'], ['مذكرة', 'داخلية'])
        doc = self.document('مذكرة داخلية مذكرة بخصوص الدوام')
        self.assertEqual(self.service.suggest(doc)['category_id'], 'memo')
        self.service.update_category('memo', 'admin', active=False)
        self.assertIsNone(self.service.suggest(doc)['category_id'])  # category change: new suggestion
        with self.assertRaises(ArchiveError):
            self.service.decide(doc, 'memo', '', self.service.get(doc)['sequence'], 'r')

    def test_backfill_suggests_for_documents_with_text_only(self):
        self.document(DECISION, doc_id='a')
        self.document('', doc_id='b')
        self.assertEqual(self.service.ensure_suggested(), 1)
        self.assertEqual(self.service.ensure_suggested(), 0)


if __name__ == '__main__':
    unittest.main()
