"""Page layout analysis (`layout-v1`): ruled tables and two-column text, for right-to-left reading order.

Tesseract's own page segmentation (psm 3) reads most pages well. It has two systematic failures on
institutional documents:
- In a ruled table it groups text by column, so a row's cells come out far apart. Tables are found from
  their ruling lines: horizontal and vertical strokes isolated with morphological opening, and the row and
  column positions where those lines span most of the table. Each cell is read on its own (`psm 6`), and a
  row is written as its cells from right to left. A missing vertical line inside a row merges cells. The
  table area is blanked before the rest of the page is read, and the rows are placed where the table was.
- On two-column text it sometimes reads straight across the gutter. A gutter is a vertical band, in the
  middle 30–70% of the text body, that is empty on many text rows that have ink on both sides of it. Only
  lines psm 3 actually merged (words on both sides with a column-sized gap at the gutter) trigger
  reordering. Those lines are split there, and the section is read right column first, then left.

Everything else keeps psm 3's order. Development set results are in docs/synthetic_evaluation.md.
"""
from dataclasses import dataclass, field

import numpy as np
from PIL import Image, ImageDraw, ImageOps

from .ocr import Line, Word, mean_confidence

METHOD = 'layout-v1'


@dataclass
class Table:
    box: tuple[int, int, int, int]
    rows: list[int]
    cols: list[int]
    vertical: np.ndarray = field(repr=False)


def _ink(gray: np.ndarray) -> np.ndarray:
    import cv2
    _, ink = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    return ink


def _positions(profile: np.ndarray, min_fill: float) -> list[int]:
    groups: list[list[int]] = []
    for i in np.where(profile >= min_fill)[0]:
        if groups and i - groups[-1][-1] <= 3:
            groups[-1].append(int(i))
        else:
            groups.append([int(i)])
    return [int(np.mean(g)) for g in groups]


def find_tables(gray: np.ndarray) -> list[Table]:
    """Ruled tables at least a quarter of the page wide with two or more row and column lines."""
    import cv2
    ink = _ink(gray)
    h, w = gray.shape
    horizontal = cv2.morphologyEx(ink, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (max(20, w // 25), 1)))
    vertical = cv2.morphologyEx(ink, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(15, h // 60))))
    grid = cv2.dilate(cv2.bitwise_or(horizontal, vertical), np.ones((5, 5), np.uint8))
    count, _, stats, _ = cv2.connectedComponentsWithStats(grid)
    tables = []
    for i in range(1, count):
        x, y, bw, bh, _ = (int(v) for v in stats[i])
        if bw < w * 0.25 or bh < h * 0.03:
            continue
        rows = _positions((horizontal[y:y + bh, x:x + bw] > 0).sum(axis=1), bw * 0.5)
        cols = _positions((vertical[y:y + bh, x:x + bw] > 0).sum(axis=0), bh * 0.5)
        if len(rows) >= 2 and len(cols) >= 2:
            tables.append(Table((x, y, x + bw, y + bh), [y + r for r in rows], [x + c for c in cols], vertical))
    return sorted(tables, key=lambda t: t.box[1])


def find_columns(gray: np.ndarray, exclude=(), step: int = 4, margin: float = 0.05, min_height: float = 0.08,
                 balance: float = 0.3) -> tuple[float, int, int] | None:
    """The main two-column section as (gutter x, top, bottom) in page pixels, or None."""
    import cv2
    ink = _ink(gray)
    h0, w0 = gray.shape
    mx, my = int(w0 * margin), int(h0 * margin * 0.5)
    ink[:, :mx] = 0
    ink[:, w0 - mx:] = 0
    ink[:my] = 0
    ink[h0 - my:] = 0  # page edges, shadows and scanner borders are not text
    for x0, y0, x1, y1 in exclude:
        ink[y0:y1, x0:x1] = 0
    ink = cv2.morphologyEx(ink, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
    small = ink[::step, ::step] > 0
    rows_n, cols_n = small.shape
    used = np.where(small.sum(axis=0) > 0)[0]
    if len(used) == 0:
        return None
    width = max(3, int(cols_n * 0.012))
    cs = np.concatenate([np.zeros((rows_n, 1), int), np.cumsum(small, axis=1)], axis=1)
    window = cs[:, width:] - cs[:, :cols_n + 1 - width]
    left = cs[:, :cols_n + 1 - width]
    right = cs[:, -1:] - cs[:, width:]
    gutter = (window == 0) & (left > 0) & (right > 0)
    has_ink = small.any(axis=1)
    lo = int(used[0] + (used[-1] - used[0]) * 0.3)
    hi = min(int(used[0] + (used[-1] - used[0]) * 0.7), cols_n - width)
    best = None
    for x in range(lo, hi):
        count, start, lsum, rsum = 0, None, 0, 0
        for y in range(rows_n):
            if not has_ink[y] or (window[y, x] == 0 and not gutter[y, x]):
                continue  # a blank row, or text on one side only (the end of a paragraph): neutral
            if gutter[y, x]:
                if start is None:
                    start, lsum, rsum = y, 0, 0
                count += 1
                lsum += left[y, x]
                rsum += right[y, x]
                if (best is None or count > best[0]) and min(lsum, rsum) >= balance * max(lsum, rsum):
                    best = (count, x, start, y)
            else:
                start, count = None, 0  # a line crosses the band: not a gutter here
    if not best:
        return None
    count, x, top, bottom = best
    if (bottom - top) * step < h0 * min_height or count * step < h0 * 0.03:
        return None
    return ((x + width / 2) * step, top * step, (bottom + 1) * step)


def _split(line: Line, gutter: float, min_gap: float):
    right = [w for w in line.words if (w.box[0] + w.box[2]) / 2 >= gutter]
    left = [w for w in line.words if (w.box[0] + w.box[2]) / 2 < gutter]
    if not right or not left:
        return None
    gap = min(w.box[0] for w in right) - max(w.box[2] for w in left)
    return (right, left) if gap >= min_gap else None


def _line(words: list[Word]) -> Line:
    box = (min(w.box[0] for w in words), min(w.box[1] for w in words),
           max(w.box[2] for w in words), max(w.box[3] for w in words))
    return Line(' '.join(w.text for w in words), mean_confidence(words), box, words)


def reorder_columns(lines: list[Line], section, width: int) -> tuple[list[Line], int]:
    """Split the lines psm 3 merged across the gutter; returns the lines and how many were merged."""
    if not section:
        return lines, 0
    gutter, top, bottom = section
    min_gap = width * 0.02
    centre = lambda line: (line.box[1] + line.box[3]) / 2  # noqa: E731
    inside = [i for i, line in enumerate(lines) if top <= centre(line) <= bottom]
    merged = [i for i in inside if _split(lines[i], gutter, min_gap)]
    if len(merged) < 3:
        return lines, 0
    lo, hi = min(merged), max(merged)
    right, left = [], []
    for line in lines[lo:hi + 1]:
        parts = _split(line, gutter, min_gap)
        if parts:
            right.append(_line(parts[0]))
            left.append(_line(parts[1]))
        elif (line.box[0] + line.box[2]) / 2 >= gutter:
            right.append(line)
        else:
            left.append(line)
    right.sort(key=centre)
    left.sort(key=centre)
    return lines[:lo] + right + left + lines[hi + 1:], len(merged)


def _offset(lines: list[Line], dx: int, dy: int) -> list[Word]:
    return [Word(w.text, w.confidence, (w.box[0] + dx, w.box[1] + dy, w.box[2] + dx, w.box[3] + dy))
            for line in lines for w in line.words]


def table_lines(engine, image: Image.Image, table: Table, inset: int = 4, pad: int = 15) -> list[Line]:
    """One line per table row: each cell read separately, cells from right to left."""
    out = []
    gray = image.convert('L')
    for r0, r1 in zip(table.rows, table.rows[1:]):
        if r1 - r0 < 12:
            continue
        band = table.vertical[r0 + 3:r1 - 3]
        present = [c for c in table.cols if band.size and (band[:, max(0, c - 3):c + 4] > 0).any(axis=1).mean() > 0.6]
        if len(present) < 2:
            present = [table.cols[0], table.cols[-1]]
        words: list[Word] = []
        for c0, c1 in reversed(list(zip(present, present[1:]))):
            if c1 - c0 < 10:
                continue
            x0, y0 = c0 + inset, r0 + inset
            cell = gray.crop((x0, y0, c1 - inset, r1 - inset))
            pixels = np.asarray(cell)
            if pixels.size == 0 or (pixels < np.median(pixels) - 40).sum() < 15:
                continue  # empty cell
            words += _offset(engine.recognize_block(ImageOps.expand(cell, border=pad, fill=255)), x0 - pad, y0 - pad)
        if words:
            out.append(_line(words))
    return out


def read_page(engine, image: Image.Image) -> tuple[list[Line], dict]:
    """Lines in reading order and what layout analysis found. Engines without `recognize_block` get psm 3 only."""
    if not hasattr(engine, 'recognize_block'):
        return engine.recognize(image), {'step': 'layout', 'method': 'none', 'reason': 'engine_without_blocks'}
    gray = np.asarray(image.convert('L'))
    tables = find_tables(gray)
    section = find_columns(gray, [t.box for t in tables])
    page = image
    if tables:
        page = image.convert('RGB').copy()
        draw = ImageDraw.Draw(page)
        for table in tables:
            draw.rectangle(table.box, fill=(255, 255, 255))
    lines, merged = reorder_columns(engine.recognize(page), section, image.width)
    out, placed = [], set()
    for line in lines:
        centre = (line.box[1] + line.box[3]) / 2
        for i, table in enumerate(tables):
            if i not in placed and centre > table.box[3]:
                out += table_lines(engine, image, table)
                placed.add(i)
        out.append(line)
    for i, table in enumerate(tables):
        if i not in placed:
            out += table_lines(engine, image, table)
    info = {'step': 'layout', 'method': METHOD,
            'tables': [{'box': list(t.box), 'rows': len(t.rows) - 1, 'columns': len(t.cols) - 1} for t in tables],
            'columns': ({'gutter_x': round(section[0]), 'top': section[1], 'bottom': section[2], 'merged_lines': merged}
                        if section and merged else None)}
    return out, info
