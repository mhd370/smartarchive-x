# ADR 0007 — Folders, the brief's taxonomy, rule-based metadata and fingerprint duplicates

Status: accepted (Sprint 5, v0.10.0)

## Context
The dean's brief asks for folder evidence, five to eight institutional document types with a hierarchy,
extraction of number/date/sender/subject, and detection of duplicates and versions. No institutional
documents are available yet, so methods must be explainable baselines that later models are compared with.

## Decision
- Folders are a path tree; a document is filed in at most one folder; moves are audited. Bulk import keeps
  the source folder structure, because folder placement is itself archival evidence.
- The default taxonomy follows the brief (8 types, 4 groups). Upgrading an existing archive refreshes only
  categories the system created, deactivates unused old defaults and keeps anything people created or used.
- Metadata `rules-v1`: labelled patterns (high confidence) before unlabelled ones; values keep page and span
  so the evidence can be shown; human corrections are separate rows that always win over re-extraction.
- Duplicates `fingerprint-v1`: SHA-256 for identical files, MinHash (64 permutations, word 3-grams) for
  near-identical text, and shared reference number/subject for versions. Links are suggestions for review.
- New text from OCR or correction re-runs metadata, classification and relation checks; each step is isolated
  so a failure cannot break OCR or a reviewer's save.

## Consequences
- Rule-based extraction will miss unlabelled layouts; it is the baseline that layout-aware extraction is
  measured against once layout analysis exists (Sprint 6).
- Thresholds (0.85 near-duplicate, 0.25/0.45 for versions) are initial values, to be tuned on the corpus.
