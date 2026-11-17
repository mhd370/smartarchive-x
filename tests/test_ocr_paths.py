"""OCR paths (ocr-paths-v1): page variants, box mapping, the choice rules and the confidence gate."""
from pathlib import Path
import sys
import unittest

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from smartarchive.processing import paths  # noqa: E402
from smartarchive.processing.ocr import Line, Word  # noqa: E402


def page() -> Image.Image:
    image = Image.new('RGB', (400, 300), (235, 230, 220))
    ImageDraw.Draw(image).rectangle((50, 50, 350, 70), fill=(90, 90, 90))
    return image


class FakeEngine:
    """Confidence depends on the variant it is given, so the choice can be checked."""
    def __init__(self, name='default'):
        self.name, self.calls = name, []

    def recognize(self, image):
        binary = set(np.unique(np.asarray(image.convert('L'))).tolist()) <= {0, 255}
        self.calls.append((image.size, binary))
        if self.name == 'ara':
            words = [Word('نص', 0.5, (10, 10, 40, 30))]
        elif binary:
            words = [Word('كتاب', 0.9, (10, 10, 60, 30)), Word('رسمي', 0.9, (70, 10, 120, 30))]
        elif image.size[0] > 400:
            words = [Word('كتاب', 0.8, (30, 30, 90, 60))]
        else:
            words = [Word('كتب', 0.6, (10, 10, 60, 30))]
        return [Line(' '.join(w.text for w in words), None, words[0].box, words)]


def plain(engine, image):
    return engine.recognize(image), {'step': 'layout', 'tables': [{'box': [0, 0, 300, 150]}]}


class PathTests(unittest.TestCase):
    def test_variants_keep_geometry_and_never_change_the_input(self):
        source = page()
        before = source.tobytes()
        binary = paths.variant('binarized', source)
        self.assertEqual(binary.image.size, source.size)
        self.assertLessEqual(set(np.unique(np.asarray(binary.image.convert('L'))).tolist()), {0, 255})
        self.assertEqual(paths.variant('upscaled', source).image.size, (600, 450))
        self.assertEqual(paths.variant('model-ara', source).languages, 'ara')
        self.assertEqual(source.tobytes(), before)
        with self.assertRaises(ValueError):
            paths.variant('nope', source)
        line = Line('a', 0.9, (30, 30, 90, 60), [Word('a', 0.9, (30, 30, 90, 60))])
        self.assertEqual(paths.rescale([line], 1.5)[0].words[0].box, (20, 20, 60, 40))

    def test_choice_rules(self):
        short = [Line('a', None, (0, 0, 1, 1), [Word('ab', 0.95, (0, 0, 1, 1))])]
        long = [Line('b', None, (0, 0, 1, 1), [Word('abcdefgh', 0.7, (0, 0, 1, 1))])]
        results = {'standard': short, 'upscaled': long}
        self.assertEqual(paths.choose(results, 'confidence'), 'standard')
        self.assertEqual(paths.choose(results, 'confident-chars'), 'upscaled')
        self.assertEqual(paths.choose({'standard': short, 'binarized': short}, 'confidence'), 'standard')  # tie

    def test_read_chooses_maps_boxes_and_respects_the_gate(self):
        default, ara = FakeEngine(), FakeEngine('ara')
        engine_for = lambda languages: ara if languages == 'ara' else default
        lines, steps = paths.read(engine_for, page(), paths.PATHS, 'confidence', 1.0, plain)
        self.assertEqual(steps['paths']['chosen'], 'binarized')
        self.assertEqual(set(steps['paths']['tried']), set(paths.PATHS))
        self.assertEqual(lines[0].text, 'كتاب رسمي')
        self.assertEqual(len(ara.calls), 1)  # model-ara used its own engine
        _, steps = paths.read(engine_for, page(), ('standard', 'upscaled'), 'confidence', 1.0, plain)
        self.assertEqual(steps['paths']['chosen'], 'upscaled')
        self.assertEqual(steps['layout']['tables'][0]['box'], [0, 0, 200, 100])  # back to prepared pixels
        # Gate: the standard page is confident enough (0.6 >= 0.5), so nothing else is read.
        default.calls.clear()
        _, steps = paths.read(engine_for, page(), paths.PATHS, 'confidence', 0.5, plain)
        self.assertEqual((steps['paths']['chosen'], len(default.calls)), ('standard', 1))


class RegionTests(unittest.TestCase):
    def test_headings_stamps_and_figures(self):
        from smartarchive.processing import regions
        image = Image.new('RGB', (1000, 1400), 'white')
        draw = ImageDraw.Draw(image)
        line = lambda text, box: Line(text, 0.9, box, [Word(text, 0.9, box)])
        lines = [line('الجمهورية', (420, 60, 580, 90)), line('وزارة الإدارة', (400, 100, 600, 130)),  # letterhead
                 line('رقم الكتاب ١٢', (700, 200, 900, 225)),                                         # right-aligned
                 line('الموضوع: طلب صيانة', (380, 300, 620, 335))]                                     # title
        lines += [line('نص الفقرة ' * 6, (100, 400 + 40 * i, 900, 430 + 40 * i)) for i in range(8)]  # paragraphs
        lines.append(line('صفحة ١ من ١', (450, 1340, 550, 1360)))                                       # footer
        for y in range(400, 720, 40):
            draw.rectangle((100, y, 900, y + 25), fill='black')
        draw.ellipse((150, 900, 330, 1080), outline=(50, 60, 180), width=6)      # blue stamp ring
        draw.ellipse((165, 915, 315, 1065), outline=(50, 60, 180), width=4)      # its inner ring
        draw.rectangle((600, 950, 900, 1000), fill='black')                       # a signature-like figure
        found = regions.find(image, lines)
        heads = [r for r in found if r['kind'] == 'heading']
        self.assertEqual([h['lines'] for h in heads], [2, 1])
        self.assertTrue(heads[1]['text'].startswith('الموضوع'))
        stamps = [r for r in found if r['kind'] == 'stamp']
        self.assertEqual(len(stamps), 1)
        self.assertTrue(stamps[0]['coloured'])
        self.assertTrue(any(r['kind'] == 'figure' and r['box'][0] >= 590 for r in found))
        # A table's grid is a table, not a figure.
        self.assertFalse(any(r['kind'] == 'figure' for r in regions.find(image, lines, [(90, 390, 910, 730)])
                             if r['box'][1] < 750))


if __name__ == '__main__':
    unittest.main()
