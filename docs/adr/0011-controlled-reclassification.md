# ADR 0011: Controlled reclassification with evidence thresholds

Status: accepted (Sprint 9 / Task 014)

## Context
The brief asks for documents to be reclassified when stronger evidence appears. The change must be controlled:
the system must never change a file's category by itself. Up to v0.13.0 a new suggestion was computed on every
new piece of evidence, such as corrected page text, a new model or edited categories. Once a person had
confirmed a category, though, a newer disagreeing suggestion was only visible in the history. Nobody was told
about it.

## Decision
1. `reclass-delta-v1` (`classification/reclassify.py`) turns a suggestion into a **reclassification proposal**
   only when all of these hold:
   - the suggestion is newer than the latest human decision;
   - its evidence differs from the evidence the person decided on. The suggestion digest covers text,
     categories and model, so a forced re-suggestion on the same evidence never reopens a decision;
   - it names a different category above the classifier's own abstention threshold;
   - that category's share of the scores is at least 0.6;
   - its share exceeds the confirmed category's share by at least 0.3 (Δ).

   Shares are the scores normalized to one. The rule therefore reads the same for keyword scores and for model
   probabilities.
2. The confirmed category stays in force. The document page shows the proposal with both shares. The review
   page lists open proposals, strongest Δ first (`GET /api/classification/reclassification`).
3. A reviewer resolves a proposal in one of two ways:
   - **Accept:** an ordinary reclassification with a required reason. The decision basis records
     `accepted_reclassification`.
   - **Dismiss** (`POST /api/documents/{id}/classification/reclassification/dismiss`): written append-only to
     `reclassification_reviews` (migration 7) and to the audit log as `reclassification.dismissed`. That
     suggestion is not proposed again; newer evidence can propose again.
4. Nothing is proposed for documents without a decision. Their suggestion is already the open question.

## Choosing the thresholds (development set only)
The gates were chosen on out-of-fold predictions of `tfidf-svm-v1` over corpus_v1 (5-fold cross-validation
grouped by relation clusters, `script/Arabic+ara` OCR text). Every (document, confirmed category) pair was
scored with the document's suggestion as the new evidence:
- if the confirmed category is right, any proposal is a false alarm;
- if it is wrong, a proposal to the true type is a catch;
- a proposal to another wrong type is a wrong move.

| Share ≥ | Δ ≥ | Caught | False alarms | Wrong moves |
|---|---|---|---|---|
| 0.4 | 0.0 | 81.0% | 1.84% | 1.57% |
| 0.5 | 0.3 | 79.5% | 0.61% | 0.70% |
| **0.6** | **0.3** | **76.7%** | **0.20%** | **0.17%** |
| 0.8 | 0.3 | 64.3% | 0.00% | 0.00% |

0.6 / 0.3 removes most false alarms and wrong moves while still catching three in four wrong confirmations. With
model probabilities, a share of 0.6 already implies Δ ≥ 0.2. Δ matters mainly for the keyword baseline,
whose raw scores can split between two strong categories. `tools/evaluate_synthetic.py` reports the same
analysis for any run, including the held-out test set.

## Consequences
- Reviewers see strong disagreements instead of finding them in the history, and every outcome is attributable.
- The analysis treats every suggestion as new evidence. In use, proposals appear only after OCR corrections,
  retraining or category edits, so their number depends on how often those happen.
- Thresholds are global. Per-category thresholds, and proposals for the folder as well as the category, are
  possible extensions.
