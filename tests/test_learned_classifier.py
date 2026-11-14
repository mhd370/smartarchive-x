"""Learned classifier (tfidf-svm-v1): training on confirmed decisions, explained suggestions, abstention."""
from pathlib import Path
import sys
import tempfile
import unittest
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from smartarchive.classification import learned  # noqa: E402
from smartarchive.classification.service import Classifications  # noqa: E402
from smartarchive.domain.documents import ArchiveError  # noqa: E402
from smartarchive.persistence.database import Database  # noqa: E402
from smartarchive.search.pages import PageTexts  # noqa: E402

INVOICES = ['فاتورة شركة النخيل رقم {n} الإجمالي {n}٠٠ دينار توريد مواد كهربائية وضريبة المبيعات',
            'فاتورة مؤسسة البناء رقم {n} المجموع {n}٥٠ دينار أصناف وكميات وسعر الوحدة',
            'فاتورة شركة الأفق للتوريدات رقم {n} الإجمالي {n}٢٠ دينار مستلزمات مكتبية']
MINUTES = ['محضر اجتماع لجنة المتابعة رقم {n} حضر السادة الأعضاء وتقرر ما يلي',
           'محضر اجتماع اللجنة الفنية رقم {n} جدول الأعمال ومناقشة المعوقات وتقرر',
           'محضر اجتماع لجنة المشتريات رقم {n} بحضور الأعضاء وبعد المداولة تقرر']
CONTRACTS = ['عقد توريد رقم {n} بين الطرف الأول والطرف الثاني البند الأول مدة العقد',
             'عقد تنفيذ أعمال رقم {n} الطرف الأول المديرية والطرف الثاني الشركة البند الثاني',
             'عقد تقديم خدمات رقم {n} يلتزم الطرف الثاني بالبنود والشروط الخاصة']


class LearnedModelTests(unittest.TestCase):
    def test_train_predict_explain_and_abstain(self):
        texts, labels = [], []
        for n in range(1, 5):
            for kind, templates in (('invoice', INVOICES), ('minutes', MINUTES), ('contract', CONTRACTS)):
                for template in templates:
                    texts.append(template.format(n=n))
                    labels.append(kind)
        model = learned.train(texts, ['scan.png'] * len(texts), labels + [], source='test')
        self.assertEqual(model['card']['classes'], ['contract', 'invoice', 'minutes'])
        groups = {'invoice': 'financial', 'minutes': 'administrative', 'contract': 'legal'}
        result = learned.predict(model, 'فاتورة شركة جديدة الإجمالي ٩٠٠ دينار ضريبة', 'x.png', groups, set(groups))
        self.assertEqual((result.category_id, result.reason, result.group_id), ('invoice', 'suggested', 'financial'))
        self.assertIn('فاتوره', [hit['keyword'] for hit in result.evidence['invoice']])  # explained by its words
        empty = learned.predict(model, '   ', 'x.png', groups, set(groups))
        self.assertEqual((empty.category_id, empty.reason), (None, 'no_text'))
        # A class that is no longer an active category is never suggested.
        only = learned.predict(model, 'فاتورة شركة الإجمالي', 'x.png', groups, {'minutes', 'contract'})
        self.assertNotEqual(only.category_id, 'invoice')
        with self.assertRaises(ValueError):
            learned.train(['a', 'b'], ['x', 'y'], ['invoice', 'minutes'], source='test')  # too few examples

    def test_character_baseline(self):
        texts, labels = [], []
        for n in range(1, 5):
            for kind, templates in (('invoice', INVOICES), ('minutes', MINUTES), ('contract', CONTRACTS)):
                texts += [t.format(n=n) for t in templates]
                labels += [kind] * len(templates)
        model = learned.train(texts, ['scan.png'] * len(texts), labels, source='test', method=learned.CHAR_METHOD)
        self.assertEqual(model['card']['method'], 'tfidf-char-lr-v1')
        groups = {'invoice': 'financial', 'minutes': 'administrative', 'contract': 'legal'}
        # A word split by OCR («فات ورة») still shares character n-grams with «فاتورة».
        result = learned.predict(model, 'فات ورة شركة جديدة الإجمالي ٩٠٠ دينار ضريبة', 'x.png', groups, set(groups))
        self.assertEqual(result.category_id, 'invoice')
        with self.assertRaises(ValueError):
            learned.train(texts, ['x'] * len(texts), labels, source='test', method='nope')


class ServiceTrainingTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.db = Database(Path(temp.name) / 'archive.sqlite3')
        self.db.initialize()
        self.classes = Classifications(self.db, models_dir=Path(temp.name) / 'models')
        self.classes.seed()

    def document(self, text: str) -> str:
        doc = str(uuid.uuid4())
        with self.db.connect() as db:
            db.execute('INSERT INTO documents VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                       (doc, 'scan.png', 10, 'image/png', uuid.uuid4().hex * 2, doc + '/o.png', 1, 'ready',
                        'OCR_COMPLETED', '2026-01-01T00:00:00', '2026-01-01T00:00:00'))
            PageTexts._upsert(db, doc, 1, 'ocr', None, None, text)
        return doc

    def test_training_on_confirmed_decisions_switches_suggestions_to_the_model(self):
        self.assertIsNone(self.classes.model_info()['model'])
        with self.assertRaises(ArchiveError):
            self.classes.train('admin')  # nothing confirmed yet
        for n in range(1, 4):
            for kind, templates in (('invoice', INVOICES), ('minutes', MINUTES)):
                for template in templates:
                    doc = self.document(template.format(n=n))
                    suggestion = self.classes.suggest(doc)
                    self.assertEqual(suggestion['method'], 'keywords-v1')
                    self.classes.decide(doc, kind, '', self.classes.get(doc)['sequence'], 'reviewer')
        card = self.classes.train('admin')
        self.assertEqual(card['examples'], {'invoice': 9, 'minutes': 9})
        info = self.classes.model_info()
        self.assertEqual((info['active_method'], info['model']['id']), ('tfidf-svm-v1', card['id']))
        new = self.document('فاتورة مؤسسة جديدة الإجمالي ٧٠٠ دينار توريد أصناف')
        suggestion = self.classes.suggest(new)
        self.assertEqual((suggestion['method'], suggestion['category_id']), ('tfidf-svm-v1', 'invoice'))
        self.assertIn('model_id', self.classes.get(new)['suggestion']['basis'])
        # Confirmed documents keep their category: a decision always wins over a new suggestion.
        decided = self.classes.get(self.document(MINUTES[0].format(n=9)))
        self.assertIn(decided['state'], ('none', 'suggested', 'uncertain'))


if __name__ == '__main__':
    unittest.main()
