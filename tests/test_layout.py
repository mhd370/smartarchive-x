"""Layout analysis (layout-v1): ruled tables read cell by cell right to left, two-column reading order."""
from pathlib import Path
import sys
import unittest

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from smartarchive.processing import layout  # noqa: E402
from smartarchive.processing.ocr import Line, Word  # noqa: E402

W, H = 1600, 2200


def table_page():
    """A 3x3 ruled table; each cell holds a small block whose position encodes (row, column)."""
    image = Image.new('L', (W, H), 255)
    draw = ImageDraw.Draw(image)
    x0, y0, cw, rh = 200, 600, 400, 100
    for i in range(4):
        draw.line((x0, y0 + i * rh, x0 + 3 * cw, y0 + i * rh), fill=0, width=3)
        draw.line((x0 + i * cw, y0, x0 + i * cw, y0 + 3 * rh), fill=0, width=3)
    for r in range(3):
        for c in range(3):
            draw.rectangle((x0 + c * cw + 150, y0 + r * rh + 35, x0 + c * cw + 250, y0 + r * rh + 65), fill=0)
    draw.rectangle((300, 200, 1300, 230), fill=0)  # a line of "text" above the table
    return image


def column_page():
    """Two text columns separated by an empty gutter, with full-width lines above."""
    image = Image.new('L', (W, H), 255)
    draw = ImageDraw.Draw(image)
    draw.rectangle((200, 200, 1400, 230), fill=0)
    for i in range(14):
        y = 400 + i * 60
        draw.rectangle((860, y, 1400, y + 28), fill=0)   # right column
        draw.rectangle((200, y, 740, y + 28), fill=0)    # left column
    return image


class CellEngine:
    """Reads a cell as the label of the block it contains, from where the block sits on the page."""
    def __init__(self, page_offsets):
        self.calls = []

    def recognize(self, image):
        return [Line('فوق', 0.9, (300, 200, 1300, 230), [Word('فوق', 0.9, (300, 200, 1300, 230))])]

    def recognize_block(self, image):
        self.calls.append(image.size)
        return [Line('x', 0.9, (150, 30, 250, 60), [Word('x', 0.9, (150, 30, 250, 60))])]


class TableTests(unittest.TestCase):
    def test_table_found_and_rows_read_right_to_left(self):
        page = table_page()
        tables = layout.find_tables(np.asarray(page))
        self.assertEqual(len(tables), 1)
        self.assertEqual((len(tables[0].rows), len(tables[0].cols)), (4, 4))
        engine = CellEngine(None)
        lines, info = layout.read_page(engine, page)
        self.assertEqual(info['tables'][0]['rows'], 3)
        self.assertEqual(len(engine.calls), 9)  # every cell on its own
        self.assertEqual([line.text for line in lines], ['فوق', 'x x x', 'x x x', 'x x x'])
        row = lines[1]
        self.assertGreater(row.words[0].box[0], row.words[-1].box[0])  # first word is the rightmost cell
        self.assertTrue(600 <= row.box[1] < row.box[3] <= 700)  # boxes are back in page coordinates

    def test_plain_page_has_no_table_or_columns(self):
        page = Image.new('L', (W, H), 255)
        draw = ImageDraw.Draw(page)
        for i in range(20):
            draw.rectangle((200, 300 + i * 60, 1400, 328 + i * 60), fill=0)
        gray = np.asarray(page)
        self.assertEqual(layout.find_tables(gray), [])
        self.assertIsNone(layout.find_columns(gray))


class ColumnTests(unittest.TestCase):
    def test_gutter_found(self):
        section = layout.find_columns(np.asarray(column_page()))
        self.assertIsNotNone(section)
        gutter, top, bottom = section
        self.assertTrue(740 < gutter < 860)
        self.assertTrue(top <= 420 and bottom >= 1150)

    def test_merged_lines_are_split_right_column_first(self):
        def merged(i):
            y = 400 + i * 60
            right, left = Word(f'R{i}', 0.9, (860, y, 1400, y + 28)), Word(f'L{i}', 0.9, (200, y, 740, y + 28))
            return Line(f'R{i} L{i}', 0.9, (200, y, 1400, y + 28), [right, left])
        lines = [Line('T', 0.9, (200, 200, 1400, 230), [Word('T', 0.9, (200, 200, 1400, 230))])]
        lines += [merged(i) for i in range(4)]
        out, count = layout.reorder_columns(lines, (800, 380, 700), W)
        self.assertEqual(count, 4)
        self.assertEqual([line.text for line in out], ['T', 'R0', 'R1', 'R2', 'R3', 'L0', 'L1', 'L2', 'L3'])
        # Lines psm 3 already kept apart (no column gap inside a line) are left alone.
        title = Line('a b', 0.9, (500, 400, 1100, 428), [Word('a', 0.9, (810, 400, 1100, 428)),
                                                          Word('b', 0.9, (500, 400, 790, 428))])
        self.assertEqual(layout.reorder_columns([title] * 3, (800, 380, 700), W), ([title] * 3, 0))

    def test_engine_without_blocks_falls_back(self):
        class Plain:
            def recognize(self, image):
                return []
        lines, info = layout.read_page(Plain(), column_page())
        self.assertEqual((lines, info['method']), ([], 'none'))


if __name__ == '__main__':
    unittest.main()
