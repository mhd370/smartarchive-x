"""Render verified originals to page images without modifying the stored bytes."""
from pathlib import Path
from typing import Iterator

from PIL import Image, ImageSequence

A4_WIDTH_IN, A4_HEIGHT_IN = 8.27, 11.69
MAX_SIDE = 5000


def _estimated_dpi(width: int, height: int) -> float:
    # Without scanner metadata assume an A4 page; reported as an estimate, never as a measurement.
    return width / (A4_WIDTH_IN if width <= height else A4_HEIGHT_IN)


def page_images(path: Path, mime: str, dpi: int) -> Iterator[tuple[int, Image.Image, float, str]]:
    """Yield (page_no, RGB image, effective dpi, dpi_source) for every page."""
    if mime == 'application/pdf':
        import pymupdf
        with pymupdf.open(path) as document:
            for index, page in enumerate(document):
                scale = dpi / 72
                longest = max(page.rect.width, page.rect.height) * scale
                if longest > MAX_SIDE:
                    scale *= MAX_SIDE / longest
                pixmap = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False, colorspace=pymupdf.csRGB)
                image = Image.frombytes('RGB', (pixmap.width, pixmap.height), pixmap.samples)
                yield index + 1, image, scale * 72, 'rendered'
        return
    with Image.open(path) as source:
        for index, frame in enumerate(ImageSequence.Iterator(source)):
            image = frame.convert('RGB')
            declared = frame.info.get('dpi')
            try:
                value = float(declared[0]) if declared else 0.0
            except (TypeError, ValueError, IndexError):
                value = 0.0
            if 50 <= value <= 1200:
                yield index + 1, image.copy(), value, 'metadata'
            else:
                yield index + 1, image.copy(), _estimated_dpi(*image.size), 'estimated_a4'
