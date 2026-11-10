# ADR 0012: Layout analysis for tables and two-column pages

Status: accepted (Sprint 10 / Task 015)

## Context
On the synthetic corpora the CER of tables (40.7%) and of two-column pages (32.6%) was far above that of
simple pages (22.9%; test set, `script/Arabic+ara`, 200 dpi). Inspecting the output showed two systematic
failures of Tesseract's page segmentation (psm 3):
- **Ruled tables, especially invoices.** Text is grouped by column, so a row's cells come out far apart and
  out of order.
- **Two columns.** Some pages are read straight across the gutter, one line of the right column followed
  by the same line of the left column. Others psm 3 reads correctly.

Two other routes to better digits did not help, on a 29-page development sample:
- a second engine: PaddleOCR CER 40.9% and EasyOCR were both worse or far slower than Tesseract;
- re-reading lines with digits, upscaled or as single lines: digit CER 37% → 43–59%.

## Decision
`layout-v1` (`processing/layout.py`) runs after preprocessing, between quality assessment and recognition:
1. **Tables.**
   - Horizontal and vertical strokes are isolated with morphological opening.
   - A table is a connected grid at least a quarter of the page wide.
   - Its row and column positions are where the lines span most of the table.
   - Each cell is read on its own (`psm 6`) and a row is written as its cells from right to left. A missing
     vertical line inside a row merges cells.
   - The table area is blanked before the rest of the page is read, and the rows go where the table was.
2. **Two columns.**
   - A gutter is an empty vertical band in the middle 30–70% of the text body. It must be empty on many
     rows that have ink on both sides, and those rows must be balanced between the two sides.
   - Page edges are ignored, so scanner borders and shadows are not text.
   - Only when psm 3 actually merged three or more lines across the gutter are those lines split. A merged
     line has a column-sized gap of at least 2% of the page width at the gutter. That part of the page is
     then read right column first. Otherwise psm 3's order is kept.
3. What was found is recorded as a `layout` step in the page's processing steps. Word boxes stay in page
   coordinates, so highlighting and review work unchanged. `SMARTARCHIVE_LAYOUT=0` turns it off for
   ablation. Engines without block recognition fall back to psm 3.

## Evaluation
Development sample, 29 pages from corpus_v1 (local Tesseract 5.3.4, `script/Arabic+ara`):

| | CER all | Simple | Tables | Two columns | Digit CER |
|---|---|---|---|---|---|
| psm 3 | 15.6% | 7.8% | 22.2% | 17.3% | 34.8% |
| layout-v1 | **9.8%** | 7.8% | **11.9%** | **9.9%** | 33.1% |

Full runs, Tesseract 5.5.3 (docs/synthetic_evaluation.md):

| CER | Dev without | Dev with | Test without | Test with |
|---|---|---|---|---|
| All | 26.1% | 24.6% | 27.5% | 25.8% |
| Tables | 40.8% | 33.6% | 40.7% | 33.3% |
| Two columns | 31.0% | 29.1% | 32.6% | 30.4% |
| Simple | 21.3% | 21.3% | 22.9% | 22.7% |

The full-set gain is smaller than on the sample. On medium and severe scans the ruling lines are often
too broken to find, and those pages keep psm 3.

## Consequences
- Each table costs one Tesseract call per cell, about half a second per table on the sample. Simple pages
  are unaffected.
- Only ruled tables are handled. Tables without lines, and more than two columns, still rely on psm 3.
- Digits remain the main OCR weakness: Arabic-Indic five and zero are confused, and some digits come out
  as Latin look-alikes. That needs a recognizer trained on these digits, not layout.
