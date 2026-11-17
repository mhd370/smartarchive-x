"""Heading and image regions of a page (`regions-v1`, ADR 0016), next to the tables and columns of layout.py.

- **Headings**: centred lines of the OCR output (letterhead, subject, title). A line is centred when its centre
  is within 6% of the text block's width from the block's centre and it is narrower than 80% of the block;
  consecutive centred lines close together form one region. Lines in the bottom 7% of the page (footers and
  page numbers) and lines inside tables are left out.
- **Stamps**: ink components roughly as wide as tall (aspect 0.6–1.6), between 5% and 30% of the page width,
  and mostly hollow (ink fills under 35% of the box), like the rings of an official stamp. Coloured ink
  (blue/red/violet) is a stamp at any fill.
- **Figures**: other large ink components outside tables (logos, signatures drawn as strokes, photos), at least
  12% of the page width or 6% of its height, and not a thin ruling line.
Boxes are in the pixels of the image given; the pipeline maps them back to the original page. The regions are
evidence shown to people; nothing in the archive depends on them. Measured on the synthetic corpora against the
ground-truth header/title and stamp blocks (tools/region_experiment.py).
"""
import statistics

import cv2
import numpy as np
from PIL import Image

METHOD = 'regions-v1'
CENTRE_TOLERANCE = 0.06
MAX_HEADING_WIDTH = 0.8
FOOTER_ZONE = 0.93


def _inside(box, tables) -> bool:
    cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
    return any(t[0] <= cx <= t[2] and t[1] <= cy <= t[3] for t in tables)


def headings(lines, height: int, tables=()) -> list[dict]:
    lines = [l for l in lines if l.text.strip() and not _inside(l.box, tables)]
    if len(lines) < 2:
        return []
    lefts = sorted(l.box[0] for l in lines)
    rights = sorted(l.box[2] for l in lines)
    left, right = lefts[len(lefts) // 20], rights[-1 - len(rights) // 20]
    width = right - left
    if width <= 0:
        return []
    centre = (left + right) / 2
    line_height = statistics.median(l.box[3] - l.box[1] for l in lines)
    regions: list[dict] = []
    for line in sorted(lines, key=lambda l: l.box[1]):
        x0, y0, x1, y1 = line.box
        if y1 > height * FOOTER_ZONE:
            continue
        span = x1 - x0
        if not (0.04 * width <= span <= MAX_HEADING_WIDTH * width and abs((x0 + x1) / 2 - centre) <= CENTRE_TOLERANCE * width):
            continue
        last = regions[-1] if regions else None
        if last and y0 - last['box'][3] <= 1.5 * line_height:
            b = last['box']
            last['box'] = [min(b[0], x0), min(b[1], y0), max(b[2], x1), max(b[3], y1)]
            last['lines'] += 1
            last['text'] += '\n' + line.text
        else:
            regions.append({'kind': 'heading', 'box': [x0, y0, x1, y1], 'lines': 1, 'text': line.text})
    return regions


def graphics(image: Image.Image, tables=()) -> list[dict]:
    rgb = np.asarray(image.convert('RGB'))
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    height, width = gray.shape
    _, ink = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    coloured = (hsv[..., 1] > 80) & (hsv[..., 2] < 235) & (ink > 0)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(ink, connectivity=8)
    out = []
    for index in range(1, count):
        x, y, w, h, area = stats[index]
        box = [int(x), int(y), int(x + w), int(y + h)]
        if _inside(box, tables) or any(_overlap(box, t) > 0.5 for t in tables):
            continue
        aspect = w / max(1, h)
        fill = area / max(1, w * h)
        colour = coloured[y:y + h, x:x + w][labels[y:y + h, x:x + w] == index].mean() if area else 0.0
        if 0.6 <= aspect <= 1.6 and 0.05 * width <= w <= 0.3 * width and (fill < 0.35 or colour > 0.5):
            out.append({'kind': 'stamp', 'box': box, 'coloured': bool(colour > 0.5)})
        elif ((w >= 0.12 * width or h >= 0.06 * height) and min(w, h) >= 0.015 * width
              and not (w >= 0.9 * width and h >= 0.9 * height)):  # not a ruling line, not the page border
            out.append({'kind': 'figure', 'box': box})
    return _merge(out)


def _overlap(a, b) -> float:
    """Share of box a covered by box b."""
    w = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    h = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    return w * h / max(1, (a[2] - a[0]) * (a[3] - a[1]))


def _merge(regions: list[dict]) -> list[dict]:
    """A region inside a larger one of the same kind (the inner ring of a stamp) is dropped."""
    regions = sorted(regions, key=lambda r: -(r['box'][2] - r['box'][0]) * (r['box'][3] - r['box'][1]))
    kept = []
    for region in regions:
        if not any(k['kind'] == region['kind'] and _overlap(region['box'], k['box']) > 0.8 for k in kept):
            kept.append(region)
    return kept


def find(image: Image.Image, lines, tables=()) -> list[dict]:
    """Heading, stamp and figure regions; `tables` are table boxes (x0, y0, x1, y1) from layout analysis."""
    tables = [tuple(t) for t in tables]
    return headings(lines, image.height, tables) + graphics(image, tables)
