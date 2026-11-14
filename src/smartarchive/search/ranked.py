"""Ranked search (`hybrid-rrf-v1`): exact matches, BM25 over light Arabic stems and character-trigram BM25.

Why two indexes:
- Words: the normalized page text with light stemming. Prefixes و ف ب ك ل ال and common suffixes are
  removed, so «والمشروع», «بالمشروع» and «مشروعات» meet «مشروع». It is ranked by SQLite FTS5 BM25, and any
  query word may match (OR), so a query still finds a page when OCR garbled one of its words.
- Character trigrams: every query word is split into 3-character pieces and ranked by BM25 over a trigram
  index. A word misread by OCR («الخدمات» → «الخدمان») still shares most of its trigrams with the query.
- Exact: pages that contain every query word (as the exact mode), the whole phrase first.
The three rankings are fused with reciprocal rank fusion (RRF, k=60) per page. A document scores as its best
page. The substring search in pages.py stays available as the exact mode.
"""
from collections import defaultdict
import re

from .arabic import find_spans, normalize

METHOD = 'hybrid-rrf-v1'
METHOD_DENSE = 'hybrid-rrf-v2'  # the same fusion plus the dense ranking of semantic.py
RRF_K = 60
CANDIDATES = 300
_PREFIXES = ('وبال', 'وال', 'بال', 'كال', 'فال', 'لل', 'ال', 'و', 'ف', 'ب', 'ك', 'ل')
_SUFFIXES = ('هما', 'كما', 'ات', 'ون', 'ين', 'ان', 'ها', 'هم', 'كم', 'نا', 'يه', 'يا', 'ه', 'ي')
MIN_STEM = 3


def stem(word: str) -> str:
    """Light stemming of one normalized word (taa marbuta is already «ه», hamza forms already unified)."""
    if not re.fullmatch(r'[ء-ي]+', word):
        return word  # numbers, Latin words and mixed tokens are kept as they are
    for prefix in _PREFIXES:
        if word.startswith(prefix) and len(word) - len(prefix) >= MIN_STEM:
            word = word[len(prefix):]
            break
    for suffix in _SUFFIXES:
        if word.endswith(suffix) and len(word) - len(suffix) >= MIN_STEM:
            word = word[:-len(suffix)]
            break
    return word


def stems(text: str) -> str:
    return ' '.join(stem(word) for word in normalize(text).split())


def trigrams(word: str) -> list[str]:
    return [word[i:i + 3] for i in range(len(word) - 2)] if len(word) >= 3 else []


def _quote(term: str) -> str:
    return '"' + term.replace('"', '""') + '"'


def index_page(db, document_id: str, page_no: int, text: str):
    """Replace one page in both indexes (called whenever page_texts changes)."""
    db.execute('DELETE FROM page_terms WHERE document_id=? AND page_no=?', (document_id, page_no))
    db.execute('DELETE FROM page_trigrams WHERE document_id=? AND page_no=?', (document_id, page_no))
    db.execute('INSERT INTO page_terms(document_id, page_no, terms) VALUES (?,?,?)', (document_id, page_no, stems(text)))
    db.execute('INSERT INTO page_trigrams(document_id, page_no, text) VALUES (?,?,?)',
               (document_id, page_no, ' '.join(normalize(text).split())))


def ensure_indexed(db) -> int:
    """Index pages that are not in the ranked indexes yet (archives older than this feature)."""
    rows = db.execute('SELECT document_id, page_no, text FROM page_texts t WHERE NOT EXISTS (SELECT 1 FROM page_terms'
                      ' p WHERE p.document_id=t.document_id AND p.page_no=t.page_no)').fetchall()
    for row in rows:
        index_page(db, row['document_id'], row['page_no'], row['text'])
    return len(rows)


def _ranked(db, sql: str, match: str) -> list[tuple[str, int]]:
    if not match:
        return []
    return [(row[0], row[1]) for row in db.execute(sql, (match, CANDIDATES))]


def search(db, query: str, dense: list[tuple[str, int]] | None = None) -> tuple[list[str], dict[tuple[str, int], float]]:
    """(normalized query words, fused RRF score per (document_id, page_no)); `dense` is semantic.py's ranking."""
    words = [word for word in normalize(query).split()][:12]
    word_match = ' OR '.join(_quote(stem(word)) for word in dict.fromkeys(words))
    grams = list(dict.fromkeys(gram for word in words for gram in trigrams(word)))
    gram_match = ' OR '.join(_quote(gram) for gram in grams[:60])
    by_words = _ranked(db, 'SELECT document_id, page_no FROM page_terms WHERE page_terms MATCH ? '
                           'ORDER BY bm25(page_terms) LIMIT ?', word_match)
    by_grams = _ranked(db, 'SELECT document_id, page_no FROM page_trigrams WHERE page_trigrams MATCH ? '
                           'ORDER BY bm25(page_trigrams) LIMIT ?', gram_match)
    # Pages holding every query word, in order of how often: the exact signal that puts the page with the whole
    # subject above pages that only share some of its words.
    exact = []
    if words:
        where = ' AND '.join("normalized LIKE ? ESCAPE '\\'" for _ in words)
        likes = ['%' + w.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%' for w in words]
        rows = db.execute(f'SELECT document_id, page_no, normalized FROM page_texts WHERE {where} LIMIT ?',
                          [*likes, CANDIDATES]).fetchall()
        exact = [(row[0], row[1]) for row in sorted(
            rows, key=lambda row: -(row[2].count(' '.join(words)) * 10 + sum(row[2].count(w) for w in words)))]
    fused: dict[tuple[str, int], float] = defaultdict(float)
    for ranking in (exact, by_words, by_grams, dense or []):
        for rank, key in enumerate(ranking):
            fused[key] += 1.0 / (RRF_K + rank + 1)
    return words, dict(fused)


def page_hits(text: str, words: list[str]) -> list[tuple[int, int]]:
    """Spans to highlight: whole query words first, otherwise their stems."""
    spans = find_spans(text, words)
    if not spans:
        spans = find_spans(text, [stem(word) for word in words if len(stem(word)) >= MIN_STEM])
    return spans

