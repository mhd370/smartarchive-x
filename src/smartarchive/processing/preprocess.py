"""Conservative page preprocessing with an exact coordinate transform back to the original page.

Uneven illumination is divided out (not thresholded) when present. Binarisation is deliberately never applied: it can erase coloured stamps, signatures and faint
writing. Each applied step is recorded so OCR output stays traceable to the source pixels.
"""
from dataclasses import dataclass, field

import cv2
import numpy as np
from PIL import Image

from .quality import Quality, estimate_skew, flatten, ink_mask, rotate

DESKEW_MIN_DEGREES = 0.3
OSD_MIN_CONFIDENCE = 2.0
# Illumination flattening when the paper is uneven or the contrast weak. On the synthetic corpus it took
# medium-quality scans from ~98% to ~38% CER and mild ones from ~11% to ~5%, with clean pages unchanged.
FLATTEN_MIN_BACKGROUND_RANGE = 0.08
FLATTEN_MAX_CONTRAST = 0.95


@dataclass
class Prepared:
    image: Image.Image
    matrix: np.ndarray  # 3x3, original page pixels -> processed pixels
    steps: list = field(default_factory=list)

    def to_original(self, box: tuple[float, float, float, float], width: int, height: int) -> tuple[float, ...]:
        """Map a processed-image box to a normalised (0..1) box on the original page."""
        x0, y0, x1, y1 = box
        inverse = np.linalg.inv(self.matrix)
        corners = np.array([[x0, y0, 1], [x1, y0, 1], [x0, y1, 1], [x1, y1, 1]], dtype=np.float64).T
        mapped = inverse @ corners
        xs, ys = mapped[0] / mapped[2], mapped[1] / mapped[2]
        clamp = lambda value, limit: min(max(float(value), 0.0), float(limit))
        return (round(clamp(xs.min(), width) / width, 5), round(clamp(ys.min(), height) / height, 5),
                round(clamp(xs.max(), width) / width, 5), round(clamp(ys.max(), height) / height, 5))


def _apply(array: np.ndarray, matrix: np.ndarray, angle: float) -> tuple[np.ndarray, np.ndarray]:
    rotated, affine = rotate(array, angle, (255, 255, 255))
    return rotated, np.vstack([affine, [0, 0, 1]]) @ matrix


def detect_orientation(image: Image.Image, tesseract_cmd: str | None) -> tuple[int, float] | None:
    """Tesseract OSD: clockwise rotation needed and its confidence, or None when unavailable."""
    if not tesseract_cmd:
        return None
    try:
        import pytesseract
        pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
        result = pytesseract.image_to_osd(image, output_type=pytesseract.Output.DICT, config='--psm 0', timeout=30)
        return int(result.get('rotate', 0)) % 360, float(result.get('orientation_conf', 0.0))
    except Exception:  # OSD fails on sparse pages; orientation is then left unchanged and recorded.
        return None


def prepare(image: Image.Image, quality: Quality, tesseract_cmd: str | None = None) -> Prepared:
    array = np.asarray(image.convert('RGB')).copy()
    matrix, steps = np.eye(3), []
    orientation = detect_orientation(image, tesseract_cmd)
    angle = quality.skew_angle
    if orientation and orientation[0] in (90, 180, 270) and orientation[1] >= OSD_MIN_CONFIDENCE:
        array, matrix = _apply(array, matrix, -orientation[0])
        steps.append({'step': 'orientation', 'rotate_clockwise': orientation[0], 'confidence': orientation[1]})
        angle = estimate_skew(ink_mask(cv2.cvtColor(array, cv2.COLOR_RGB2GRAY)))
    else:
        steps.append({'step': 'orientation', 'applied': False,
                      'detail': 'unavailable' if orientation is None else f'rotate={orientation[0]} conf={orientation[1]:.2f}'})
    if abs(angle) >= DESKEW_MIN_DEGREES:
        array, matrix = _apply(array, matrix, angle)
        steps.append({'step': 'deskew', 'degrees': angle})
    else:
        steps.append({'step': 'deskew', 'applied': False, 'degrees': angle})
    uneven = quality.raw.get('background_range', 0.0) >= FLATTEN_MIN_BACKGROUND_RANGE
    if uneven or quality.contrast < FLATTEN_MAX_CONTRAST:
        # Per channel, so coloured stamps and signatures keep their colour; geometry is unchanged.
        array = np.dstack([flatten(np.ascontiguousarray(array[..., c])) for c in range(3)])
        steps.append({'step': 'illumination', 'method': 'background_division',
                      'background_range': quality.raw.get('background_range'), 'contrast': quality.contrast})
    if quality.noise < 0.5:
        array = cv2.medianBlur(array, 3)
        steps.append({'step': 'denoise', 'method': 'median_3x3'})
    steps.append({'step': 'binarization', 'applied': False, 'reason': 'preserves stamps, signatures and faint text'})
    return Prepared(Image.fromarray(array), matrix, steps)
