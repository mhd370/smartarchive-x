# ADR 0003 — Versioned OCR runs with recorded page quality

- Status: accepted (2026-10-30)
- Context: quality-aware routing must be evaluated against fixed strategies, and results must stay
  traceable to the source pixels. OCR must never overwrite earlier results or the original.
- Decision: each OCR execution is an `ocr_runs` row (engine, version, actual languages, parameters,
  requester). Per page it stores the quality analysis (B, C, R, S, L terms, weights, Q and suggested route),
  the preprocessing steps actually applied, and lines/words with engine confidences and boxes normalised
  to the original page. Preprocessing transforms are recorded as a matrix so boxes map back exactly.
  Binarisation is not applied (it destroys stamps and faint text). Pages below the review threshold
  (initially 0.60 mean confidence) or without text are flagged for human review.
- Consequences: re-running OCR produces a new version, so fixed-strategy and adaptive runs can be compared
  on the same document. Thresholds and weights are initial values recorded with each run; they are tuned
  on the validation split, never on the test split.
