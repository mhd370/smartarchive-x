"""Dense retrieval (search/semantic.py) with a stand-in encoder: incremental vectors, ranking, fusion."""
from pathlib import Path
import sys
import tempfile
import unittest
import uuid

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from smartarchive.persistence.database import Database  # noqa: E402
from smartarchive.search import ranked, semantic  # noqa: E402
from smartarchive.search.pages import PageTexts  # noqa: E402

# A tiny "meaning" space: synonyms share a dimension, which is what a real embedding model provides.
CONCEPTS = {'عقد': 0, 'اتفاقيه': 0, 'شراء': 1, 'توريد': 1, 'اجتماع': 2, 'محضر': 2, 'لجنه': 2}


class ConceptEncoder:
    name = 'test-concepts'
    min_similarity = 0.5  # the threshold belongs to the model; a real e5 model uses semantic.MIN_SIMILARITY

    def __init__(self):
        self.calls = 0

    def encode(self, texts, kind='passage', batch=16):
        self.calls += len(texts)
        out = np.zeros((len(texts), 4), np.float32)
        for i, text in enumerate(texts):
            for word in text.split():
                out[i, CONCEPTS.get(word, 3)] += 1.0
            out[i] /= max(np.linalg.norm(out[i]), 1e-9)
        return out


class SemanticTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.db = Database(Path(temp.name) / 'archive.sqlite3')
        self.db.initialize()
        self.encoder = ConceptEncoder()
        self.index = semantic.SemanticIndex(self.encoder)
        self.texts = PageTexts(self.db)
        self.texts.semantic = self.index

    def page(self, text: str, doc: str | None = None) -> str:
        doc = doc or str(uuid.uuid4())
        with self.db.connect() as db:
            db.execute('INSERT OR IGNORE INTO documents VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                       (doc, 'scan.png', 10, 'image/png', uuid.uuid4().hex * 2, doc + '/o.png', 1, 'ready',
                        'OCR_COMPLETED', '2026-01-01T00:00:00', '2026-01-01T00:00:00'))
            PageTexts._upsert(db, doc, 1, 'ocr', None, None, text)
        return doc

    def test_vectors_follow_the_text_and_find_other_words_for_the_same_thing(self):
        supply = self.page('اتفاقية توريد مواد مكتبية')
        minutes = self.page('محضر اجتماع اللجنة')
        with self.db.connect() as db:
            self.assertEqual(self.index.refresh(db), 2)
            self.assertEqual(self.index.refresh(db), 0)  # nothing changed: nothing embedded again
            self.assertEqual(self.index.search(db, 'عقد شراء'), [(supply, 1)])  # no shared word
        self.page('محضر اجتماع لجنة المشتريات المعدل', minutes)  # a corrected page gets new vectors
        with self.db.connect() as db:
            self.assertEqual(self.index.refresh(db), 1)
        result = self.texts.search_ranked('عقد شراء', 10, 0)
        self.assertEqual(result['method'], ranked.METHOD_DENSE)
        self.assertEqual([item['document']['id'] for item in result['items']], [supply])

    def test_windows_overlap_and_cover_long_pages(self):
        words = [f'w{i}' for i in range(300)]
        parts = semantic.windows(' '.join(words))
        self.assertEqual(parts[0].split()[0], 'w0')
        self.assertIn('w299', parts[-1].split())
        self.assertTrue(all(len(p.split()) <= semantic.WINDOW for p in parts))
        self.assertEqual(semantic.windows('   '), [])

    def test_missing_model_disables_the_feature(self):
        self.assertIsNone(semantic.load(None))
        self.assertIsNone(semantic.load(Path(tempfile.gettempdir()) / 'no-such-model'))
        self.texts.semantic = None
        self.assertEqual(self.texts.search_ranked('عقد', 10, 0)['method'], ranked.METHOD)


if __name__ == '__main__':
    unittest.main()
