"""Characterize legacy behavior; known limitations are not desired new contracts.

No OCR subprocess, model download or historical-output writes are performed.
These checks intentionally make policy differences visible before extraction.
"""
import importlib.util
from pathlib import Path
import tempfile
import unittest

from PIL import Image
import layout_ocr_v03

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('legacy_baseline', ROOT / 'src/run_ocr.py')
baseline = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(baseline)


class LegacyMetricTests(unittest.TestCase):
    def test_arabic_identity_and_diacritic_difference(self):
        self.assertEqual(baseline.metrics('كتاب', 'كتاب'), {'cer': 0.0, 'wer': 0.0})
        self.assertGreater(baseline.metrics('كتاب', 'كِتاب')['cer'], 0)

    def test_insert_delete_substitute_denominators(self):
        for prediction, reference in [('abcd', 'abc'), ('ab', 'abc'), ('axc', 'abc')]:
            with self.subTest(prediction=prediction):
                self.assertAlmostEqual(baseline.metrics(prediction, reference)['cer'], 1 / 3)
        self.assertEqual(baseline.metrics('one three', 'one two')['wer'], 0.5)

    def test_known_whitespace_policy_difference(self):
        self.assertEqual(baseline.metrics('a b', 'a\nb')['cer'], 0)
        self.assertEqual(layout_ocr_v03.metrics('a\nb', 'a b')['cer'], 0.3333)

    def test_known_empty_reference_policy(self):
        # Current behavior only: benchmark must explicitly decide blank-page policy.
        self.assertEqual(baseline.metrics('abc', '')['cer'], 3)

    def test_known_bom_difference(self):
        self.assertGreater(baseline.metrics('abc', '\ufeffabc')['cer'], 0)


class LegacyRasterTests(unittest.TestCase):
    def test_known_multiframe_tiff_limitation(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'two_pages.tiff'
            first = Image.new('RGB', (32, 32), 'white')
            second = Image.new('RGB', (32, 32), 'black')
            first.save(path, save_all=True, append_images=[second])
            with Image.open(path) as image:
                self.assertEqual(image.n_frames, 2)
            self.assertEqual(len(list(baseline.iter_pages(path, 300))), 1)


if __name__ == '__main__':
    unittest.main()
