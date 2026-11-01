"""Arabic normalization, page text index, human review revisions and text search (Sprint 2)."""
from pathlib import Path
import json
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from smartarchive.domain.documents import ArchiveError
from smartarchive.persistence.database import Database, now
from smartarchive.search.arabic import find_spans, normalize, parse_query, snippets
from smartarchive.search.pages import PageTexts


class NormalizationTests(unittest.TestCase):
    def test_hamza_taa_marbuta_yaa_diacritics_tatweel_and_digits(self):
        self.assertEqual(normalize('أحمد إبراهيم آمنة'), 'احمد ابراهيم امنه')
        self.assertEqual(normalize('مُدِيـــرِيَّة'), 'مديريه')
        self.assertEqual(normalize('مسؤول شؤون رئيس على'), 'مسوول شوون رييس علي')
        self.assertEqual(normalize('رقم ١٢٣ و ۴۵۶'), 'رقم 123 و 456')
        self.assertEqual(normalize('Report-2024 / Final'), 'report 2024 final')

    def test_query_keeps_quoted_phrases_and_drops_duplicates(self):
        self.assertEqual(parse_query('"القرار الإداري" قرار  قرار'), ['القرار الاداري', 'قرار'])
        self.assertEqual(parse_query('  ؟؟ '), [])

    def test_spans_point_into_the_original_text_including_trailing_marks(self):
        text = 'وبالقرارِ الإداريّ رقم ١٢٣'
        spans = find_spans(text, parse_query('قرار اداري 123'))
        self.assertEqual([text[a:b] for a, b in spans], ['قرارِ', 'إداريّ', '١٢٣'])

    def test_snippets_mark_matches_and_do_not_cut_words(self):
        text = 'مقدمة طويلة جدا ' * 10 + 'نص القرار المهم هنا ' + 'خاتمة طويلة ' * 10
        parts = snippets(text, find_spans(text, ['قرار']), radius=20)[0]
        self.assertTrue(any(p['match'] and p['text'] == 'قرار' for p in parts))
        joined = ''.join(p['text'] for p in parts).strip('… ')
        self.assertIn(joined.split()[0], {'مقدمة', 'طويلة', 'جدا'})


class PageTextTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.db = Database(Path(temp.name) / 'archive.sqlite3')
        self.db.initialize()
        self.texts = PageTexts(self.db)

    def document(self, name='قرار.pdf', pages=2, created='2026-01-01T00:00:00'):
        doc_id = f'doc-{name}'
        with self.db.connect() as db:
            db.execute('INSERT INTO documents VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                       (doc_id, name, 10, 'application/pdf', 'x' * 64, 'key-' + name, pages, 'ready',
                        'OCR_COMPLETED', created, created))
        return self.db.get(doc_id)

    def run_ocr(self, document, pages: dict[int, tuple[list[str], float]], created='2026-01-02T00:00:00'):
        """Insert a completed run; pages maps page_no -> (lines, confidence)."""
        run_id = f"run-{document['id']}-{created}"
        review = any(conf < 0.6 for _, conf in pages.values())
        with self.db.connect() as db:
            db.execute("INSERT INTO ocr_runs(id,document_id,status,engine,languages,params,created_by,created_at,"
                       "pages_total,pages_done,review_required) VALUES (?,?,'ready','fake','ara','{}','admin',?,?,?,?)",
                       (run_id, document['id'], created, len(pages), len(pages), int(review)))
            for page_no, (lines, conf) in pages.items():
                db.execute('INSERT INTO page_analyses VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                           (run_id, page_no, 100, 100, 300, 'metadata', '{}', 0.8, 'fast', 0, '[]', conf,
                            int(conf < 0.6), sum(map(len, lines))))
                for index, line in enumerate(lines):
                    db.execute('INSERT INTO ocr_lines VALUES (?,?,?,?,?,?,?,?,?,?)',
                               (run_id, page_no, index + 1, line, conf, 0, 0, 1, 1, '[]'))
            self.texts.index_run(db, run_id, document['id'])
            reason = 'REVIEW_REQUIRED' if review else 'OCR_COMPLETED'
            self.db.set_status(db, document['id'], 'ready', reason)
        return run_id

    def test_search_finds_normalized_arabic_with_clitics_and_groups_pages(self):
        doc = self.document()
        self.run_ocr(doc, {1: (['بناءً على القرار الإداريّ رقم ١٢'], 0.9), 2: (['ملحق: وبالقرار المذكور'], 0.9)})
        other = self.document('تقرير.pdf', created='2026-02-01T00:00:00')
        self.run_ocr(other, {1: (['تقرير سنوي'], 0.9)})
        result = self.texts.search('قرار اداري', 10, 0)
        self.assertEqual(result['total'], 1)
        item = result['items'][0]
        self.assertEqual((item['document']['id'], item['matched_pages']), (doc['id'], 1))
        self.assertNotIn('storage_key', item['document'])
        marked = [p['text'] for p in item['pages'][0]['snippets'][0] if p['match']]
        self.assertEqual(marked, ['قرار', 'إداريّ'])  # highlighted in the original text, marks included
        self.assertEqual(self.texts.search('قرار', 10, 0)['items'][0]['matched_pages'], 2)
        self.assertEqual(self.texts.search('12', 10, 0)['total'], 1)
        self.assertEqual(self.texts.search('غير موجود', 10, 0)['total'], 0)

    def test_filename_matches_are_included_and_ranked_below_text_hits(self):
        named = self.document('قرار تعيين.png', pages=1, created='2026-03-01T00:00:00')
        self.run_ocr(named, {1: (['لا شيء هنا'], 0.9)})
        texty = self.document('ملف.pdf', pages=1)
        self.run_ocr(texty, {1: (['قرار قرار قرار قرار قرار قرار'], 0.9)})
        items = self.texts.search('قرار', 10, 0)['items']
        self.assertEqual([i['document']['id'] for i in items], [texty['id'], named['id']])
        self.assertTrue(items[1]['filename_match'])
        self.assertEqual(items[1]['pages'], [])

    def test_like_wildcards_in_queries_are_literal(self):
        doc = self.document(pages=1)
        self.run_ocr(doc, {1: (['نسبة 50 بالمئة'], 0.9)})
        self.assertEqual(self.texts.search('%', 10, 0)['total'], 0)
        self.assertEqual(self.texts.search('_', 10, 0)['total'], 0)
        self.assertEqual(self.texts.search('60%', 10, 0)['total'], 0)  # punctuation is ignored, not a wildcard

    def test_review_creates_versions_updates_search_queue_status_and_audit(self):
        doc = self.document()
        self.run_ocr(doc, {1: (['قرار ادري'], 0.4), 2: (['صفحة واضحة'], 0.95)})
        doc = self.db.get(doc['id'])
        queue = self.texts.queue(10, 0)
        self.assertEqual([(i['document_id'], i['page_no']) for i in queue['items']], [(doc['id'], 1)])
        page = self.texts.page(doc, 1)
        self.assertEqual((page['source'], page['version'], page['review_required']), ('ocr', 0, True))

        updated = self.texts.revise(doc, 1, '  قرار إداري  ', 0, 'تصحيح كلمة', 'reviewer1')
        self.assertEqual((updated['source'], updated['version'], updated['text']), ('review', 1, 'قرار إداري'))
        self.assertEqual(updated['revisions'][0]['author'], 'reviewer1')
        self.assertEqual(self.texts.queue(10, 0)['total'], 0)
        self.assertEqual(self.db.get(doc['id'])['status_reason'], 'REVIEW_COMPLETED')
        self.assertEqual(self.texts.search('اداري', 10, 0)['items'][0]['pages'][0]['source'], 'review')
        self.assertEqual(self.texts.search('ادري', 10, 0)['total'], 0)  # the OCR error is no longer searchable
        event = [e for e in self.db.events(doc['id']) if e['action'] == 'page.reviewed'][0]
        self.assertEqual((event['actor'], event['details']['version'], event['details']['note']), ('reviewer1', 1, 'تصحيح كلمة'))

        with self.assertRaises(ArchiveError) as stale:
            self.texts.revise(doc, 1, 'نص آخر', 0, '', 'reviewer2')
        self.assertEqual((stale.exception.code, stale.exception.status), ('stale_version', 409))
        with self.assertRaises(ArchiveError) as same:
            self.texts.revise(doc, 1, 'قرار إداري', 1, '', 'reviewer2')
        self.assertEqual(same.exception.code, 'unchanged')
        second = self.texts.revise(doc, 1, 'قرار إداري رقم 5', 1, '', 'reviewer2')
        self.assertEqual([r['version'] for r in second['revisions']], [2, 1])
        self.assertEqual(self.texts.revision_text(doc['id'], 1, 1)['text'], 'قرار إداري')

    def test_revisions_are_append_only(self):
        doc = self.document(pages=1)
        self.run_ocr(doc, {1: (['نص'], 0.4)})
        self.texts.revise(self.db.get(doc['id']), 1, 'نص مصحح', 0, '', 'r')
        with self.db.connect() as db, self.assertRaises(sqlite3.IntegrityError):
            db.execute("UPDATE page_revisions SET text='x'")
        with self.db.connect() as db, self.assertRaises(sqlite3.IntegrityError):
            db.execute('DELETE FROM page_revisions')

    def test_new_ocr_run_keeps_human_corrections_and_refreshes_other_pages(self):
        doc = self.document()
        self.run_ocr(doc, {1: (['نص قديم'], 0.4), 2: (['نص قديم'], 0.9)})
        self.texts.revise(self.db.get(doc['id']), 1, 'نص مصحح يدويا', 0, '', 'r')
        self.run_ocr(doc, {1: (['نص جديد'], 0.4), 2: (['نص جديد'], 0.9)}, created='2026-01-05T00:00:00')
        self.assertEqual(self.texts.page(doc, 1)['text'], 'نص مصحح يدويا')
        self.assertEqual(self.texts.page(doc, 2)['text'], 'نص جديد')
        self.assertEqual(self.texts.queue(10, 0)['total'], 0)

    def test_review_is_refused_when_not_ready_or_page_invalid_or_too_long(self):
        doc = self.document(pages=1)
        self.run_ocr(doc, {1: (['نص'], 0.4)})
        with self.assertRaises(ArchiveError) as bad_page:
            self.texts.revise(self.db.get(doc['id']), 2, 'x', 0, '', 'r')
        self.assertEqual(bad_page.exception.status, 404)
        with self.assertRaises(ArchiveError) as long_text:
            self.texts.revise(self.db.get(doc['id']), 1, 'x' * 100_001, 0, '', 'r')
        self.assertEqual(long_text.exception.status, 422)
        with self.db.connect() as db:
            self.db.set_status(db, doc['id'], 'processing', 'OCR_RUNNING')
        with self.assertRaises(ArchiveError) as busy:
            self.texts.revise(self.db.get(doc['id']), 1, 'نص جديد', 0, '', 'r')
        self.assertEqual(busy.exception.code, 'not_ready')

    def test_backfill_indexes_runs_completed_before_this_feature(self):
        doc = self.document(pages=1)
        run_id = self.run_ocr(doc, {1: (['أرشيف قديم'], 0.9)})
        with self.db.connect() as db:
            db.execute('DELETE FROM page_texts')
        self.assertEqual(self.texts.search('ارشيف', 10, 0)['total'], 0)
        self.assertEqual(self.texts.ensure_indexed(), 1)
        self.assertEqual(self.texts.ensure_indexed(), 0)
        self.assertEqual(self.texts.page(doc, 1)['run_id'], run_id)
        self.assertEqual(self.texts.search('ارشيف', 10, 0)['total'], 1)


if __name__ == '__main__':
    unittest.main()
