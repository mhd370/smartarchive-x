# Changelog

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
