"""Learned classifier (tfidf-svm-v1): training on confirmed decisions, explained suggestions, abstention, and the
multimodal fusion with first-page layout features (visual-layout-v1)."""
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


def page(kind: str, n: int):
    """A synthetic first page: invoices are ruled tables, minutes are plain paragraphs."""
    from PIL import Image, ImageDraw
    image = Image.new('RGB', (600, 850), 'white')
    draw = ImageDraw.Draw(image)
    if kind == 'invoice':
        for y in range(250 + n * 3, 700, 40):
            draw.line((40, y, 560, y), fill='black', width=3)
        for x in (40, 200, 380, 560):
            draw.line((x, 250 + n * 3, x, 690), fill='black', width=3)
    else:
        for y in range(120 + n * 3, 760, 22):
            draw.rectangle((60 + (y % 50), y, 540, y + 9), fill='black')
    return image


class MultimodalTests(unittest.TestCase):
    def test_the_image_model_is_trained_saved_and_fused(self):
        from smartarchive.classification import visual
        texts, labels, images = [], [], []
        for n in range(1, 5):
            for kind, templates in (('invoice', INVOICES), ('minutes', MINUTES)):
                for template in templates:
                    texts.append(template.format(n=n))
                    labels.append(kind)
                    images.append(visual.features(page(kind, n)))
        model = learned.train(texts, ['scan.png'] * len(texts), labels, source='test', images=images)
        self.assertEqual((model['card']['image_method'], model['card']['beta']), ('visual-layout-v1', 1.0))
        groups = {'invoice': 'financial', 'minutes': 'administrative'}
        # A page without text: the text model alone abstains, the image decides.
        self.assertEqual(learned.predict(model, '', 'x.png', groups, set(groups)).reason, 'no_text')
        blank = learned.predict(model, '', 'x.png', groups, set(groups), visual.features(page('invoice', 7)))
        self.assertEqual((blank.category_id, blank.image_used), ('invoice', True))
        self.assertEqual(learned.method_name(model, blank.image_used), 'tfidf-svm-v1+visual-layout-v1')
        with tempfile.TemporaryDirectory() as folder:
            learned.save(model, Path(folder))
            loaded = learned.load(Path(folder))
            self.assertIsNotNone(loaded['image'])
            again = learned.predict(loaded, '', 'x.png', groups, set(groups), visual.features(page('minutes', 7)))
            self.assertEqual(again.category_id, 'minutes')
            # retrained without images: the stale image model is removed, never fused with the new text model
            learned.save(learned.train(texts, ['scan.png'] * len(texts), labels, source='test'), Path(folder))
            self.assertIsNone(learned.load(Path(folder))['image'])
        # Too few images per class: text only.
        few = learned.train(texts, ['scan.png'] * len(texts), labels, source='test', images=images[:2] + [None] * 22)
        self.assertIsNone(few['image'])
        self.assertNotIn('image_method', few['card'])


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

    def test_the_service_fuses_the_first_page_image(self):
        pages = {}
        self.classes.page_image = lambda document_id: pages.get(document_id)
        for n in range(1, 4):
            for kind, templates in (('invoice', INVOICES), ('minutes', MINUTES)):
                for template in templates:
                    doc = self.document(template.format(n=n))
                    pages[doc] = page(kind, n)
                    self.classes.suggest(doc)
                    self.classes.decide(doc, kind, '', self.classes.get(doc)['sequence'], 'reviewer')
        card = self.classes.train('admin')
        self.assertEqual(card['image_method'], 'visual-layout-v1')
        with self.db.connect() as db:  # features are cached, not recomputed from the original
            self.assertEqual(db.execute('SELECT COUNT(*) FROM document_images').fetchone()[0], 18)
        # A severe scan: OCR read almost nothing, but the page is a ruled table.
        scan = self.document('ـ')
        pages[scan] = page('invoice', 5)
        suggestion = self.classes.suggest(scan, force=True)
        self.assertEqual((suggestion['method'], suggestion['category_id']), ('tfidf-svm-v1+visual-layout-v1', 'invoice'))
        # Without a readable original the suggestion falls back to the text model.
        lost = self.document(INVOICES[0].format(n=8))
        suggestion = self.classes.suggest(lost)
        self.assertEqual((suggestion['method'], suggestion['category_id']), ('tfidf-svm-v1', 'invoice'))


if __name__ == '__main__':
    unittest.main()
