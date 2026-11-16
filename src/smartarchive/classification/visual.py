"""Page-image features for the multimodal classifier (`visual-layout-v1`).

When OCR text is missing or garbled (severe scans), the text models have nothing to read, but the page still
shows its layout: a letterhead block, a ruled table, two columns, a signature area, a form grid. These features
describe that layout from the first page image only, at a resolution where blur does not matter:
- the ink profile down the page (64 bins) and across it (32 bins);
- the ink density on a 16 × 12 grid;
- long horizontal and vertical ruling lines (tables and forms) and the overall ink and aspect ratio.
They are combined with the text model by late fusion (tools/classification_experiments.py, ADR 0015).
"""
import cv2
import numpy as np
from PIL import Image

METHOD = 'visual-layout-v1'
WIDTH = 256


def features(image: Image.Image) -> np.ndarray:
    gray = np.asarray(image.convert('L'))
    height = max(1, round(gray.shape[0] * WIDTH / gray.shape[1]))
    small = cv2.resize(gray, (WIDTH, height), interpolation=cv2.INTER_AREA)
    _, ink = cv2.threshold(small, 0, 1, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    ink = ink.astype(np.float32)
    rows = cv2.resize(ink.mean(axis=1).reshape(-1, 1), (1, 64), interpolation=cv2.INTER_AREA).ravel()
    cols = cv2.resize(ink.mean(axis=0).reshape(1, -1), (32, 1), interpolation=cv2.INTER_AREA).ravel()
    grid = cv2.resize(ink, (12, 16), interpolation=cv2.INTER_AREA).ravel()
    mask = (ink * 255).astype(np.uint8)
    horizontal = cv2.morphologyEx(mask, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (WIDTH // 4, 1)))
    vertical = cv2.morphologyEx(mask, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(8, height // 8))))
    lines = [float((horizontal.max(axis=1) > 0).sum()) / height * 10, float((vertical.max(axis=0) > 0).sum()) / WIDTH * 10]
    return np.concatenate([rows, cols, grid, lines, [float(ink.mean()), height / WIDTH]]).astype(np.float32)
