"""Synthetic fixtures test infrastructure, never institutional ground truth."""
import copy
from contextlib import redirect_stdout
from datetime import datetime
import hashlib
import json
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from smartarchive.evaluation.metrics import evaluate, levenshtein, normalize
from smartarchive.evaluation.runner import main, run
from smartarchive.evaluation.tracking import create_run
from smartarchive.evaluation.validation import ValidationError, decode_text, parse_json


class MetricsTests(unittest.TestCase):
    def test_known_edit_operations(self):
        for ref, hyp, expected in [('abc', 'axc', (1, 0, 0)), ('abc', 'ac', (0, 1, 0)),
                                   ('abc', 'abxc', (0, 0, 1)), ('', 'abc', (0, 0, 3)),
                                   ('abc', '', (0, 3, 0)), ('', '', (0, 0, 0))]:
            with self.subTest(ref=ref, hyp=hyp):
                edits = levenshtein(ref, hyp)
                self.assertEqual((edits.substitutions, edits.deletions, edits.insertions), expected)

    def test_kitten_sitting(self):
        self.assertEqual(levenshtein('kitten', 'sitting').distance, 3)

    def test_known_rates(self):
        result = evaluate(reference='abc def', hypothesis='axc def!', policy='strict-v1')
        self.assertEqual(result['cer']['distance'], 2)
        self.assertEqual(result['cer']['rate'], 2 / 7)
        self.assertEqual(result['wer']['substitutions'], 2)
        self.assertEqual(result['wer']['rate'], 1)

    def test_mixed_languages(self):
        result = evaluate(reference='كتاب API 2', hypothesis='كتاب API 3', policy='strict-v1')
        self.assertEqual(result['wer']['rate'], 1 / 3)
        self.assertEqual(result['cer']['substitutions'], 1)

    def test_strict_preserves_every_codepoint(self):
        text = '  كِـتاب،\r\nAPI!  '
        self.assertEqual(normalize(text, 'strict-v1'), text)

    def test_normalization_arabic_forms_marks_and_whitespace(self):
        self.assertEqual(normalize('  ﻻ  كِـتاب\r\nAPI،  ', 'normalized-v1'), 'لا كتاب API،')

    def test_nfc_and_arabic_letters_preserved(self):
        self.assertEqual(normalize('ا\u0654 إ آ ى ي ة ه', 'normalized-v1'), 'أ إ آ ى ي ة ه')

    def test_punctuation_case_digits_and_nonarabic_compatibility_preserved(self):
        self.assertEqual(normalize('API، api! ١ 1 ①', 'normalized-v1'), 'API، api! ١ 1 ①')

    def test_symmetric_normalization_and_raw_unchanged(self):
        ref, hyp = 'كِـتاب\nAPI', 'كتاب API'
        self.assertEqual(evaluate(reference=ref, hypothesis=hyp, policy='normalized-v1')['cer']['rate'], 0)
        self.assertGreater(evaluate(reference=ref, hypothesis=hyp, policy='strict-v1')['cer']['rate'], 0)
        self.assertEqual(ref, 'كِـتاب\nAPI')

    def test_empty_reference_undefined_with_insertions(self):
        result = evaluate(reference='', hypothesis='abc', policy='strict-v1')
        self.assertIsNone(result['cer']['rate'])
        self.assertEqual(result['cer']['insertions'], 3)
        self.assertEqual(result['wer']['insertions'], 1)

    def test_empty_prediction_is_all_deletions_at_metric_level(self):
        self.assertEqual(evaluate(reference='كتاب', hypothesis='', policy='strict-v1')['cer']['rate'], 1)

    def test_multicolumn_reading_order_matters(self):
        ref = 'عنوان\nعمود أيمن\nعمود أيسر'
        swapped = 'عنوان\nعمود أيسر\nعمود أيمن'
        self.assertEqual(evaluate(reference=ref, hypothesis=ref, policy='normalized-v1')['wer']['rate'], 0)
        self.assertGreater(evaluate(reference=ref, hypothesis=swapped, policy='normalized-v1')['wer']['rate'], 0)

    def test_invalid_policy(self):
        with self.assertRaises(ValueError):
            normalize('text', 'unknown')


class ValidationTests(unittest.TestCase):
    def test_invalid_text(self):
        for data in (b'', b' \n', b'\xff', b'\xef\xbb\xbfabc', b'abc\x00'):
            with self.subTest(data=data), self.assertRaises(ValidationError):
                decode_text(data, 'fixture')

    def test_json_invalid_duplicate_nonfinite_and_wrong_type(self):
        for data in (b'{', b'[]', b'{"x":1,"x":2}', b'{"x":NaN}',
                     b'{"x":' + b'1' * 5000 + b'}'):
            with self.subTest(data=data), self.assertRaises(ValidationError):
                parse_json(data, 'fixture')


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'source.bin'
        self.source.write_bytes(b'synthetic source, not an institutional document')
        self.pred = self.root / 'prediction.txt'
        self.pred.write_text('كتاب API', encoding='utf-8')
        self.ref = self.root / 'reference.txt'
        self.ref.write_text('كِتاب API', encoding='utf-8')
        self.gt_path = self.root / 'page.json'
        self.gt = {
            'schema_version': 'gt-v1', 'document_id': 'synthetic-1',
            'source_sha256': self.hash(self.source), 'page': 1,
            'text_path': 'reference.txt', 'text_sha256': self.hash(self.ref),
            'is_blank': False, 'reading_order': ['header', 'right column', 'left column'],
            'transcriber': 'synthetic-author',
            'review': {'status': 'approved', 'reviewer': 'synthetic-reviewer',
                       'reviewed_at': '2026-10-27T10:00:00-07:00'},
        }
        self.entry = {
            'document_id': 'synthetic-1', 'source_path': 'source.bin',
            'source_sha256': self.hash(self.source), 'page': 1, 'split': 'pilot',
            'variant': 'synthetic-output', 'prediction_path': 'prediction.txt',
            'ground_truth_path': 'page.json', 'engine': {'name': 'synthetic', 'version': None},
            'language': 'ara+eng', 'configuration': {'psm': 3},
            'preprocessing': {'method': 'none'}, 'ocr_runtime_seconds': None,
        }
        self.manifest = self.root / 'manifest.json'

    @staticmethod
    def hash(path):
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def execute(self, entries=None):
        self.gt_path.write_text(json.dumps(self.gt, ensure_ascii=False), encoding='utf-8')
        self.manifest.write_text(json.dumps({'schema_version': 'benchmark-v1',
                                            'entries': entries if entries is not None else [self.entry]}),
                                 encoding='utf-8')
        return run(self.manifest, self.root / 'runs', ['strict-v1', 'normalized-v1'])

    def test_approved_evaluation_provenance_and_raw_snapshots(self):
        before = {p: p.read_bytes() for p in (self.source, self.pred, self.ref)}
        folder, report = self.execute()
        row = report['pages'][0]
        self.assertEqual(row['status'], 'EVALUATED')
        self.assertEqual(row['source_sha256'], self.hash(self.source))
        self.assertEqual(row['prediction_sha256'], self.hash(self.pred))
        self.assertEqual(row['ground_truth']['text_sha256'], self.hash(self.ref))
        self.assertEqual((folder / 'entry_00001/prediction.txt').read_bytes(), self.pred.read_bytes())
        self.assertEqual((folder / 'entry_00001/reference.txt').read_bytes(), self.ref.read_bytes())
        self.assertEqual((folder / 'input_manifest.json').read_bytes(), self.manifest.read_bytes())
        self.assertEqual(report['manifest_sha256'], self.hash(self.manifest))
        self.assertIsNotNone(datetime.fromisoformat(report['finished_at']).tzinfo)
        self.assertIn('benchmark_source_sha256', report['environment'])
        self.assertEqual(row['evaluations']['normalized-v1']['cer']['rate'], 0)
        self.assertTrue((folder / 'pages.csv').is_file())
        self.assertTrue((folder / 'summaries.csv').is_file())
        for path, data in before.items():
            self.assertEqual(path.read_bytes(), data)

    def test_unique_runs_and_no_overwrite(self):
        first, _ = self.execute()
        old = (first / 'report.json').read_bytes()
        second, _ = self.execute()
        self.assertNotEqual(first, second)
        self.assertEqual((first / 'report.json').read_bytes(), old)

    def test_output_root_is_file_never_overwritten(self):
        occupied = self.root / 'occupied'
        occupied.write_bytes(b'preserve me')
        with self.assertRaises(FileExistsError):
            run(self.manifest, occupied, ['strict-v1'])
        self.assertEqual(occupied.read_bytes(), b'preserve me')

    def test_forced_run_collision_rejected(self):
        with patch('smartarchive.evaluation.tracking.uuid.uuid4') as identifier:
            identifier.return_value.hex = 'fixed'
            with patch('smartarchive.evaluation.tracking.datetime') as clock:
                clock.now.return_value.strftime.return_value = 'fixed-time_'
                create_run(self.root / 'collision')
                with self.assertRaises(FileExistsError):
                    create_run(self.root / 'collision')

    def test_missing_gt_not_evaluated(self):
        self.entry['ground_truth_path'] = None
        _, report = self.execute()
        self.assertEqual(report['pages'][0]['status'], 'NOT_EVALUATED')
        self.assertEqual(report['pages'][0]['evaluations'], {})
        self.assertIsNone(report['summaries'][0]['cer']['micro_rate'])

    def test_draft_and_reviewed_gt_not_evaluated(self):
        for status in ('draft', 'reviewed'):
            self.gt['review']['status'] = status
            if status == 'draft':
                self.gt['review'].update(reviewer=None, reviewed_at=None)
            else:
                self.gt['review'].update(reviewer='reviewer', reviewed_at='2026-10-27T00:00:00Z')
            _, report = self.execute()
            self.assertEqual(report['pages'][0]['status'], 'NOT_EVALUATED')

    def test_missing_configured_gt_file_is_error(self):
        self.entry['ground_truth_path'] = 'missing.json'
        _, report = self.execute()
        self.assertEqual(report['pages'][0]['status'], 'VALIDATION_ERROR')

    def test_empty_prediction_error(self):
        self.pred.write_bytes(b'')
        _, report = self.execute()
        self.assertIn('empty', report['pages'][0]['reason'])

    def test_empty_reference_requires_blank_label(self):
        self.ref.write_bytes(b'')
        self.gt['text_sha256'] = self.hash(self.ref)
        _, report = self.execute()
        self.assertEqual(report['status'], 'FAILED_VALIDATION')
        self.gt['is_blank'] = True
        _, report = self.execute()
        self.assertIsNone(report['pages'][0]['evaluations']['strict-v1']['cer']['rate'])

    def test_wrong_source_page_hash_and_review_metadata(self):
        mutations = [
            ('source_sha256', '0' * 64), ('page', 2), ('document_id', 'wrong'),
            ('text_sha256', '0' * 64), ('reading_order', ['same', 'same']),
            ('review', {'status': 'approved', 'reviewer': 'synthetic-author',
                        'reviewed_at': '2026-10-27T00:00:00Z'}),
            ('review', {'status': 'approved', 'reviewer': 'reviewer', 'reviewed_at': 'yesterday'}),
        ]
        original = copy.deepcopy(self.gt)
        for key, value in mutations:
            with self.subTest(key=key, value=value):
                self.gt = {**copy.deepcopy(original), key: value}
                _, report = self.execute()
                self.assertEqual(report['status'], 'FAILED_VALIDATION')

    def test_missing_prediction_and_source_hash_mismatch(self):
        for mutation in ({'prediction_path': 'missing.txt'}, {'source_sha256': '0' * 64}, {'page': True}):
            with self.subTest(mutation=mutation):
                _, report = self.execute([{**self.entry, **mutation}])
                self.assertEqual(report['status'], 'FAILED_VALIDATION')

    def test_duplicate_entries(self):
        _, report = self.execute([self.entry, self.entry])
        self.assertEqual(report['pages'][1]['status'], 'VALIDATION_ERROR')

    def test_document_split_conflict(self):
        other = {**self.entry, 'page': 2, 'split': 'test'}
        _, report = self.execute([self.entry, other])
        self.assertIn('conflicting', report['pages'][1]['reason'])

    def test_same_source_different_id_cannot_leak_across_splits(self):
        other = {**self.entry, 'document_id': 'alias', 'split': 'test'}
        _, report = self.execute([self.entry, other])
        self.assertIn('different dataset splits', report['pages'][1]['reason'])

    def test_nonobject_entry_and_unknown_field_reported(self):
        for entry in (None, [], {**self.entry, 'typo': 1}):
            with self.subTest(entry=entry):
                _, report = self.execute([entry])
                self.assertEqual(report['status'], 'FAILED_VALIDATION')

    def test_malformed_prediction_utf8(self):
        self.pred.write_bytes(b'\xff')
        _, report = self.execute()
        self.assertIn('UTF-8', report['pages'][0]['reason'])

    def test_reference_prediction_path_alias_rejected(self):
        self.gt['text_path'] = 'prediction.txt'
        self.gt['text_sha256'] = self.hash(self.pred)
        _, report = self.execute()
        self.assertIn('separate files', report['pages'][0]['reason'])

    def test_mixed_valid_invalid_pages_retained(self):
        other = {**self.entry, 'page': 2, 'prediction_path': 'missing.txt'}
        _, report = self.execute([self.entry, other])
        self.assertEqual(report['status'], 'FAILED_VALIDATION')
        self.assertEqual(report['pages'][0]['status'], 'EVALUATED')
        self.assertEqual(report['pages'][1]['status'], 'VALIDATION_ERROR')

    def test_variant_metadata_conflict(self):
        other = {**self.entry, 'page': 2, 'configuration': {'psm': 6}}
        _, report = self.execute([self.entry, other])
        self.assertIn('conflicting engine', report['pages'][1]['reason'])

    def test_same_stem_different_documents_do_not_collide(self):
        self.entry['ground_truth_path'] = None
        other = {**self.entry, 'document_id': 'synthetic-2'}
        folder, report = self.execute([self.entry, other])
        self.assertEqual(report['status'], 'COMPLETED')
        self.assertTrue((folder / 'entry_00002/prediction.txt').exists())

    def test_document_micro_aggregation_not_cross_page_alignment(self):
        # Reuse synthetic GT but bind page 2 explicitly.
        gt2 = {**self.gt, 'page': 2}
        (self.root / 'page2.json').write_text(json.dumps(gt2), encoding='utf-8')
        other = {**self.entry, 'page': 2, 'ground_truth_path': 'page2.json'}
        _, report = self.execute([self.entry, other])
        summary = next(item for item in report['summaries']
                       if item['scope'] == 'document' and item['policy'] == 'strict-v1')
        self.assertEqual(summary['evaluated_pages'], 2)
        self.assertEqual(summary['cer']['deletions'], 2)
        self.assertEqual(summary['cer']['reference_units'], 2 * len('كِتاب API'))

    def test_malformed_manifest_generates_failure_report_and_nonzero_cli(self):
        self.manifest.write_text('{', encoding='utf-8')
        folder, report = run(self.manifest, self.root / 'runs', ['strict-v1'])
        self.assertEqual(report['status'], 'FAILED_VALIDATION')
        self.assertTrue((folder / 'report.json').exists())
        output = io.StringIO()
        with redirect_stdout(output):
            code = main(['--manifest', str(self.manifest), '--output-root', str(self.root / 'cli')])
        self.assertEqual(code, 2)
        self.assertIn('FAILED_VALIDATION', output.getvalue())


if __name__ == '__main__':
    unittest.main()
