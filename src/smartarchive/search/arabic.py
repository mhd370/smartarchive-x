"""Arabic search normalization with a map back to the original characters.

Search compares normalized text, but results are shown in the original (OCR or reviewed) text, so
every normalized character remembers which original character it came from.

Rules (search only; stored text is never changed):
- remove diacritics (tashkeel, Quranic marks), tatweel and invisible format characters;
- unify hamza carriers: أ إ آ ٱ → ا, ؤ → و, ئ → ي; alef maqsura ى → ي; taa marbuta ة → ه;
- Arabic-Indic and Persian digits → 0-9; Latin letters lower-cased;
- any run of whitespace or punctuation → one space.
"""
import re
import unicodedata

_DROP = set(range(0x064B, 0x0660)) | {0x0670, 0x0640} | set(range(0x06D6, 0x06EE)) | \
    {0x200B, 0x200C, 0x200D, 0x200E, 0x200F, 0x061C, 0xFEFF}
_MAP = {**{c: 'ا' for c in 'أإآٱ'}, 'ؤ': 'و', 'ئ': 'ي', 'ى': 'ي', 'ة': 'ه',
        **{chr(0x0660 + i): str(i) for i in range(10)}, **{chr(0x06F0 + i): str(i) for i in range(10)}}


def _word_char(ch: str) -> bool:
    return unicodedata.category(ch)[0] in 'LN'


def normalize_with_map(text: str) -> tuple[str, list[int]]:
    """Return (normalized, positions) where positions[i] is the original index of normalized[i]."""
    out: list[str] = []
    positions: list[int] = []
    pending_space = False
    for index, ch in enumerate(unicodedata.normalize('NFC', text)):
        if ord(ch) in _DROP:
            continue
        ch = _MAP.get(ch, ch)
        if not _word_char(ch):
            pending_space = bool(out)
            continue
        if pending_space:
            out.append(' ')
            positions.append(index - 1)
            pending_space = False
        out.append(ch.lower())
        positions.append(index)
    return ''.join(out), positions


def normalize(text: str) -> str:
    return normalize_with_map(text)[0]


_QUOTED = re.compile(r'"([^"]+)"')


def parse_query(query: str, max_terms: int = 8) -> list[str]:
    """Split a query into normalized terms; "quoted phrases" stay together. Duplicates removed."""
    terms = [normalize(phrase) for phrase in _QUOTED.findall(query)]
    terms += normalize(_QUOTED.sub(' ', query)).split()
    unique = []
    for term in terms:
        if term and term not in unique:
            unique.append(term)
    return unique[:max_terms]


def find_spans(text: str, terms: list[str]) -> list[tuple[int, int]]:
    """[start, end) spans in the NFC form of `text` for every term occurrence, merged and sorted.

    A span includes diacritics that follow its last letter, so a highlighted word is never cut."""
    text = unicodedata.normalize('NFC', text)
    normalized, positions = normalize_with_map(text)
    spans = []
    for term in terms:
        start = normalized.find(term)
        while start != -1:
            end = start + len(term)
            stop = positions[end - 1] + 1
            while stop < len(text) and ord(text[stop]) in _DROP:
                stop += 1
            spans.append((positions[start], stop))
            start = normalized.find(term, end)
    spans.sort()
    merged: list[tuple[int, int]] = []
    for start, end in spans:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    return merged


def _widen(text: str, lo: int, hi: int, slack: int = 15) -> tuple[int, int]:
    """Move excerpt edges outwards to the nearest whitespace so words are not cut in half."""
    if lo > 0:
        space = text.rfind(' ', max(0, lo - slack), lo)
        lo = space + 1 if space != -1 else lo
    if hi < len(text):
        space = text.find(' ', hi, hi + slack)
        hi = space if space != -1 else hi
    return lo, hi


def snippets(text: str, spans: list[tuple[int, int]], radius: int = 60, limit: int = 3) -> list[list[dict]]:
    """Up to `limit` excerpts around matches, each a list of {text, match} parts of the original."""
    text = unicodedata.normalize('NFC', text)
    windows: list[list] = []
    for start, end in spans:
        lo, hi = _widen(text, max(0, start - radius), min(len(text), end + radius))
        if windows and lo <= windows[-1][1]:
            windows[-1][1] = max(windows[-1][1], hi)
            windows[-1][2].append((start, end))
        else:
            if len(windows) == limit:
                break
            windows.append([lo, hi, [(start, end)]])
    result = []
    for lo, hi, inner in windows:
        parts, cursor = [], lo
        if lo > 0:
            parts.append({'text': '… ', 'match': False})
        for start, end in inner:
            if start > cursor:
                parts.append({'text': text[cursor:start], 'match': False})
            parts.append({'text': text[start:end], 'match': True})
            cursor = end
        if hi > cursor:
            parts.append({'text': text[cursor:hi], 'match': False})
        if hi < len(text):
            parts.append({'text': ' …', 'match': False})
        result.append(parts)
    return result
