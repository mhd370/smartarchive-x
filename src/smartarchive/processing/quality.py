"""Per-page image quality assessment for quality-aware OCR routing.

Q_p = w1*B + w2*C + w3*R + w4*S + w5*L, every term normalised to [0, 1] where 1 is best:
B sharpness, C contrast, R resolution, S skew integrity, L layout simplicity.
Normalisation bounds and route thresholds are initial engineering values; they are recorded
with every result so later calibration on the validation split stays traceable.
"""
from dataclasses import asdict, dataclass
import math

import cv2
import numpy as np
from PIL import Image

ANALYSIS_SIDE = 1600
ROUTE_FAST, ROUTE_LAYOUT = 0.80, 0.55
BOUNDS = {'sharpness_var': (30.0, 600.0), 'contrast_range': (0.25, 0.75), 'dpi': (100.0, 300.0),
          'skew_degrees': 5.0, 'noise_sigma': (2.0, 12.0)}


@dataclass
class Quality:
    score: float
    route: str
    blank: bool
    skew_angle: float
    columns: int
    has_table: bool
    layout: str
    sharpness: float
    contrast: float
    resolution: float
    skew: float
    layout_simplicity: float
    noise: float
    raw: dict
    weights: tuple

    def to_dict(self) -> dict:
        return asdict(self)


def _clip(value: float) -> float:
    return float(min(1.0, max(0.0, value)))


def _scaled_gray(image: Image.Image) -> np.ndarray:
    gray = np.asarray(image.convert('L'))
    scale = ANALYSIS_SIDE / max(gray.shape)
    if scale < 1:
        gray = cv2.resize(gray, (round(gray.shape[1] * scale), round(gray.shape[0] * scale)),
                          interpolation=cv2.INTER_AREA)
    return gray


def ink_mask(gray: np.ndarray) -> np.ndarray:
    _, mask = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    return mask


def rotate(array: np.ndarray, angle: float, border) -> tuple[np.ndarray, np.ndarray]:
    """Rotate counter-clockwise by angle degrees on an expanded canvas; return image and 2x3 matrix."""
    height, width = array.shape[:2]
    matrix = cv2.getRotationMatrix2D((width / 2, height / 2), angle, 1.0)
    cos, sin = abs(matrix[0, 0]), abs(matrix[0, 1])
    new_w, new_h = int(round(height * sin + width * cos)), int(round(height * cos + width * sin))
    matrix[0, 2] += new_w / 2 - width / 2
    matrix[1, 2] += new_h / 2 - height / 2
    rotated = cv2.warpAffine(array, matrix, (new_w, new_h), flags=cv2.INTER_LINEAR,
                             borderMode=cv2.BORDER_CONSTANT, borderValue=border)
    return rotated, matrix


def estimate_skew(mask: np.ndarray) -> float:
    """Projection-profile skew estimate in degrees (the counter-clockwise correction to apply)."""
    if mask.max() == 0:
        return 0.0
    scale = 1000 / max(mask.shape)
    small = cv2.resize(mask, (max(1, round(mask.shape[1] * scale)), max(1, round(mask.shape[0] * scale))),
                       interpolation=cv2.INTER_AREA) if scale < 1 else mask

    def score(angle: float) -> float:
        rotated, _ = rotate(small, angle, 0)
        return float(np.var(rotated.sum(axis=1, dtype=np.float64)))

    coarse = max(np.arange(-10, 10.01, 0.5), key=score)
    fine = max(np.arange(coarse - 0.5, coarse + 0.51, 0.1), key=score)
    return round(float(fine), 2)


def _columns_and_tables(mask: np.ndarray) -> tuple[int, bool]:
    height, width = mask.shape
    horizontal = cv2.morphologyEx(mask, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (max(10, width // 12), 1)))
    vertical = cv2.morphologyEx(mask, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(10, height // 12))))
    h_lines = len(cv2.findContours(horizontal, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[0])
    v_lines = len(cv2.findContours(vertical, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[0])
    has_table = h_lines >= 3 and v_lines >= 2
    text = cv2.subtract(mask, cv2.bitwise_or(horizontal, vertical))
    rows = np.where(text.sum(axis=1) > 0)[0]
    if rows.size == 0:
        return 0, has_table
    # Column gutters: wide vertical bands with (almost) no ink inside the text body.
    body = text[rows[0]:rows[-1] + 1]
    profile = body.sum(axis=0) / 255.0
    kernel = max(3, width // 100)
    smooth = np.convolve(profile, np.ones(kernel) / kernel, mode='same')
    filled = smooth > max(1.0, 0.02 * body.shape[0])
    segments, start = [], None
    for x, value in enumerate(filled):
        if value and start is None:
            start = x
        elif not value and start is not None:
            segments.append((start, x))
            start = None
    if start is not None:
        segments.append((start, width))
    min_gap, min_width = 0.03 * width, 0.08 * width
    merged = []
    for segment in segments:
        if merged and segment[0] - merged[-1][1] < min_gap:
            merged[-1] = (merged[-1][0], segment[1])
        else:
            merged.append(segment)
    columns = len([s for s in merged if s[1] - s[0] >= min_width]) or 1
    return columns, has_table


def assess(image: Image.Image, dpi: float | None,
           weights: tuple[float, float, float, float, float] = (0.2, 0.2, 0.2, 0.2, 0.2)) -> Quality:
    gray = _scaled_gray(image)
    mask = ink_mask(gray)
    ink = mask > 0
    ink_ratio = float(ink.mean())
    # Ink-vs-paper contrast. Global percentiles fail on sparse letters, where ink is under 2% of
    # the page and both tails of the histogram are paper.
    if ink.any() and (~ink).any():
        contrast_range = float(np.median(gray[~ink]) - np.percentile(gray[ink], 10)) / 255.0
    else:
        contrast_range = 0.0
    blank = ink_ratio < 0.001 or contrast_range < 0.08
    laplacian = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    background = mask == 0
    residual = gray.astype(np.int16) - cv2.medianBlur(gray, 3).astype(np.int16)
    noise_sigma = float(residual[background].std()) if background.any() else 0.0
    angle = 0.0 if blank else estimate_skew(mask)
    columns, has_table = (0, False) if blank else _columns_and_tables(ink_mask(rotate(gray, angle, 255)[0]) if abs(angle) >= 0.3 else mask)

    low, high = BOUNDS['sharpness_var']
    sharpness = _clip((math.log10(max(laplacian, 1e-6)) - math.log10(low)) / (math.log10(high) - math.log10(low)))
    contrast = _clip((contrast_range - BOUNDS['contrast_range'][0]) / (BOUNDS['contrast_range'][1] - BOUNDS['contrast_range'][0]))
    resolution = _clip(((dpi or 0) - BOUNDS['dpi'][0]) / (BOUNDS['dpi'][1] - BOUNDS['dpi'][0]))
    skew = _clip(1 - abs(angle) / BOUNDS['skew_degrees'])
    noise = _clip(1 - (noise_sigma - BOUNDS['noise_sigma'][0]) / (BOUNDS['noise_sigma'][1] - BOUNDS['noise_sigma'][0]))
    simplicity = {0: 1.0, 1: 1.0, 2: 0.7}.get(columns, 0.45) - (0.25 if has_table else 0.0)
    simplicity = _clip(simplicity)
    layout = 'tabular' if has_table else 'multi_column' if columns >= 2 else 'simple'
    score = round(sum(w * v for w, v in zip(weights, (sharpness, contrast, resolution, skew, simplicity))), 4)
    route = 'fast' if score >= ROUTE_FAST else 'layout' if score >= ROUTE_LAYOUT else 'advanced'
    raw = {'laplacian_variance': round(laplacian, 2), 'contrast_range': round(contrast_range, 4),
           'dpi': round(dpi, 1) if dpi else None, 'noise_sigma': round(noise_sigma, 3),
           'ink_ratio': round(ink_ratio, 5), 'bounds': BOUNDS,
           'route_thresholds': {'fast': ROUTE_FAST, 'layout': ROUTE_LAYOUT}}
    return Quality(score=score, route=route, blank=blank, skew_angle=angle, columns=columns, has_table=has_table,
                   layout=layout, sharpness=round(sharpness, 4), contrast=round(contrast, 4),
                   resolution=round(resolution, 4), skew=round(skew, 4), layout_simplicity=round(simplicity, 4),
                   noise=round(noise, 4), raw=raw, weights=tuple(weights))
