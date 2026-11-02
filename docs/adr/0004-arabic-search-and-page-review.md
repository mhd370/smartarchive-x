# ADR 0004 — Arabic text search and versioned page review

Status: accepted (Sprint 2, v0.7.0)

## Context
The archive must find documents by their content, in Arabic, where OCR output and user queries differ in
hamza forms, taa marbuta, alef maqsura, diacritics and digit scripts, and words carry attached clitics
(و، ب، ال). OCR text of low-confidence pages needs human correction that is attributable and reversible.

## Decision
- One normalization function (`search/arabic.py`) is applied to stored page text and to queries. It keeps a
  map to the original characters, so excerpts are highlighted in the text as written.
- Matching is substring-based on normalized text (every term must appear), not token-based. This keeps
  clitic forms searchable without a stemmer. Ranking is the number of occurrences; file-name matches add a
  fixed weight. A plain SQLite table is scanned with `LIKE`; at the expected archive size (thousands of
  pages) this is fast and needs no extra component. If it grows past that, an FTS5 trigram index can replace
  the scan behind the same API.
- `page_revisions` is append-only (triggers) and numbered per page; saves carry `expected_version` and are
  refused on conflict. `page_texts` is derived, rebuildable data: the latest revision, else the OCR text of
  the latest completed run. A new OCR run never replaces a corrected page.

## Consequences
- Search quality depends on OCR quality until pages are reviewed; the UI says which text is shown.
- Corrected pages become reference transcriptions for later CER/WER measurement.
- No morphological analysis (roots, broken plurals) yet; may be added later without changing the API.
