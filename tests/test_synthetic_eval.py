"""Scoring of the synthetic-corpus evaluation (tools/evaluate_synthetic.py), end to end with a fake OCR engine."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import evaluate_synthetic as ev  # noqa: E402
from smartarchive.processing.ocr import Line, Word  # noqa: E402
from test_ocr_pipeline import encoded  # noqa: E402
from test_processing import text_page  # noqa: E402

INVOICE = ('مكتب الضياء للاستشارات\nرقم الفاتورة: INV-654-2025\nالتاريخ: ١٧/١١/٢٠٢٥\n'
           'إلى: مديرية الخدمات العامة - الشؤون المالية\nفاتورة\nالإجمالي: ٥,٤١٥ دينار')
LETTER = ('وزارة الأشغال\nالرقم: و/١٢٣/٢٠٢٤\nالتاريخ: 03/02/2024\nمن: وزارة الأشغال\n'
          'إلى: مديرية الخدمات العامة - الدائرة الفنية\nالموضوع: تمديد مدة مشروع الطريق الدائري\n'
          'نرجو الموافقة على تمديد مدة المشروع وفق الكتاب المرفق والتنسيق مع الجهات المعنية.')
TRUTH = {
    'S0001': ('invoice', 'financial', INVOICE, {'reference_number': 'INV-654-2025', 'date': '2025-11-17',
              'sender': 'مكتب الضياء للاستشارات', 'recipient': 'مديرية الخدمات العامة - الشؤون المالية',
              'subject': 'فاتورة مكتب الضياء للاستشارات', 'amount': '5,415 دينار'}),
    'S0002': ('incoming_letter', 'correspondence', LETTER, {'reference_number': 'و/١٢٣/٢٠٢٤', 'date': '2024-02-03',
              'sender': 'وزارة الأشغال', 'recipient': 'مديرية الخدمات العامة - الدائرة الفنية',
              'subject': 'تمديد مدة مشروع الطريق الدائري', 'amount': None}),
}


class QueueEngine:
    """Returns the queued page texts in processing order (one page per document here)."""
    name, languages, missing = 'fake', 'ara', []
    outputs: list[str] = []

    def version(self):
        return 'test'

    def recognize(self, image):
        text = QueueEngine.outputs.pop(0)
        return [Line(line, 0.9, (0, i * 50, 900, i * 50 + 40), [Word(line, 0.9, (0, i * 50, 900, i * 50 + 40))])
                for i, line in enumerate(text.split('\n'))]


class ScoringTests(unittest.TestCase):
    def test_metadata_values_compare_after_normalization(self):
        text = 'رقم الكتاب: و/١٢٣/٢٠٢٤\nالمبلغ ٥,٤١٥ دينار'
        result = ev.score_metadata({'reference_number': 'و/١٢٣/٢٠٢٤', 'amount': '5,415 دينار', 'sender': 'وزارة المالية'},
                                   {'reference_number': 'و/123/2024', 'amount': '5,415'}, text)
        self.assertTrue(result['reference_number']['correct'])
        self.assertTrue(result['amount']['correct'])
        self.assertFalse(result['sender']['correct'])
        self.assertFalse(result['sender']['in_text'])  # not written in the document: reported apart

    def test_relations_are_scored_per_unordered_pair_and_kind(self):
        truth = {frozenset(('A', 'B')): 'exact_duplicate', frozenset(('C', 'D')): 'version_of'}
        result = ev.score_relations(truth, [('B', 'A', 'exact_duplicate'), ('D', 'C', 'near_duplicate'),
                                            ('E', 'F', 'near_duplicate')])
        self.assertEqual(result['exact_duplicate']['precision'], 1.0)
        self.assertEqual(result['version_of']['recall'], 0.0)
        self.assertEqual(result['near_duplicate']['precision'], 0.0)
        self.assertEqual(result['any_relation']['recall'], 1.0)
        self.assertAlmostEqual(result['any_relation']['precision'], 2 / 3)

    def test_retrieval_metrics(self):
        self.assertEqual(ev.retrieval(['x', 'a'], {'a'}), {'recall': 1.0, 'mrr': 0.5, 'ndcg': 1 / __import__('math').log2(3)})
        self.assertEqual(ev.retrieval([], {'a'})['recall'], 0.0)


class EndToEndTests(unittest.TestCase):
    def test_pipeline_is_scored_against_ground_truth(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        corpus, work = Path(temp.name) / 'corpus', Path(temp.name) / 'work'
        (corpus / 'ground_truth').mkdir(parents=True)
        images = {'S0001': encoded(text_page(seed=1)), 'S0002': encoded(text_page(seed=2))}
        images['S0003'] = images['S0001']  # the same file filed again
        manifest = []
        for doc_id in ('S0001', 'S0002', 'S0003'):
            kind, group, text, meta = TRUTH['S0001' if doc_id == 'S0003' else doc_id]
            relations = [{'kind': 'exact_duplicate', 'target': 'S0001'}] if doc_id == 'S0003' else []
            path = corpus / 'archive' / 'finance' / '2025' / f'scan_{doc_id}.png'
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(images[doc_id])
            entry = {'doc_id': doc_id, 'file': path.relative_to(corpus).as_posix(), 'type': kind, 'group': group,
                     'folder': 'finance/2025', 'layout': 'simple', 'quality': 'clean', 'pages': 1, 'relations': relations}
            manifest.append(entry)
            truth = {**entry, 'metadata': meta, 'pages': [{'page_no': 1, 'text': text, 'blocks': []}]}
            (corpus / 'ground_truth' / f'{doc_id}.json').write_text(json.dumps(truth, ensure_ascii=False), encoding='utf-8')
        (corpus / 'manifest.json').write_text(json.dumps({'generator': 'test', 'seed': 1, 'documents': manifest},
                                                         ensure_ascii=False), encoding='utf-8')
        (corpus / 'queries.json').write_text(json.dumps([
            {'id': 'Q001', 'query': 'تمديد مدة مشروع الطريق الدائري', 'kind': 'subject', 'relevant': ['S0002']},
            {'id': 'Q002', 'query': 'INV-654-2025', 'kind': 'reference_number', 'relevant': ['S0001', 'S0003']}],
            ensure_ascii=False), encoding='utf-8')
        QueueEngine.outputs = [INVOICE, LETTER.replace('الدائري', 'الداثري'), INVOICE]

        report = ev.evaluate(corpus, work, engine_factory=QueueEngine, log=lambda *_: None)

        self.assertEqual(report['pages'], 3)
        self.assertEqual(report['ocr']['by_layout']['simple']['pages'], 3)
        self.assertGreater(report['ocr']['all']['cer'], 0)
        self.assertLess(report['ocr']['all']['cer'], 0.01)
        self.assertEqual(report['relations']['exact_duplicate']['recall'], 1.0)
        fields = report['metadata']['by_field']
        self.assertEqual(fields['reference_number']['accuracy'], 1.0)
        self.assertEqual(fields['date']['accuracy'], 1.0)
        self.assertEqual(fields['amount']['accuracy'], 1.0)
        self.assertEqual(report['search']['exact']['reference_number']['recall@10'], 1.0)
        self.assertEqual(report['search']['exact']['subject']['recall@10'], 0.0)  # an OCR error breaks the exact subject
        self.assertEqual(report['search']['ranked']['subject']['recall@10'], 1.0)  # ranked search tolerates it
        self.assertEqual(report['classification']['documents'], 3)
        self.assertTrue((work / 'report.md').read_text(encoding='utf-8').startswith('# Synthetic evaluation'))
        again = ev.evaluate(corpus, work, engine_factory=QueueEngine, log=lambda *_: None,
                            re_enrich=True)  # resumes: no re-import, no new OCR
        self.assertEqual(again['documents'], 3)
        self.assertEqual(again['ocr']['all']['cer'], report['ocr']['all']['cer'])
        self.assertEqual(again['metadata']['by_field']['amount']['mean_value_cer'], 0.0)
        self.assertEqual(json.loads((work / 'state.json').read_text(encoding='utf-8'))['ids'].keys(),
                         {'S0001', 'S0002', 'S0003'})


if __name__ == '__main__':
    unittest.main()
