"""Synthetic pilot/review/adapter fixtures. No institutional GT is produced."""
import copy
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from PIL import Image
from smartarchive.evaluation.ground_truth import current, submit, transition
from smartarchive.evaluation.historical import import_binding, prepare
from smartarchive.evaluation.metrics import evaluate
from smartarchive.evaluation.pilot import find_page, inventory, load_dataset
from smartarchive.evaluation.pilot_cli import main
from smartarchive.evaluation.runner import run
from smartarchive.evaluation.validation import ValidationError, digest


class PilotFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'input').mkdir()
        self.source = self.root / 'input/page.png'
        Image.new('RGB', (100, 120), 'white').save(self.source)
        self.dataset = inventory(self.root, self.root / 'input')
        self.document = self.dataset['documents'][0]
        self.identifier = self.document['document_id']
        self.store = self.root / 'gt'
        self.text = self.root / 'manual.txt'
        self.text.write_text('عنوان\nيمين API\nيسار', encoding='utf-8')
        self.folder = self.root / 'legacy/page_001'
        self.folder.mkdir(parents=True)
        (self.folder / 'original.png').write_bytes(self.source.read_bytes())
        self.regions = [
            {'type': 'shared_header', 'bbox': [0, 0, 100, 20], 'lines_detected': 1},
            {'type': 'right_column', 'bbox': [50, 20, 100, 120], 'lines_detected': 1},
            {'type': 'left_column', 'bbox': [0, 20, 50, 120], 'lines_detected': 1},
        ]
        self.blocks = [
            {'region_type': 'shared_header', 'region_order': 1, 'line_order': 1,
             'bbox': [0, 0, 100, 20], 'text': 'عنوان'},
            {'region_type': 'right_column', 'region_order': 2, 'line_order': 1,
             'bbox': [50, 20, 100, 40], 'text': 'يمين API'},
            {'region_type': 'left_column', 'region_order': 3, 'line_order': 1,
             'bbox': [0, 20, 50, 40], 'text': 'يسار'},
        ]
        self.prediction = 'عنوان\n\nيمين API\n\nيسار\n'
        for name in ('baseline_psm3.txt', 'region_psm.txt', 'line_psm.txt'):
            (self.folder / name).write_bytes(self.prediction.replace('\n', '\r\n').encode('utf-8'))
        self.report = {'page': 1, 'image_size': [100, 120], 'regions': self.regions,
                       'line_count': 3, 'variants': {name: {'characters': len(self.prediction), 'seconds': 1}
                                                   for name in ('baseline_psm3', 'region_psm', 'line_psm')}}
        self.write_metadata()
        self.binding = {'document_id': self.identifier, 'page': 1, 'layout': 'v3',
                        'kind': 'lines', 'directory': 'legacy/page_001'}

    def write_metadata(self):
        (self.folder / 'report.json').write_text(json.dumps(self.report), encoding='utf-8')
        (self.folder / 'line_blocks.json').write_text(json.dumps(self.blocks), encoding='utf-8')

    def add(self, *, expected=0, complete=True, manual=True, order=None):
        return submit(self.store, self.dataset, self.identifier, 1, self.text,
                      transcriber='author', reading_order=order or ['header', 'right column', 'left column'],
                      reason='Synthetic fixture revision', expected_version=expected,
                      complete=complete, manual=manual)

    def decision(self, action, *, version=1, actor='reviewer', attest=True):
        return transition(self.store, self.dataset, self.identifier, 1, actor=actor,
                          expected_version=version, action=action, attest=attest)

    def bindings(self):
        return {'schema_version': 'historical-bindings-v1', 'bindings': [self.binding]}

    def compare(self):
        bundle = prepare(self.root, self.dataset, self.bindings(), self.root / 'imports', self.store)
        return bundle, run(bundle / 'benchmark.json', bundle / 'evaluation', ['strict-v1', 'normalized-v1'])[1]


class InventoryTests(PilotFixture):
    def test_inventory_deterministic_pending_and_hashes(self):
        self.assertEqual(inventory(self.root, self.root / 'input'), self.dataset)
        self.assertEqual(self.document['source_sha256'], digest(self.source.read_bytes()))
        self.assertEqual(self.document['pages'][0]['ground_truth_status'], 'PENDING')

    def test_duplicate_bytes_are_aliases_not_new_documents(self):
        (self.root / 'input/copy.png').write_bytes(self.source.read_bytes())
        result = inventory(self.root, self.root / 'input')
        self.assertEqual(len(result['documents']), 1)
        self.assertEqual(len(result['documents'][0]['source_aliases']), 1)

    def test_multiframe_tiff_records_every_frame(self):
        one = Image.new('RGB', (30, 40), 'black')
        two = Image.new('RGB', (30, 40), 'white')
        one.save(self.root / 'input/multi.tiff', save_all=True, append_images=[two])
        result = inventory(self.root, self.root / 'input')
        multi = next(d for d in result['documents'] if d['source_path'].endswith('.tiff'))
        self.assertEqual([r['page'] for r in multi['pages']], [1, 2])
        self.assertNotEqual(multi['pages'][0]['pixel_sha256'], multi['pages'][1]['pixel_sha256'])

    def test_multipage_pdf_inventory(self):
        import pymupdf
        path = self.root / 'input/multi.pdf'
        with pymupdf.open() as pdf:
            pdf.new_page(width=24, height=24)
            page = pdf.new_page(width=24, height=24)
            page.draw_rect(pymupdf.Rect(0, 0, 12, 12), color=(0, 0, 0), fill=(0, 0, 0))
            pdf.save(path)
        result = inventory(self.root, self.root / 'input')
        multi = next(d for d in result['documents'] if d['source_path'].endswith('.pdf'))
        self.assertEqual([p['page'] for p in multi['pages']], [1, 2])
        self.assertEqual(multi['pages'][0]['width'], 100)
        self.assertNotEqual(multi['pages'][0]['pixel_sha256'], multi['pages'][1]['pixel_sha256'])

    def test_missing_or_malformed_source_rejected(self):
        (self.root / 'input/broken.png').write_bytes(b'not an image')
        with self.assertRaises(OSError):
            inventory(self.root, self.root / 'input')

    def test_unknown_page_is_error(self):
        with self.assertRaises(ValidationError):
            find_page(self.dataset, self.identifier, 2)

    def test_dataset_duplicate_ids_and_page_ids_rejected(self):
        for mutation in ('document', 'page'):
            value = copy.deepcopy(self.dataset)
            if mutation == 'document':
                value['documents'].append(copy.deepcopy(value['documents'][0]))
            else:
                value['documents'][0]['pages'].append(copy.deepcopy(value['documents'][0]['pages'][0]))
            path = self.root / 'dataset.json'
            path.write_text(json.dumps(value), encoding='utf-8')
            with self.subTest(mutation=mutation), self.assertRaises(ValidationError):
                load_dataset(path, self.root)

    def test_changed_source_fails_validation(self):
        path = self.root / 'dataset.json'
        path.write_text(json.dumps(self.dataset), encoding='utf-8')
        self.source.write_bytes(b'changed')
        with self.assertRaises(ValidationError):
            load_dataset(path, self.root)

    def test_unicode_policies_unchanged(self):
        self.assertEqual(evaluate(reference='ﻻ كِـتاب API', hypothesis='لا كتاب API',
                                  policy='normalized-v1')['cer']['rate'], 0)
        self.assertGreater(evaluate(reference='ﻻ كِـتاب API', hypothesis='لا كتاب API',
                                   policy='strict-v1')['cer']['rate'], 0)


class WorkflowTests(PilotFixture):
    def test_cli_manual_review_approval_and_comparison(self):
        (self.root / 'dataset.json').write_text(json.dumps(self.dataset), encoding='utf-8')
        (self.root / 'bindings.json').write_text(json.dumps(self.bindings()), encoding='utf-8')
        base = ['--root', str(self.root), '--dataset', 'dataset.json', '--store', 'gt']
        identity = ['--document', self.identifier, '--page', '1', '--expected-version', '1']
        with redirect_stdout(io.StringIO()):
            self.assertEqual(main([*base, 'submit', '--document', self.identifier, '--page', '1',
                                   '--expected-version', '0', '--text', 'manual.txt', '--transcriber', 'author',
                                   '--reading-order', 'header', 'right', 'left', '--reason', 'synthetic',
                                   '--manual', '--complete']), 0)
            self.assertEqual(main([*base, 'review', *identity, '--reviewer', 'reviewer', '--attest']), 0)
            self.assertEqual(main([*base, 'approve', *identity, '--reviewer', 'reviewer', '--attest']), 0)
            self.assertEqual(main([*base, 'compare', '--bindings', 'bindings.json', '--output-root', 'output']), 0)

    def test_manual_draft_review_approve_and_snapshots(self):
        state = self.add()
        self.assertEqual(state['status'], 'draft')
        self.assertEqual(state['version'], 1)
        draft_bytes = state['sidecar'].read_bytes()
        self.decision('review')
        approved = self.decision('approve')
        self.assertEqual(approved['status'], 'approved')
        self.assertEqual(state['sidecar'].read_bytes(), draft_bytes)
        self.assertEqual(approved['ground_truth']['review']['reviewer'], 'reviewer')

    def test_no_automatic_or_skipped_approval(self):
        self.add()
        with self.assertRaises(ValidationError):
            self.decision('approve')
        self.assertEqual(current(self.store, self.document, 1)['status'], 'draft')

    def test_transcriber_cannot_review_case_alias(self):
        self.add()
        with self.assertRaises(ValidationError):
            self.decision('review', actor='AUTHOR')

    def test_missing_attestations_rejected(self):
        with self.assertRaises(ValidationError):
            self.add(manual=False)
        self.add()
        with self.assertRaises(ValidationError):
            self.decision('review', attest=False)

    def test_incomplete_labels_block_review(self):
        self.add(complete=False)
        with self.assertRaises(ValidationError):
            self.decision('review')

    def test_empty_reference_missing_order_and_duplicate_order_rejected(self):
        self.text.write_bytes(b'')
        with self.assertRaises(ValidationError):
            self.add()
        self.text.write_text('synthetic', encoding='utf-8')
        with self.assertRaises(ValidationError):
            self.add(order=['right', 'right'])
        with self.assertRaises(ValidationError):
            submit(self.store, self.dataset, self.identifier, 1, self.text, transcriber='author',
                   reading_order=[], reason='synthetic', expected_version=0, complete=True, manual=True)

    def test_blank_reference_explicitly_approved_with_undefined_rates(self):
        self.text.write_bytes(b'')
        submit(self.store, self.dataset, self.identifier, 1, self.text, transcriber='author',
               reading_order=['blank page'], reason='synthetic blank', expected_version=0,
               complete=True, manual=True, is_blank=True)
        self.decision('review')
        self.decision('approve')
        _, report = self.compare()
        self.assertEqual(report['pages'][0]['status'], 'EVALUATED')
        self.assertIsNone(report['pages'][0]['evaluations']['strict-v1']['cer']['rate'])

    def test_stale_versions_and_wrong_approver_rejected(self):
        self.add()
        with self.assertRaises(ValidationError):
            self.add(expected=0)
        self.decision('review')
        with self.assertRaises(ValidationError):
            self.decision('approve', version=2)
        with self.assertRaises(ValidationError):
            self.decision('approve', actor='another-reviewer')

    def test_correction_preserves_history_and_resets_gate(self):
        self.add()
        self.decision('review')
        old = self.decision('approve')
        old_bytes = old['sidecar'].read_bytes()
        self.text.write_text('corrected synthetic Arabic API', encoding='utf-8')
        new = self.add(expected=1)
        self.assertEqual(new['version'], 2)
        self.assertEqual(new['status'], 'draft')
        self.assertEqual(old['sidecar'].read_bytes(), old_bytes)
        _, report = self.compare()
        self.assertEqual(report['pages'][0]['status'], 'NOT_EVALUATED')
        self.assertEqual(report['pages'][0]['reason'], 'GROUND_TRUTH_NOT_APPROVED')

    def test_transcript_tampering_detected(self):
        draft = self.add()
        (draft['sidecar'].parent / 'transcript.txt').write_text('changed', encoding='utf-8')
        with self.assertRaises(ValidationError):
            current(self.store, self.document, 1)

    def test_decision_tampering_detected(self):
        self.add()
        state = self.decision('review')
        state['sidecar'].write_text('{}', encoding='utf-8')
        with self.assertRaises(ValidationError):
            current(self.store, self.document, 1)

    def test_pending_and_reviewed_excluded_approved_evaluated(self):
        _, pending = self.compare()
        self.assertEqual(pending['pages'][0]['status'], 'NOT_EVALUATED')
        self.add()
        self.decision('review')
        _, reviewed = self.compare()
        self.assertEqual(reviewed['pages'][0]['status'], 'NOT_EVALUATED')
        self.decision('approve')
        _, approved = self.compare()
        self.assertEqual(approved['pages'][0]['status'], 'EVALUATED')
        self.assertEqual(set(approved['pages'][0]['evaluations']), {'strict-v1', 'normalized-v1'})


class AdapterTests(PilotFixture):
    def test_whole_region_line_import_preserves_raw_bytes(self):
        for kind, name in [('whole', 'baseline_psm3.txt'), ('regions', 'region_psm.txt'), ('lines', 'line_psm.txt')]:
            with self.subTest(kind=kind):
                raw, _, evidence = import_binding(self.root, self.dataset, {**self.binding, 'kind': kind})
                self.assertEqual(raw, (self.folder / name).read_bytes())
                self.assertIn(b'\r\n', raw)
                self.assertEqual(evidence['source_sha256'], self.document['source_sha256'])

    def test_v1_v2_region_order_and_assembly(self):
        for layout in ('v1', 'v2'):
            regions = []
            for index, region in enumerate(self.regions, 1):
                if layout == 'v1':
                    # v1 has no shared-header region; use only right/left columns.
                    if index == 1:
                        continue
                    regions.append({'reading_order': index - 1, 'bbox_xyxy': region['bbox']})
                else:
                    regions.append({**region, 'order': index})
            texts = ['يمين API', 'يسار'] if layout == 'v1' else ['عنوان', 'يمين API', 'يسار']
            report = {'page': 1, 'page_size': [100, 120], 'regions': regions}
            (self.folder / 'layout_report.json').write_text(json.dumps(report), encoding='utf-8')
            for index, text in enumerate(texts, 1):
                (self.folder / f'region_{index:02d}_ocr.txt').write_bytes((text + '\r\n').encode('utf-8'))
            aggregate = ('\n\n'.join(texts) + '\n').replace('\n', '\r\n').encode('utf-8')
            (self.folder / 'rtl_reading_order.txt').write_bytes(aggregate)
            raw, _, _ = import_binding(self.root, self.dataset, {**self.binding, 'layout': layout, 'kind': 'regions'})
            self.assertEqual(raw, aggregate)

    def test_wrong_page_directory_and_report_rejected(self):
        with self.assertRaises(ValidationError):
            import_binding(self.root, self.dataset, {**self.binding, 'page': 2})
        with self.assertRaisesRegex(ValidationError, 'Directory page'):
            import_binding(self.root, self.dataset, {**self.binding, 'directory': 'legacy/page_002'})
        self.report['page'] = 2
        self.write_metadata()
        with self.assertRaises(ValidationError):
            import_binding(self.root, self.dataset, self.binding)

    def test_wrong_original_pixels_rejected(self):
        Image.new('RGB', (100, 120), 'black').save(self.folder / 'original.png')
        with self.assertRaises(ValidationError):
            import_binding(self.root, self.dataset, self.binding)

    def test_ambiguous_identical_pages_rejected(self):
        other = copy.deepcopy(self.document)
        other['document_id'] = 'another-document'
        self.dataset['documents'].append(other)
        with self.assertRaises(ValidationError):
            import_binding(self.root, self.dataset, self.binding)

    def test_filename_guessing_and_duplicate_bindings_rejected(self):
        with self.assertRaises(ValidationError):
            import_binding(self.root, self.dataset, {'directory': 'legacy/page_001'})
        value = self.bindings()
        value['bindings'].append(copy.deepcopy(self.binding))
        with self.assertRaises(ValidationError):
            prepare(self.root, self.dataset, value, self.root / 'imports', self.store)

    def test_missing_line_labels_and_duplicate_order_rejected(self):
        original = copy.deepcopy(self.blocks)
        for mutation in ('missing', 'duplicate', 'geometry'):
            self.blocks = copy.deepcopy(original)
            if mutation == 'missing':
                del self.blocks[0]['text']
            elif mutation == 'duplicate':
                self.blocks[1]['region_order'] = 1
            else:
                self.blocks[1]['bbox'] = [0, 0, 1, 1]
            self.write_metadata()
            with self.subTest(mutation=mutation), self.assertRaises(ValidationError):
                import_binding(self.root, self.dataset, self.binding)

    def test_duplicate_json_line_labels_rejected(self):
        (self.folder / 'line_blocks.json').write_bytes(b'[{"text":"a","text":"b"}]')
        with self.assertRaisesRegex(ValidationError, 'duplicate JSON key'):
            import_binding(self.root, self.dataset, self.binding)

    def test_swapped_rtl_columns_rejected(self):
        self.report['regions'][1:3] = list(reversed(self.report['regions'][1:3]))
        self.write_metadata()
        with self.assertRaises(ValidationError):
            import_binding(self.root, self.dataset, self.binding)

    def test_changed_aggregate_rejected(self):
        (self.folder / 'line_psm.txt').write_text('wrong aggregation', encoding='utf-8')
        with self.assertRaises(ValidationError):
            import_binding(self.root, self.dataset, self.binding)

    def test_bundle_snapshots_and_provenance(self):
        before = {path: path.read_bytes() for path in self.folder.iterdir() if path.is_file()}
        bundle, report = self.compare()
        metadata = json.loads((bundle / 'associations.json').read_text(encoding='utf-8'))
        self.assertEqual(metadata['associations'][0]['gt_status'], 'PENDING')
        self.assertEqual((bundle / 'prediction_00001.txt').read_bytes(), (self.folder / 'line_psm.txt').read_bytes())
        self.assertEqual(report['pages'][0]['status'], 'NOT_EVALUATED')
        for path, raw in before.items():
            self.assertEqual(path.read_bytes(), raw)


if __name__ == '__main__':
    unittest.main()
