# ADR 0015: Multimodal classification and folder suggestion

Status: accepted (Sprint 12 / Task 017)

## Context
The text classifiers (`keywords-v1`, `tfidf-svm-v1`, `tfidf-char-lr-v1`) reach 80–98% on readable pages.
On severe scans they fail almost entirely, because the OCR text is nearly empty: the SVM is right on 1.1% of
them on the test set. The brief asks for a classifier that uses the image as well as the text, for macro-F1
in the evaluation, and for a suggestion of the right folder.

## Decision
1. **Image features** (`classification/visual.py`, `visual-layout-v1`). From the first page image, at a
   width of 256 px where blur does not matter, there are 292 features:
   - the ink profile down the page (64 bins) and across it (32 bins);
   - a 16 × 12 ink-density grid;
   - the extent of long horizontal and vertical ruling lines;
   - the overall ink ratio and the aspect ratio.

   A standardized logistic regression is trained on them.
2. **Fusion.** Two combinations are measured with `tools/classification_experiments.py`:
   - **Late fusion:** log p = log p_text + β · log p_image. A document without text gets a uniform text
     distribution, so its image decides.
   - **Gated:** the text model's answer where it gives one; otherwise the fused distribution.

   β is chosen by 5-fold cross-validation on the development set. The 0.4 abstention threshold applies to
   the result.
3. **Macro-F1.** `evaluate_synthetic.py` reports per-type precision, recall and F1 and their macro average.
   An abstention counts as a miss for recall and as no prediction for precision.
4. **Folder suggestion** (`folder-knn-v1`, `GET /api/documents/{id}/folder-suggestions`).
   - The k = 5 filed documents most similar to this one by TF-IDF cosine vote for their folders, weighted by
     their similarity.
   - The document page shows up to three folders with their share and the number of supporting documents.
   - A user who may file documents can move it there with one click.
   - It only suggests; filing stays a person's action and is audited as before.

## Results
See "Sprint 12" in docs/synthetic_evaluation.md.

## Consequences
- The image model is measured offline. It is not yet wired into the service's automatic suggestion, which
  would need the first page image at classification time.
- Folder suggestion is computed on request from the stored text; at archive scale (thousands of documents)
  that takes about a second, and it needs no stored model.
