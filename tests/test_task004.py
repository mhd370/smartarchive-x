"""Regressions for offline manual workspaces and approved-only error analysis."""
import csv
import json
import re

from test_pilot import PilotFixture
from smartarchive.evaluation.error_analysis import summarize, write_analysis
from smartarchive.evaluation.ground_truth import current
from smartarchive.evaluation.review_workspace import create_workspace
from smartarchive.evaluation.validation import ValidationError


class WorkspaceTests(PilotFixture):
    def workspace(self, **kwargs):
        return create_workspace(self.root, self.dataset, self.store, self.identifier, 1,
                                self.root / 'workspaces', **kwargs)

    def test_new_workspace_is_blank_and_never_uses_predictions(self):
        folder = self.workspace()
        html = (folder / 'workspace.html').read_text(encoding='utf-8')
        # HTML removes exactly the first newline immediately after <textarea>.
        self.assertEqual(re.search(r'<textarea[^>]*>(.*?)</textarea>', html, re.S).group(1).removeprefix('\n'), '')
        self.assertIn('dir="rtl"', html)
        self.assertIn('connect-src \'none\'', html)
        metadata = json.loads((folder / 'workspace.json').read_text(encoding='utf-8'))
        self.assertEqual(metadata['gt_status'], 'PENDING')
        self.assertIsNone(metadata['reference_sha256'])
        self.assertIsNone(current(self.store, self.document, 1))
        self.assertFalse((folder / 'reference_snapshot.txt').exists())

    def test_review_requires_a_submitted_transcription(self):
        with self.assertRaises(ValidationError):
            self.workspace(review_only=True)

    def test_review_is_read_only_escaped_and_byte_pinned(self):
        self.text.write_bytes(b'\n</textarea><script>alert(1)</script>\r\n__PAGE__')
        state = self.add()
        before = state['sidecar'].read_bytes()
        folder = self.workspace(review_only=True)
        html = (folder / 'workspace.html').read_text(encoding='utf-8')
        self.assertIn(' readonly', html)
        self.assertIn('&lt;/textarea&gt;&lt;script&gt;', html)
        self.assertIn('__PAGE__</textarea>', html)
        self.assertNotIn('id="save"', html)
        self.assertEqual((folder / 'reference_snapshot.txt').read_bytes(), self.text.read_bytes())
        self.assertEqual(state['sidecar'].read_bytes(), before)
        self.assertEqual(current(self.store, self.document, 1)['status'], 'draft')

    def test_workspace_is_unique_and_source_identity_checked(self):
        first, second = self.workspace(), self.workspace()
        self.assertNotEqual(first, second)
        self.source.write_bytes(b'changed source')
        with self.assertRaises(ValidationError):
            self.workspace()


class AnalysisTests(PilotFixture):
    def report_path(self, *, approve=False):
        if approve:
            self.add()
            self.decision('review')
            self.decision('approve')
        bundle, _ = self.compare()
        folder = next((bundle / 'evaluation').iterdir())
        return folder / 'report.json', bundle / 'associations.json'

    def test_pending_results_have_no_accuracy_or_error_counts(self):
        report_path, associations = self.report_path()
        result = write_analysis(report_path, associations_path=associations)
        self.assertEqual(result['status'], 'NOT_EVALUATED')
        self.assertEqual(result['evaluated_page_variants'], 0)
        self.assertTrue(all(row['cer'] is None and row['wer'] is None for row in result['results']))
        with (report_path.parent / 'accuracy_by_page.csv').open(encoding='utf-8', newline='') as stream:
            rows = list(csv.DictReader(stream))
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(row['cer_rate'] == '' and row['cer_substitutions'] == '' for row in rows))

    def test_approved_analysis_reuses_rates_and_preserves_policy_separation(self):
        report_path, associations = self.report_path(approve=True)
        before = report_path.read_bytes()
        result = write_analysis(report_path, associations_path=associations)
        report = json.loads(before)
        self.assertEqual(result['status'], 'EVALUATED')
        self.assertEqual({row['policy'] for row in result['results']}, {'strict-v1', 'normalized-v1'})
        for row in result['results']:
            self.assertEqual(row['cer'], report['pages'][0]['evaluations'][row['policy']]['cer'])
        self.assertEqual(report_path.read_bytes(), before)
        self.assertIsNotNone(result['associations_sha256'])

    def test_analysis_cannot_overwrite_or_trust_changed_snapshot(self):
        report_path, _ = self.report_path(approve=True)
        write_analysis(report_path)
        with self.assertRaises(FileExistsError):
            write_analysis(report_path)
        (report_path.parent / 'entry_00001/reference.txt').write_bytes(b'changed')
        with self.assertRaises(ValidationError):
            summarize(report_path)

    def test_analysis_rejects_evaluated_row_without_approved_gt(self):
        report_path, _ = self.report_path(approve=True)
        value = json.loads(report_path.read_text(encoding='utf-8'))
        value['pages'][0]['ground_truth']['metadata']['review']['status'] = 'draft'
        report_path.write_text(json.dumps(value), encoding='utf-8')
        with self.assertRaises(ValidationError):
            summarize(report_path)
