"""OCR engine adapters. Every engine returns lines with word boxes and its own confidences.

Confidence is the engine's value rescaled to 0..1; it is never estimated from text length.
"""
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from PIL import Image


@dataclass
class Word:
    text: str
    confidence: float | None
    box: tuple[int, int, int, int]


@dataclass
class Line:
    text: str
    confidence: float | None
    box: tuple[int, int, int, int]
    words: list[Word] = field(default_factory=list)


class Engine(Protocol):
    name: str

    def version(self) -> str: ...

    def recognize(self, image: Image.Image) -> list[Line]: ...


def mean_confidence(words: list[Word]) -> float | None:
    """Character-weighted mean of word confidences, ignoring words without a confidence."""
    scored = [(w.confidence, len(w.text)) for w in words if w.confidence is not None]
    total = sum(length for _, length in scored)
    return round(sum(c * length for c, length in scored) / total, 4) if total else None


def installed_languages(command: str, tessdata_dir: str | None = None) -> set[str]:
    """Models Tesseract can load, including `script/...` ones. pytesseract.get_languages is not used: it drops
    names with a slash and caches its first answer for the whole process, whatever folder is asked."""
    import subprocess
    args = [command] + (['--tessdata-dir', tessdata_dir] if tessdata_dir else []) + ['--list-langs']
    result = subprocess.run(args, capture_output=True, timeout=60)
    lines = result.stdout.decode('utf-8', 'replace').splitlines()
    names = {line.strip().replace('\\', '/') for line in lines[1:] if line.strip() and ' ' not in line.strip()}
    if tessdata_dir:  # some Windows builds list only top-level models; the files themselves are the truth
        root = Path(tessdata_dir)
        names |= {path.relative_to(root).with_suffix('').as_posix() for path in root.rglob('*.traineddata')}
    return names


class TesseractEngine:
    name = 'tesseract'

    def __init__(self, command: str, languages: str, timeout: int = 120, tessdata_dir=None):
        import pytesseract
        self._tess = pytesseract
        pytesseract.pytesseract.tesseract_cmd = command
        self.tessdata_dir = str(tessdata_dir) if tessdata_dir else None
        if self.tessdata_dir and ' ' in self.tessdata_dir:
            raise RuntimeError('the tessdata folder path must not contain spaces')
        self._config = f'--tessdata-dir {self.tessdata_dir} ' if self.tessdata_dir else ''
        installed = installed_languages(command, self.tessdata_dir)
        requested = [code for code in languages.split('+') if code]
        self.languages = '+'.join(code for code in requested if code in installed)
        self.missing = [code for code in requested if code not in installed]
        if not self.languages:
            raise RuntimeError(f'none of the OCR languages {requested} are installed')
        self.timeout = timeout
        self._version = str(pytesseract.get_tesseract_version())

    def version(self) -> str:
        return self._version

    def recognize(self, image: Image.Image) -> list[Line]:
        return self._read(image, 3)

    def recognize_block(self, image: Image.Image) -> list[Line]:
        """A region read as one uniform block of text (psm 6), e.g. a table cell (layout.py)."""
        return self._read(image, 6)

    def _read(self, image: Image.Image, psm: int) -> list[Line]:
        data = self._tess.image_to_data(image, lang=self.languages, config=self._config + f'--oem 1 --psm {psm}',
                                        output_type=self._tess.Output.DICT, timeout=self.timeout)
        groups: dict[tuple[int, int, int], list[Word]] = {}
        for index, raw in enumerate(data['text']):
            text = (raw or '').strip()
            if not text:
                continue
            conf = float(data['conf'][index])
            left, top = int(data['left'][index]), int(data['top'][index])
            box = (left, top, left + int(data['width'][index]), top + int(data['height'][index]))
            key = (data['block_num'][index], data['par_num'][index], data['line_num'][index])
            groups.setdefault(key, []).append(Word(text, round(conf / 100, 4) if conf >= 0 else None, box))
        lines = []
        for words in groups.values():  # dict order = Tesseract reading order
            box = (min(w.box[0] for w in words), min(w.box[1] for w in words),
                   max(w.box[2] for w in words), max(w.box[3] for w in words))
            lines.append(Line(' '.join(w.text for w in words), mean_confidence(words), box, words))
        return lines
