"""Quality assessment, preprocessing transforms, OCR adapters and degradation (Task 006).

Synthetic pages are generated in-test so assertions do not depend on private documents.
"""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from smartarchive.config import find_tesseract
from smartarchive.processing.degrade import LEVELS, degrade
from smartarchive.processing.ocr import Word, mean_confidence
from smartarchive.processing.preprocess import Prepared, prepare
from smartarchive.processing.quality import assess, rotate
from smartarchive.processing.render import page_images

WORDS = 'archive record letter decision contract invoice report meeting minutes department'.split()


def text_page(columns=1, width=1654, height=2339, size=34, table=False, seed=3) -> Image.Image:
    """A clean A4 page at ~200 dpi with real glyphs in one or more columns."""
    rng = np.random.default_rng(seed)
    page = Image.new('RGB', (width, height), 'white')
    draw = ImageDraw.Draw(page)
    font = ImageFont.load_default(size=size)
    margin, gutter = 120, 140
    col_width = (width - 2 * margin - gutter * (columns - 1)) // columns
    for column in range(columns):
        x0 = margin + column * (col_width + gutter)
        y = 160
        while y < height - 600:
            line, x = [], x0
            while True:
                word = WORDS[int(rng.integers(len(WORDS)))]
                advance = draw.textlength(word + ' ', font=font)
                if x + advance > x0 + col_width:
                    break
                line.append(word)
                x += advance
            draw.text((x0, y), ' '.join(line), fill='black', font=font)
            y += int(size * 1.9)
    if table:
        top, left, right = height - 520, margin, width - margin
        for row in range(5):
            draw.line([(left, top + row * 90), (right, top + row * 90)], fill='black', width=4)
        for col in range(4):
            x = left + col * (right - left) // 3
            draw.line([(x, top), (x, top + 360)], fill='black', width=4)
    return page


class QualityTests(unittest.TestCase):
    def test_clean_page_scores_high_and_reports_all_terms(self):
        quality = assess(text_page(), 200)
        self.assertFalse(quality.blank)
        self.assertGreater(quality.sharpness, 0.7)
        self.assertGreater(quality.contrast, 0.9)
        self.assertAlmostEqual(quality.resolution, 0.5, places=2)
        self.assertAlmostEqual(quality.skew_angle, 0.0, delta=0.3)
        self.assertEqual(quality.columns, 1)
        expected = sum(0.2 * v for v in (quality.sharpness, quality.contrast, quality.resolution,
                                         quality.skew, quality.layout_simplicity))
        self.assertAlmostEqual(quality.score, expected, places=3)
        self.assertIn(quality.route, ('fast', 'layout', 'advanced'))
        self.assertEqual(quality.raw['route_thresholds'], {'fast': 0.8, 'layout': 0.55})

    def test_degradations_lower_the_matching_terms(self):
        page = text_page()
        clean = assess(page, 300)
        blurred = assess(page.filter(ImageFilter.GaussianBlur(3)), 300)
        self.assertLess(blurred.sharpness, clean.sharpness)
        faded = Image.fromarray((255 - (255 - np.asarray(page)) * 0.25).astype(np.uint8))
        self.assertLess(assess(faded, 300).contrast, clean.contrast)
        self.assertLess(assess(page, 120).resolution, clean.resolution)
        self.assertLess(assess(page.filter(ImageFilter.GaussianBlur(3)), 120).score, clean.score)

    def test_skew_is_measured_with_sign(self):
        page = text_page()
        for angle in (3.0, -4.0):
            with self.subTest(angle=angle):
                tilted = page.rotate(angle, expand=True, fillcolor='white')
                quality = assess(tilted, 300)
                # The estimate is the counter-clockwise correction that straightens the page.
                self.assertAlmostEqual(quality.skew_angle, -angle, delta=0.4)
                self.assertLess(quality.skew, 0.5)

    def test_layout_detects_columns_and_tables(self):
        self.assertEqual(assess(text_page(columns=2), 300).columns, 2)
        two = assess(text_page(columns=2), 300)
        self.assertEqual(two.layout, 'multi_column')
        self.assertLess(two.layout_simplicity, 1.0)
        tabular = assess(text_page(table=True), 300)
        self.assertTrue(tabular.has_table)
        self.assertEqual(tabular.layout, 'tabular')

    def test_blank_page_is_flagged(self):
        quality = assess(Image.new('RGB', (800, 1100), 'white'), 300)
        self.assertTrue(quality.blank)
        noise = np.random.default_rng(1).normal(240, 3, (1100, 800)).clip(0, 255).astype(np.uint8)
        self.assertTrue(assess(Image.fromarray(noise).convert('RGB'), 300).blank)

    def test_sparse_letter_is_not_blank(self):
        # Regression: an official letter has ~1% ink, so both histogram tails are paper.
        page = Image.new('RGB', (1654, 2339), 'white')
        draw, font = ImageDraw.Draw(page), ImageFont.load_default(size=38)
        for row in range(6):
            draw.text((300, 400 + row * 78), 'archive decision letter', fill='#111', font=font)
        self.assertLess((np.asarray(page.convert('L')) < 128).mean(), 0.02)
        quality = assess(page, 200)
        self.assertFalse(quality.blank)
        self.assertGreater(quality.contrast, 0.9)


class PreprocessTests(unittest.TestCase):
    def test_deskew_and_exact_mapping_back_to_original(self):
        page = text_page()
        tilted = page.rotate(3, expand=True, fillcolor='white')
        quality = assess(tilted, 300)
        prepared = prepare(tilted, quality, tesseract_cmd=None)
        self.assertEqual([s['step'] for s in prepared.steps], ['orientation', 'deskew', 'binarization'])
        self.assertFalse(prepared.steps[-1]['applied'])
        # A known point in the original survives the round trip through the matrix.
        point = np.array([500.0, 700.0, 1.0])
        forward = prepared.matrix @ point
        box = (forward[0] - 1, forward[1] - 1, forward[0] + 1, forward[1] + 1)
        x0, y0, x1, y1 = prepared.to_original(box, *tilted.size)
        self.assertAlmostEqual((x0 + x1) / 2 * tilted.width, 500, delta=2)
        self.assertAlmostEqual((y0 + y1) / 2 * tilted.height, 700, delta=2)

    def test_identity_when_page_is_straight_and_boxes_are_normalised(self):
        page = text_page()
        prepared = prepare(page, assess(page, 300), tesseract_cmd=None)
        self.assertTrue(np.allclose(prepared.matrix, np.eye(3)))
        self.assertEqual(prepared.to_original((0, 0, page.width, page.height), *page.size), (0.0, 0.0, 1.0, 1.0))

    def test_rotate_keeps_whole_page(self):
        array = np.zeros((100, 200, 3), np.uint8)
        rotated, _ = rotate(array, 90, (255, 255, 255))
        self.assertEqual(rotated.shape[:2], (200, 100))


class OcrAdapterTests(unittest.TestCase):
    def test_mean_confidence_is_character_weighted_and_ignores_missing(self):
        words = [Word('aaaa', 0.9, (0, 0, 1, 1)), Word('b', 0.1, (0, 0, 1, 1)), Word('ccc', None, (0, 0, 1, 1))]
        self.assertAlmostEqual(mean_confidence(words), (0.9 * 4 + 0.1) / 5, places=4)
        self.assertIsNone(mean_confidence([Word('x', None, (0, 0, 1, 1))]))

    @unittest.skipUnless(find_tesseract(), 'Tesseract is not installed')
    def test_real_tesseract_reads_a_clean_english_page(self):
        from smartarchive.processing.ocr import TesseractEngine
        engine = TesseractEngine(find_tesseract(), 'eng', timeout=120)
        page = text_page(size=40).crop((0, 0, 1654, 700))
        lines = engine.recognize(page)
        text = ' '.join(line.text for line in lines).lower()
        self.assertGreaterEqual(sum(word in text for word in WORDS), 5)
        self.assertTrue(all(line.confidence is None or 0 <= line.confidence <= 1 for line in lines))
        self.assertTrue(all(line.box[2] > line.box[0] and line.box[3] > line.box[1] for line in lines))


class RenderAndDegradeTests(unittest.TestCase):
    def test_image_dpi_from_metadata_or_labelled_estimate(self):
        with tempfile.TemporaryDirectory() as folder:
            tagged, plain = Path(folder) / 'tagged.png', Path(folder) / 'plain.png'
            Image.new('RGB', (1240, 1754), 'white').save(tagged, dpi=(150, 150))
            Image.new('RGB', (1240, 1754), 'white').save(plain)
            (_, _, dpi, source), = page_images(tagged, 'image/png', 300)
            self.assertEqual((round(dpi), source), (150, 'metadata'))
            (_, _, dpi, source), = page_images(plain, 'image/png', 300)
            self.assertEqual((round(dpi), source), (150, 'estimated_a4'))

    def test_degradation_is_seeded_recorded_and_ordered_by_severity(self):
        page = text_page()
        first, again = degrade(page, 'medium', 11), degrade(page, 'medium', 11)
        self.assertEqual(first.params, again.params)
        self.assertTrue(np.array_equal(np.asarray(first.image), np.asarray(again.image)))
        self.assertNotEqual(degrade(page, 'medium', 12).params, first.params)
        self.assertEqual(degrade(page, 'clean', 1).params, {'seed': 1})
        scores = [assess(degrade(page, level, 5).image, 300 * LEVELS[level].get('dpi_scale', 1)).score
                  for level in ('clean', 'mild', 'severe')]
        self.assertGreater(scores[0], scores[1])
        self.assertGreater(scores[1], scores[2])
        with self.assertRaises(ValueError):
            degrade(page, 'extreme', 1)


if __name__ == '__main__':
    unittest.main()
