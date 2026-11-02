# ADR 0009: Hybrid ranked search over OCR text

Status: accepted (Sprint 7 / Task 012)

## Context
Until v0.11.0 the search returned pages containing every query word as a normalized substring. Results were
ordered by occurrence count. On the synthetic development set (321 queries over OCR text) this found the
relevant document in the top 10 for 44% of queries, and for only 12% of reference-number queries. One misread
word, a different clitic or a missing word lost the document. The brief asks for a hybrid lexical and
semantic index with re-ranking.

## Decision
1. Two derived SQLite FTS5 indexes of `page_texts` (migration 6), updated whenever a page's effective text
   changes (OCR or human correction) and back-filled at start-up:
   - `page_terms`: normalized words after light Arabic stemming (prefixes و ف ب ك ل ال, common suffixes,
     stems of at least three letters), ranked by BM25 with any word allowed to match.
   - `page_trigrams`: the normalized text, queried with the character trigrams of the query words and ranked
     by BM25. A word misread by OCR still shares most of its trigrams.
2. A third ranking holds the pages that contain every query word, the whole phrase first. This is the old
   exact signal.
3. The three rankings are fused per page with reciprocal rank fusion (k = 60), and a document scores as its
   best page (`hybrid-rrf-v1`). The fusion is rank-based, so the scores of the three rankings do not need
   calibrating against each other.
4. Ranked is the default mode of `GET /api/search` and of the search page. `mode=exact` keeps the previous
   behaviour for users who need every word.

## Consequences
- Development set, same OCR text: Recall@10 rose from 44.2% to 54.2% and nDCG@10 from 33.3% to 37.7%.
  Reference-number Recall@10 rose from 12.2% to 30.5%, and MRR from 30.9% to 33.4%. Without the exact
  ranking, MRR fell for subjects, because many documents share most subject words.
- The indexes are derived data: they can be dropped and rebuilt from `page_texts` at any time.
- Dense (embedding) retrieval and cross-encoder re-ranking come next as further inputs to the same fusion.
  Each is kept only if it improves the development set and is then confirmed on the test set.
