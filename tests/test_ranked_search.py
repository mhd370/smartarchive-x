"""Ranked search (hybrid-bm25-v1): light stemming, BM25 over stems and trigrams, OCR-error tolerance."""
from pathlib import Path
import sys
import tempfile
import unittest
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from smartarchive.persistence.database import Database  # noqa: E402
from smartarchive.search import ranked  # noqa: E402
from smartarchive.search.pages import PageTexts  # noqa: E402

LETTER = 'الموضوع: تمديد مدة مشروع صيانة المباني الحكومية\nنرجو الموافقة على تمديد المشروع لمدة تسعين يوما'
INVOICE = 'فاتورة شركة النخيل للمقاولات\nالإجمالي: ٥,٤١٥ دينار\nتوريد أنابيب مياه وإسمنت'
REPORT = 'تقرير فني حول سير العمل في مشروع تجهيز قاعة الاجتماعات\nبلغت نسبة الإنجاز ٨٨٪'


class StemTests(unittest.TestCase):
    def test_light_stemming_joins_clitic_and_plural_forms(self):
        self.assertEqual(ranked.stem('والمشروع'), ranked.stem('مشروع'))
        self.assertEqual(ranked.stem('بالمشروع'), 'مشروع')
        self.assertEqual(ranked.stem('مشروعات'), 'مشروع')
        self.assertEqual(ranked.stem('2024'), '2024')  # numbers and Latin words are not stemmed
        self.assertEqual(ranked.stem('ولد'), 'ولد')  # never below three letters
        self.assertEqual(ranked.trigrams('خدمات'), ['خدم', 'دما', 'مات'])


class RankedSearchTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.db = Database(Path(temp.name) / 'archive.sqlite3')
        self.db.initialize()
        self.texts = PageTexts(self.db)
        self.ids = {name: self.document(name, text) for name, text in
                    (('letter.png', LETTER), ('invoice.png', INVOICE), ('report.png', REPORT))}

    def document(self, name: str, text: str) -> str:
        doc = str(uuid.uuid4())
        with self.db.connect() as db:
            db.execute('INSERT INTO documents VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                       (doc, name, 10, 'image/png', uuid.uuid4().hex * 2, doc + '/original.png', 1, 'ready',
                        'OCR_COMPLETED', '2026-01-01T00:00:00', '2026-01-01T00:00:00'))
            PageTexts._upsert(db, doc, 1, 'ocr', None, None, text)
        return doc

    def test_ranks_relevant_document_first_and_any_word_may_match(self):
        result = self.texts.search_ranked('مشاريع صيانة المباني', 10, 0)
        self.assertEqual(result['mode'], 'ranked')
        self.assertEqual(result['items'][0]['document']['id'], self.ids['letter.png'])
        self.assertTrue(result['items'][0]['pages'][0]['snippets'])
        # The exact mode needs every term on the page; ranked mode does not.
        self.assertEqual(self.texts.search('مشاريع صيانة المباني', 10, 0)['total'], 0)

    def test_tolerates_an_ocr_misread_word(self):
        result = self.texts.search_ranked('النخيل للمقاولات', 10, 0)
        self.assertEqual(result['items'][0]['document']['id'], self.ids['invoice.png'])
        misread = self.texts.search_ranked('النخيڶ للمقاولاث', 10, 0)  # two misread letters
        self.assertEqual(misread['items'][0]['document']['id'], self.ids['invoice.png'])

    def test_corrections_reindex_and_category_filter_applies(self):
        with self.db.connect() as db:
            PageTexts._upsert(db, self.ids['report.png'], 1, 'review', None, 1, 'محضر اجتماع لجنة المشتريات')
        old_text = self.texts.search_ranked('تجهيز قاعة', 10, 0)
        self.assertNotIn(self.ids['report.png'], [item['document']['id'] for item in old_text['items']])
        self.assertEqual(self.texts.search_ranked('المشتريات', 10, 0)['items'][0]['document']['id'],
                         self.ids['report.png'])
        only = self.texts.search_ranked('مشروع', 10, 0, allowed={self.ids['invoice.png']})
        self.assertTrue(all(item['document']['id'] == self.ids['invoice.png'] for item in only['items']))

    def test_backfill_indexes_pages_from_before_the_feature(self):
        with self.db.connect() as db:
            db.execute('DELETE FROM page_terms')
            db.execute('DELETE FROM page_trigrams')
        def count():
            with self.db.connect() as db:
                return db.execute('SELECT COUNT(*) FROM page_terms').fetchone()[0]
        self.assertEqual(count(), 0)
        self.texts.ensure_indexed()
        self.assertEqual(count(), 3)
        self.assertEqual(self.texts.search_ranked('النخيل', 10, 0)['items'][0]['document']['id'],
                         self.ids['invoice.png'])
        self.assertEqual(self.texts.search_ranked('   ', 10, 0)['items'], [])


if __name__ == '__main__':
    unittest.main()
