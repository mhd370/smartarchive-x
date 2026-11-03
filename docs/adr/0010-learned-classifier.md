# ADR 0010: Learned document classifier trained on confirmed decisions

Status: accepted (Sprint 8 / Task 013)

## Context
Up to v0.12.0 categories were suggested by `keywords-v1`: weighted keywords per category, an explained score
and abstention. On the synthetic development set (OCR text) it answered about 78% of documents, and 90% of
those answers were right. Keywords must be written by hand for each new category, and they do not learn from
the corrections reviewers make. The brief asks for learned baselines and for classification that improves as
the archive grows.

## Decision
1. `tfidf-svm-v1` (`classification/learned.py`):
   - features: TF-IDF of normalized word unigrams and bigrams (min_df 2, sublinear tf), with the file name
     added to the text as in the keyword baseline;
   - model: a linear SVM calibrated with `CalibratedClassifierCV`, so the scores are probabilities.
2. Training data is the latest human decision of each document with its page texts. Categories with fewer
   than three confirmed documents are left out and listed in the model card. Training is an admin action
   (`POST /api/admin/classifier/train`, the button on the system page, or `tools/train_classifier.py
   --archive`) and is written to the security log as `classifier.trained`.
3. The model is stored under `storage/models` as `classifier.joblib` with a JSON card: id, classes,
   examples per class, classes left out, training time, source, threshold. Once a model exists, it replaces
   the keyword baseline for new suggestions, and all open suggestions are recomputed. If the model cannot
   be loaded, suggestions fall back to keywords.
4. Abstention as before: the top probability must reach 0.4. Below that, the level-1 group is still named
   when the group's summed probability reaches 0.4 (`group_only`); otherwise the document is left for a
   person (`ambiguous`). Classes that are no longer active categories are never suggested.
5. Explanation: the words whose TF-IDF weight times the class's mean SVM coefficient pushed most towards the
   suggestion, shown in the same evidence list as the keywords.
6. A suggestion never changes a confirmed category. The suggestion basis records the model id, so a new
   model produces a new suggestion that can be told apart from the old one.

## Evaluation
- Development set (corpus_v1, OCR text, 5-fold cross-validation grouped by document so that copies never
  straddle folds): accuracy 82.9% without abstention; at 0.4, coverage 82.9% and precision 96.8%.
  Keyword baseline on the same text: coverage about 78%, precision 90%.
- Held-out test set (corpus_v2): the model trained on all of corpus_v1's OCR text classifies corpus_v2
  (`tools/evaluate_synthetic.py --classifier-model`). Results are in `docs/synthetic_evaluation.md`.

## Consequences
- New dependencies: scikit-learn and joblib (API only).
- The classifier is text-only. Severe scans with little OCR text still abstain; image and layout features
  (the multimodal classifier of the brief) are later work.
- The model is trained only when an admin asks. Automatic retraining and reclassification thresholds belong
  to the reclassification engine.
- joblib files run code when loaded. They are only ever written by the archive itself, into its own
  storage folder, and never accepted from users.
