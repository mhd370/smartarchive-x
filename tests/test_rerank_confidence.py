"""Cross-encoder re-ranking, confidence-aware fusion, visual features and macro-F1 (Sprint 12, ADR 0014/0015)."""
from pathlib import Path
import sys
import tempfile
import unittest
import uuid

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'tools'))
from smartarchive.classification import visual  # noqa: E402
from smartarchive.persistence.database import Database  # noqa: E402
from smartarchive.search import ranked, rerank  # noqa: E402
from smartarchive.search.pages import PageTexts  # noqa: E402


class FakeReranker:
    """Scores a passage by whether it holds the word «توريد»: enough to see the order change."""
    mode = 'replace'

    def score(self, query, passages):
        return [1.0 if 'توريد' in p else 0.0 for p in passages]


class RerankTests(unittest.TestCase):
    def test_passage_is_a_window_around_the_first_match(self):
        text = 'كلمة ' * 300 + 'الهدف هنا ' + 'نص ' * 300
        start = text.index('الهدف')
        window = rerank.passage(text, [(start, start + 5)], size=200)
        self.assertIn('الهدف', window)
        self.assertLessEqual(len(window), 200)
        self.assertEqual(rerank.passage('', []), '')

    def test_reorder_replace_and_fuse(self):
        keys, scores = ['a', 'b', 'c'], [0.1, 0.2, 0.9]
        self.assertEqual(rerank.reorder(keys, scores, 'replace'), ['c', 'b', 'a'])
        fused = rerank.reorder(keys, scores, 'fuse')
        # a: hybrid 1st + model 3rd ties with c: hybrid 3rd + model 1st; the hybrid order breaks the tie
        self.assertEqual(fused, ['a', 'c', 'b'])
        with self.assertRaises(ValueError):
            rerank.reorder(keys, scores, 'other')


class ConfidenceAndRerankSearchTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.db = Database(Path(temp.name) / 'archive.sqlite3')
        self.db.initialize()
        self.texts = PageTexts(self.db)

    def document(self, text: str, confidence: float | None) -> str:
        doc, run = str(uuid.uuid4()), str(uuid.uuid4())
        with self.db.connect() as db:
            db.execute('INSERT INTO documents VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                       (doc, f'{doc[:6]}.png', 10, 'image/png', uuid.uuid4().hex * 2, doc + '/o.png', 1, 'ready',
                        'OCR_COMPLETED', '2026-01-01T00:00:00', '2026-01-01T00:00:00'))
            db.execute("INSERT INTO ocr_runs (id, document_id, status, engine, languages, params, created_by, created_at,"
                       " pages_total) VALUES (?,?,'ready','tesseract','ara','{}','test','2026-01-01T00:00:00',1)",
                       (run, doc))
            db.execute("INSERT INTO page_analyses (run_id, page_no, width, height, dpi_source, metrics, quality_score,"
                       " suggested_route, blank, preprocessing, mean_confidence, review_required, text_length)"
                       " VALUES (?,1,100,100,'test','{}',0.5,'fast',0,'[]',?,0,?)", (run, confidence, len(text)))
            PageTexts._upsert(db, doc, 1, 'ocr', run, None, text)
        return doc

    def test_page_confidence_and_weighting(self):
        low = self.document('عقد توريد مواد المشروع الأول', 0.3)
        high = self.document('عقد توريد مواد المشروع الثاني', 0.95)
        with self.db.connect() as db:
            confidence = ranked.page_confidence(db)
            self.assertAlmostEqual(confidence[(low, 1)], 0.3)
            _, plain = ranked.search(db, 'توريد مواد', components=('grams',))
            _, weighted = ranked.search(db, 'توريد مواد', components=('grams',), confidence=confidence, alpha=1.0)
        self.assertAlmostEqual(weighted[(low, 1)] / plain[(low, 1)], 1.7, places=3)
        self.assertAlmostEqual(weighted[(high, 1)] / plain[(high, 1)], 1.05, places=3)

    def test_search_ranked_with_reranker_and_alpha(self):
        first = self.document('عقد خدمات صيانة المشروع', 0.9)
        second = self.document('عقد توريد للمشروع', 0.9)
        self.texts.confidence_alpha = 0.5
        result = self.texts.search_ranked('عقد المشروع', 10, 0)
        self.assertIn('+conf0.5', result['method'])
        self.texts.reranker = FakeReranker()
        result = self.texts.search_ranked('عقد المشروع', 10, 0)
        self.assertEqual(result['items'][0]['document']['id'], second)
        self.assertTrue(result['method'].endswith('+' + rerank.METHOD))
        self.assertEqual({i['document']['id'] for i in result['items']}, {first, second})
        self.texts.components = ('exact',)
        self.assertEqual(len(self.texts.search_ranked('توريد', 10, 0)['items']), 1)


class VisualAndMacroTests(unittest.TestCase):
    def test_visual_features_see_ruled_tables(self):
        plain, table = Image.new('RGB', (600, 850), 'white'), Image.new('RGB', (600, 850), 'white')
        for image in (plain, table):
            draw = ImageDraw.Draw(image)
            for y in range(80, 780, 30):
                draw.rectangle((80, y, 520, y + 10), fill='black')
        draw = ImageDraw.Draw(table)
        for y in range(200, 600, 40):
            draw.line((40, y, 560, y), fill='black', width=3)
        a, b = visual.features(plain), visual.features(table)
        self.assertEqual(a.shape, b.shape)
        self.assertGreater(b[-4], a[-4])  # horizontal ruling lines

    def test_macro_scores(self):
        from evaluate_synthetic import macro_scores
        rows = [{'type': 'a', 'predicted': 'a'}, {'type': 'a', 'predicted': None}, {'type': 'b', 'predicted': 'a'},
                {'type': 'b', 'predicted': 'b'}]
        result = macro_scores(rows)
        self.assertEqual(result['per_class']['a'], {'precision': 0.5, 'recall': 0.5, 'f1': 0.5, 'documents': 2})
        self.assertEqual(result['per_class']['b']['precision'], 1.0)
        self.assertAlmostEqual(result["macro_f1"], (0.5 + 2 / 3) / 2, places=3)


if __name__ == '__main__':
    unittest.main()
