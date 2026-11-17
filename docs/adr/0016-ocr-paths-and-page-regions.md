# ADR 0016: OCR paths, page regions and the multimodal suggestion in the service

Status: accepted (Sprint 13 / Task 018)

## Context
After Sprint 12, three items of the brief were still only partly done:
- detecting text, table, **image and heading** regions: tables and columns were found (ADR 0012), but not
  images (stamps, logos, signatures) or headings;
- choosing the **most suitable OCR route automatically**: every page went through one Tesseract path, and the
  other engines (PaddleOCR, EasyOCR) had been measured and rejected (worse and 7–40 times slower);
- three OCR paths with raw and corrected text.

The multimodal classifier of ADR 0015 was measured offline but not used by the service.

## Decision
1. **OCR paths** (`processing/paths.py`, `ocr-paths-v1`). Every path reads the same prepared page, so the word
   boxes map back to the original in the same way:
   - `standard`: the prepared page (the single path until now);
   - `binarized`: an adaptive local-mean threshold of the prepared page, for faint or blotchy scans. Only the
     OCR input is thresholded; the original and its colours are never changed (ADR 0003);
   - `upscaled`: the page enlarged 1.5×, for small print;
   - `model-ara`: the same page read with the `ara` model alone instead of `script/Arabic+ara`.

   **Choice per page** from the engine's own output, never from ground truth:
   - `confidence`: the highest character-weighted mean word confidence;
   - `confident-chars`: the largest sum of confidence × length.

   With a gate below 1, the other paths are read only when the standard path's confidence is below it.
   `tools/ocr_paths_experiment.py` reads a stratified sample of pages on every path once, then scores every
   path set, rule and gate from the stored results. The configuration is chosen on the development set and
   measured once on the test set. The service default (`SMARTARCHIVE_OCR_PATHS`, `_RULE`, `_GATE`) follows that
   result: see "Sprint 13" in docs/synthetic_evaluation.md. Each run records the paths, rule and gate in its
   parameters, and each page records the confidence of every path read and the one chosen.
2. **Regions** (`processing/regions.py`, `regions-v1`), recorded per page as a `regions` step with boxes
   normalized to the original page:
   - headings: centred OCR lines, narrower than 80% of the text block, merged when consecutive;
   - stamps: roughly square, mostly hollow ink components 5–30% of the page wide, or coloured ink;
   - figures: other large non-table ink components (logos, signatures, drawings).

   The thresholds were set by hand on drawn examples and **not tuned** on either corpus.
   `tools/region_experiment.py` scores them against the ground-truth header/title and stamp boxes using the
   stored OCR lines, with no new OCR. The document page can draw the regions over the preview.
3. **Multimodal suggestion in the service.**
   - Training stores the first-page layout features of each confirmed document (`document_images`,
     migration 9; rendered once at 72 dpi from the verified original).
   - When at least two categories have three such documents, an image model is trained next to the text model.
   - Suggestions fuse them with β = 1 (ADR 0015) and are recorded as `tfidf-svm-v1+visual-layout-v1`.
   - A page whose OCR text is empty is still classified from its image.
   - Without a readable original the suggestion falls back to the text model.

## Results (synthetic corpora)
Regions:

| Corpus | Heading precision | Heading recall | Stamp precision | Stamp recall |
| --- | --- | --- | --- | --- |
| Development, 499 pages | 83.8% | 62.8% | 100% | 71.2% |
| Test, 624 pages | 80.6% | 58.1% | 99.7% | 71.1% |
| Test, born-digital / clean / mild pages | 85.5–98.6% | 70.6–78.0% | 100% | 100% |
| Test, medium / severe scans | 9.1% / 12.0% | 29.3% / 9.3% | — | 3.2% / 0% |

On readable pages every stamp is found and almost every predicted heading is a real header or title. On
degraded scans the ink no longer forms clean rings, and the OCR lines are fragments, so both detectors fail.
That limit is reported as it stands, not hidden.

OCR paths, test set (103 pages; chosen on the development set):

| Configuration | CER | OCR s/page |
| --- | --- | --- |
| `standard` alone | 32.1% | 3.1 |
| standard + binarized + upscaled, `confident-chars`, gate 1 | **27.8%** | 10.4 |
| Oracle (best path per page) | 26.4% | 12.0 |

- **Development set:** 31.0% with `standard` alone, 27.2% with the chosen configuration, 26.2% for the oracle.
- **Where the test-set gain comes from:** mostly severe scans (95.4% → 78.3%); medium scans lose 1.1 points.
- **Service default:** these three paths, with `confident-chars` and gate 1. `SMARTARCHIVE_OCR_PATHS=standard`
  returns to the single, faster path.

Full tables are in docs/synthetic_evaluation.md, "Sprint 13".

## Consequences
- More paths cost more OCR time on the pages where they run; the gate limits this to low-confidence pages.
- Regions are evidence shown to people. Nothing else in the archive depends on them.
- Older archives get image features lazily, the first time a document is used for training or suggestion.
