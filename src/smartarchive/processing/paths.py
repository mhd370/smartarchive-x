"""Several OCR paths per page and an automatic choice between them (`ocr-paths-v1`, ADR 0016).

Every path reads the same prepared page (orientation, deskew, illumination, denoise from preprocess.py), so
the word boxes of every path map back to the original page the same way:
- `standard`: the prepared page as it is (the single path before Sprint 13);
- `binarized`: an adaptive (local mean) threshold of the prepared page, for faint or blotchy scans. Only the
  OCR input is thresholded; the stored original and its colours are never changed;
- `upscaled`: the prepared page enlarged 1.5x, for small print at 200 dpi;
- `model-ara`: the prepared page read with the `ara` model only, a second recognition model.

The choice is made per page from the engine's own output, never from the ground truth:
- `confidence`: the highest character-weighted mean word confidence;
- `confident-chars`: the most characters weighted by confidence (sum of confidence x length), which also
  rewards a path that reads more of the page.
With a gate below 1, the other paths are read only when the standard path's confidence is below the gate.
The rule, the paths and the gate are chosen on the development set (tools/ocr_paths_experiment.py).
"""
from dataclasses import dataclass

import cv2
import numpy as np
from PIL import Image

from .ocr import Line, Word, mean_confidence

METHOD = 'ocr-paths-v1'
PATHS = ('standard', 'binarized', 'upscaled', 'model-ara')
RULES = ('confidence', 'confident-chars')
UPSCALE = 1.5


@dataclass
class PathImage:
    name: str
    image: Image.Image
    scale: float = 1.0  # processed-image pixels per prepared-image pixel
    languages: str | None = None  # None: the engine's own languages


def variant(name: str, image: Image.Image) -> PathImage:
    if name == 'standard':
        return PathImage(name, image)
    if name == 'binarized':
        gray = cv2.cvtColor(np.asarray(image.convert('RGB')), cv2.COLOR_RGB2GRAY)
        block = max(15, (min(gray.shape) // 40) | 1)
        binary = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY, block, 12)
        return PathImage(name, Image.fromarray(binary).convert('RGB'))
    if name == 'upscaled':
        width, height = image.size
        return PathImage(name, image.resize((round(width * UPSCALE), round(height * UPSCALE)), Image.LANCZOS), UPSCALE)
    if name == 'model-ara':
        return PathImage(name, image, languages='ara')
    raise ValueError(f'unknown OCR path {name}')


def rescale(lines: list[Line], scale: float) -> list[Line]:
    """Boxes from an enlarged image back to prepared-image pixels."""
    if scale == 1.0:
        return lines
    box = lambda b: tuple(round(v / scale) for v in b)
    return [Line(l.text, l.confidence, box(l.box), [Word(w.text, w.confidence, box(w.box)) for w in l.words])
            for l in lines]


def score(lines: list[Line], rule: str) -> float:
    words = [w for line in lines for w in line.words]
    if rule == 'confidence':
        value = mean_confidence(words)
        return -1.0 if value is None else value
    if rule == 'confident-chars':
        return sum((w.confidence or 0.0) * len(w.text) for w in words)
    raise ValueError(f'unknown selection rule {rule}')


def choose(results: dict[str, list[Line]], rule: str) -> str:
    """The path with the best score; ties go to the earlier path in PATHS order (standard first)."""
    names = [name for name in PATHS if name in results]
    return max(names, key=lambda name: (score(results[name], rule), -names.index(name)))


def read(engine_for, image: Image.Image, paths: tuple[str, ...], rule: str, gate: float, read_page) -> tuple[list[Line], dict]:
    """Read the page on the standard path, then on the others when its confidence is below `gate`.
    `engine_for(languages)` gives the engine for a path (None: the default one); `read_page(engine, image)` returns
    (lines, layout_step). Returns the chosen lines and {'layout': step of the chosen path, 'paths': choice record}."""
    results, layouts = {}, {}
    first = 'standard' if 'standard' in paths else paths[0]
    order = [first] + [name for name in paths if name != first]
    for index, name in enumerate(order):
        if index == 1:
            confidence = mean_confidence([w for line in results[first] for w in line.words])
            if confidence is not None and confidence >= gate:
                break
        path = variant(name, image)
        lines, layout = read_page(engine_for(path.languages), path.image)
        if path.scale != 1.0 and layout and layout.get('tables'):
            layout = {**layout, 'tables': [{**t, 'box': [round(v / path.scale) for v in t['box']]}
                                           for t in layout['tables']]}
        results[name], layouts[name] = rescale(lines, path.scale), layout
    chosen = choose(results, rule) if len(results) > 1 else first
    step = {'step': 'ocr_paths', 'method': METHOD, 'rule': rule, 'gate': gate, 'chosen': chosen,
            'tried': {name: mean_confidence([w for line in lines for w in line.words]) for name, lines in results.items()}}
    return results[chosen], {'layout': layouts[chosen], 'paths': step}
