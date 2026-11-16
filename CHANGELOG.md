# Changelog

## 0.17.0 — Sprint 12 / Task 017 (unreleased)
- Search ablation and two optional search extensions (ADR 0014), measured with `tools/search_experiments.py`
  on the stored OCR text of both corpora:
  - `ranked.search(components=...)` restricts the fusion to any subset of exact, BM25 stems and trigrams;
  - confidence-aware fusion: pages read with low OCR confidence weigh the trigram ranking more and the exact
    ranking less (`SMARTARCHIVE_CONFIDENCE_ALPHA`);
  - cross-encoder re-ranking of the top 20 (`search/rerank.py`, `ce-mminilm-v1`, multilingual MiniLM trained
    on mMARCO, ONNX on the CPU; `tools/fetch_reranker_model.py`, `SMARTARCHIVE_RERANK=1`).
- Multimodal classification experiment (ADR 0015): `visual-layout-v1` page-image layout features, late and
  gated fusion with `tfidf-svm-v1`, β chosen by cross-validation on the development set
  (`tools/classification_experiments.py`). The same tool reports all three text baselines with macro-F1.
- Macro-F1 and per-type precision/recall/F1 in `tools/evaluate_synthetic.py`.
- Folder suggestion `folder-knn-v1`: `GET /api/documents/{id}/folder-suggestions`; the document page shows the
  folders of the most similar filed documents with a one-click move.
- Literature review: 51 works, every entry checked; Arabic OCR correction and retrieval on OCR text added.

## 0.16.0 — Sprint 11 / Task 016 (unreleased)
- Dense retrieval `dense-e5-small-v1` (ADR 0013): multilingual-e5-small through ONNX Runtime on the CPU, with
  page vectors in `page_vectors` (migration 8) and a background indexer, fused as a fourth ranking
  (`hybrid-rrf-v2`). Paraphrased queries gain 6.7 points of Recall@10 on the development set but only 0.5 on
  the test set, so it ships **off by default** (`SMARTARCHIVE_SEMANTIC=1`, `tools/fetch_semantic_model.py`).
- Paraphrased evaluation queries (`tools/paraphrase_queries.py`), reported separately. Exact search finds
  2–3% of paraphrased needs and ranked search about a third.
- Folder knowledge graph (`GET /api/graph`, `folder-graph-v1`): the folders page maps folders to the categories
  of their documents (confirmed or suggested) and lists relations that cross folders.
- Third classification baseline `tfidf-char-lr-v1` (character 2–5-grams, logistic regression): `learned.train
  (method=...)`, `tools/train_classifier.py --method`. Test set, trained on corpus_v1 layout text: accuracy 79.7%, coverage 83.2%, precision 95.8%, against 81.2% / 82.8% / 98.0% for `tfidf-svm-v1`, which stays the default.
- Reclassification gates confirmed on the held-out set: 78.5% of wrong confirmations caught, 0.3% false alarms (development set 76.7% / 0.2%).
- Literature review draft: 43 works in 8 themes, with a comparison table (`docs/literature_review.md`).

## 0.15.0 — Sprint 10 / Task 015 (unreleased)
- Layout analysis `layout-v1` (ADR 0012): ruled tables found from their ruling lines and read cell by cell,
  right to left; two-column sections whose lines psm 3 merged are split at the gutter and read right column
  first. Recorded as a `layout` processing step; `SMARTARCHIVE_LAYOUT=0` turns it off. Test set CER 27.5% →
  25.8% (tables 40.7% → 33.3%, two columns 32.6% → 30.4%, simple pages unchanged).
- Supporting evidence on the page: a search result opens its matching page and outlines the lines that hold the
  query's words on the page image (the `page` and `q` link parameters were previously ignored).
- Evaluation fix: `tools/evaluate_synthetic.py` now back-fills the ranked indexes before scoring. Archives OCR'd
  before ranked search had been scored with the exact signal only. The corrected development figure is ranked
  Recall@10 60.1% against 51.2% exact, and 35.4% against 6.7% on reference numbers. The Sprint 8 note that
  ranked ≈ exact is withdrawn.
- Second OCR engines compared on 40 development pages: PaddleOCR 40.9% and EasyOCR 43.2% CER against
  Tesseract's 30.8%, and 7–40× slower; Tesseract stays.

## 0.14.0 — Sprint 9 / Task 014 (unreleased)
- Controlled reclassification `reclass-delta-v1` (ADR 0011). New evidence that disagrees with a confirmed
  category becomes a proposal when its share is at least 0.6 and exceeds the confirmed category's by Δ ≥ 0.3.
  The category never changes by itself. A reviewer accepts the proposal (a reclassification with a reason) or
  dismisses it; dismissals are kept append-only. Development set: 76.7% of wrong confirmations caught, 0.2%
  false alarms on correct ones.
- `GET /api/classification/reclassification` and `POST /api/documents/{id}/classification/reclassification/dismiss`;
  the proposal appears on the document page and in a new section of the review page.
- Migration 7: `reclassification_reviews`.
- `tools/evaluate_synthetic.py` reports the reclassification gates (catches, false alarms, wrong moves) over a
  threshold grid.
- Search results explained (docs/synthetic_evaluation.md): on the same `script/Arabic+ara` text the ranked
  search gains about 2 MRR points on both sets. The earlier 10-point recall gain came from the noisier
  `ara+eng` OCR text.

## 0.13.0 — Sprint 8 / Task 013 (unreleased)
- Learned classifier `tfidf-svm-v1` (ADR 0010): TF-IDF word uni/bigrams with a calibrated linear SVM, trained
  on the documents whose category a person confirmed. It replaces the keyword baseline once trained, keeps
  abstention (0.4) and the group-only answer, and explains each suggestion with the words that weighed most.
  A suggestion never changes a confirmed category.
- Held-out test set (corpus_v2, model trained on corpus_v1): accuracy 81.0% against 71.6% for keywords,
  coverage 82.7% against 76.4%, precision when answered 98.0% against 93.7%.
- `GET /api/classifier` (model card and confirmed examples per category) and `POST /api/admin/classifier/train`
  (security event `classifier.trained`); the system page shows the model and a train button.
- `tools/train_classifier.py` (archive or labelled corpus) and `tools/evaluate_synthetic.py --classifier-model`.
- New API dependencies: scikit-learn 1.9.1, joblib 1.6.0.
- Ranked search measured on the test set: Recall@10 46.3% against 46.2% exact; the development-set gain did
  not carry over (see docs/synthetic_evaluation.md).

## 0.12.0 — Sprint 7 / Task 012 (unreleased)
- Ranked search (`hybrid-rrf-v1`, ADR 0009), now the default. Results are a reciprocal-rank fusion of three
  rankings:
  - pages containing every query word, with the whole phrase first;
  - BM25 over light Arabic stems (prefixes و ف ب ك ل ال and common suffixes removed);
  - BM25 over character trigrams, which still matches words misread by OCR.

  A document scores as its best page. Development set, same OCR text: Recall@10 rose from 44.2% to 54.2%,
  nDCG@10 from 33.3% to 37.7%, and reference-number Recall@10 from 12.2% to 30.5%. `mode=exact` and the
  search page's «كل الكلمات حرفيًا» keep the previous behaviour.
- Migration 6: FTS5 indexes `page_terms` and `page_trigrams`. They are derived from `page_texts`, updated with
  every OCR result or correction and back-filled on start-up.
- `tools/evaluate_synthetic.py` scores both search modes.

## 0.11.0 — Sprint 6 / Task 011 (unreleased)
- Synthetic institutional corpus (`tools/synth_corpus.py`, ADR 0008): the brief's eight types rendered as
  real PDFs with correct right-to-left Arabic (paragraphs, two-column pages read right column first, tables),
  signatures and stamps. Part of the corpus is turned into scans degraded with the project's seeded levels.
  Ground truth is exact: page text in reading order, block types and boxes, metadata, type and group, plus
  duplicates, near-duplicates and versions. Search queries come with their relevant documents.
  Development set `corpus_v1` (seed 2026); held-out test set `corpus_v2` (seed 7351).
- Ground-truth evaluation (`tools/evaluate_synthetic.py`): imports a corpus into a throw-away archive and runs
  the real pipeline. Scores OCR CER/WER by quality level and layout, metadata per field (exact match and value
  CER), classification (accuracy, coverage, group), duplicates/versions (precision/recall per kind) and search
  (Recall@10, MRR@10, nDCG@10). Resumable; `--re-enrich` re-scores new rules without new OCR.
- OCR fix: on shaded scans the global threshold counted the dark side of the paper as ink. A 3° tilt was
  measured as 10.5°, and the wrong deskew destroyed the page. Ink is now found on an illumination-flattened
  page. Uneven or low-contrast pages are flattened before OCR (division by the estimated paper background,
  per channel, no binarisation; recorded as step `illumination`).
- OCR models: `ara` knows only ٠ and ١ of the Arabic-Indic digits. `tools/fetch_ocr_models.py` installs
  pinned, hash-checked tessdata_fast models, including `script/Arabic`, which has all of them.
  `SMARTARCHIVE_TESSDATA_DIR`, `SMARTARCHIVE_OCR_DPI`; languages under a `script/` folder are detected
  correctly (pytesseract's list dropped them and cached the first answer).
- Metadata `rules-v2`:
  - A bare «من»/«إلى» needs a colon (OCR often reads it as «؛»).
  - Amounts prefer the grand total.
  - A date may come after its label on mixed-direction lines.
  - Untitled subjects are taken from «قرار ... بشأن ...», contract, report or minutes titles.
  - Direction marks are ignored.
  - Value CER per field is reported.
- Document page: when processing ended, the run summary could stay on "processing" because its last poll
  came before the run was ready; it is now fetched once more when processing ends (found by the browser test).
- `tools/ocr_engine_probe.py`: compares OCR engines (PaddleOCR, EasyOCR, Tesseract) on the development set
  in a separate environment, with the archive's own preprocessing.
- Relations `fingerprint-v2`: reference numbers link documents only with four or more digits, since OCR
  fragments like «ع/4» caused every false version suggestion. Only labelled or human-entered values link
  documents.

## 0.10.0 — Sprint 5 / Task 010 (unreleased)
- `docs/dean_requirements.md`: the dean's brief verbatim with a requirement-by-requirement status table.
- Folders: tree with document counts, upload into a folder, move (audited `document.filed`), filter documents
  by folder including sub-folders, `/folders` page; `tools/import_tree.py` imports a whole folder tree.
- Taxonomy from the brief: eight types (incoming/outgoing letters, decisions, administrative forms, minutes,
  contracts, invoices, technical reports) under four level-1 groups (administrative, financial, legal,
  technical). The classifier scores both levels and can report a confident group with an uncertain type.
  Existing archives are upgraded once: own defaults refreshed, unused old defaults deactivated, anything an
  administrator created or a reviewer used is kept.
- Metadata extraction (`rules-v1`): reference number, date (ISO; Hijri kept), sender, recipient, subject and
  amount with page and span; reviewers correct values and corrections always win; append-only history;
  protected fields flagged for the later constrained OCR correction.
- Duplicates and versions (`fingerprint-v1`): identical bytes, near-identical text (MinHash of word 3-grams)
  and versions sharing a reference number or subject; reviewers confirm or reject; nothing is merged.
- New text (OCR or correction) triggers metadata extraction, a new category suggestion and relation checks.

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
