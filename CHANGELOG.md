# Changelog

## 0.9.0 — Sprint 4 / Task 009 (unreleased)
- Backups: one zip with an online SQLite snapshot, every referenced original and a SHA-256 manifest; refused
  when an original is missing or damaged; verification re-hashes every member, checks database integrity and
  that each document's original matches the database. Admin page `/system` (create, verify, download) and
  `tools/archive_ops.py backup|verify`. `SMARTARCHIVE_BACKUP_DIR` sets the folder (default `storage/backups`).
- Restore (`tools/archive_ops.py restore`) only into a new or empty folder, after verification, re-checking
  every written file; the live archive is never overwritten.
- Integrity check (`/system`, CLI): re-hashes every original against the database, reports missing or changed
  originals, orphan folders, unfinished uploads, missing append-only triggers and unindexed documents; never
  deletes or repairs. Backups, verifications and checks are recorded as security events.
- Evaluation (`/evaluation`, `GET /api/evaluation`, `tools/archive_ops.py evaluate`): OCR post-editing CER/WER
  of corrected pages against their latest revision, overall and by OCR-confidence band; classifier coverage,
  accuracy, per-category precision/recall/F1 and confusion matrix against confirmed categories. Both state
  their limits (post-editing is not independent ground truth; reviewers saw the suggestion).

## 0.8.0 — Sprint 3 / Task 008 (unreleased)
- Explainable document classification (`keywords-v1`): ten default institutional categories (decision, circular,
  letter, minutes, report, contract, financial, certificate, request, personnel); whole-word Arabic keyword
  matching with clitics; heading and file-name weighting; confidence = top / (top + runner-up + 1); abstains
  below score 3 or confidence 0.5. Suggested automatically after OCR, after a page correction, and once for
  existing documents on start-up.
- Human decisions: confirm the suggestion or choose another category; changing a confirmed category needs a
  reason; expected-sequence check refuses stale edits; append-only `classifications` history; audit events
  `classification.confirmed` / `classification.changed`.
- Categories page (`/categories`): keywords and counts; admins add, edit or deactivate categories (logged as
  security events). Category column and filter in Documents; category filter in search; approval queue in
  Review; category breakdown on the dashboard.
- Schema version 4: `categories`, `classifications` (append-only triggers) and view `document_categories`.
- Quality gate: snapshots from Task 006 onwards now protect research code, data and results but not the
  evolving application code, which git versions (ADR 0005). Snapshots 003–005 and the 108 historical files
  are verified unchanged as before.

## 0.7.0 — Sprint 2 / Task 007 (unreleased)
- Arabic full-text search over page text and file names (`GET /api/search`, `/search` page, top-bar search).
  Normalization ignores diacritics, tatweel and invisible marks, unifies أ/إ/آ/ٱ→ا, ؤ→و, ئ→ي, ى→ي, ة→ه and
  Arabic-Indic digits; substring matching keeps clitics (و/ب/ال) searchable; "quoted phrases" stay together.
  Results are grouped per document with page links and highlighted excerpts in the original text.
- Human review of page text: append-only, numbered revisions with author, note and optimistic version check
  (stale edits are refused with 409); the corrected text replaces the OCR text in search; a new OCR run never
  overwrites a corrected page. Audit event `page.reviewed`.
- Review queue (`GET /api/review/queue`, `/review` page) of low-confidence or empty pages, lowest confidence first;
  the document reason moves from REVIEW_REQUIRED to REVIEW_COMPLETED when every flagged page is corrected.
- Dashboard shows pages awaiting review; document page shows the approved text, its source and revision history,
  and opens at `?page=n` from search results.
- Schema version 3 adds `page_revisions` (append-only triggers) and the derived `page_texts`; existing completed
  runs are indexed automatically on start-up.

## 0.6.0 — Sprint 1 / Task 006 (unreleased)
- Sign-in, first-run admin setup, four roles, user management page, session revocation, account lockout.
- Every document action is audited with the acting user; account events in an append-only security log.
- Persisted OCR runs with a background worker, restart recovery, progress and honest failure states.
- Per-page quality assessment Q = w·[B, C, R, S, L] with suggested route; blank-page detection.
- Conservative preprocessing: orientation (Tesseract OSD), deskew, conditional denoise, no binarisation.
- Tesseract adapter with line/word boxes mapped to the original page and engine confidences.
- Document page: quality panel, extracted text per page with confidence, boxes highlighted on the preview,
  run history, re-run button. Low-confidence pages flagged for review.
- Seeded degradation generator (`tools/degrade_pages.py`) for the simulation experiments.
- `tools/check.py` local quality gate; ADRs 0001–0003.
- The frontend forwards `/api/*` to FastAPI, so the browser uses one origin (no cross-port requests).
- Fix (found in manual review): sparse letters (<2% ink) were classified as blank pages; contrast is now
  measured as ink against paper. Regression test added.
- Upload buttons are hidden from roles without upload permission (the API already refused them).

## 0.5.0 — Task 005
- First full-stack archive: upload, immutable originals with SHA-256, SQLite metadata, audit, preview,
  download, dashboard (Next.js RTL frontend + FastAPI).

## 0.4.0 — Task 004
- Arabic transcription and review workspaces, error analysis reports.
