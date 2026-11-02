# ADR 0008: Synthetic institutional corpus with exact ground truth

Status: accepted (Sprint 6 / Task 011)

## Context
The brief asks for an evaluation on 500+ pages of institutional documents (five or more types), at least 100
pages with ground truth, and 50 judged queries. No authorized institutional documents are available. The public
Arabic OCR datasets (Arabic Documents OCR Dataset, KITAB-Bench) cover OCR only: they have no document types,
archival metadata, duplicates, versions or folder structure. The evaluation of Sprint 4 measures post-editing on
reviewed pages only.

## Decision
1. `tools/synth_corpus.py` generates a documented synthetic corpus of the brief's eight types (four groups),
   with fictional organizations, people, numbers and dates. Documents are rendered as real PDFs with correct
   Arabic shaping (PyMuPDF HTML layout; each paragraph and table cell is right-to-left). Three layouts:
   simple, two columns (right column read first) and tables. Signatures and stamps are added.
   Part of the corpus becomes scans degraded with the project's own seeded levels (clean/mild/medium/severe),
   saved as PNG, JPEG, multi-page TIFF or image-only PDF.
2. The ground truth is exact because the documents are rendered from it: page text in reading order, block
   types and boxes, metadata, document type and group, and relations. About one in six documents is an exact
   copy filed elsewhere, a near-duplicate rendered again (another font or scan), or a new version with the same
   reference number.
3. Queries (subjects and reference numbers) are generated with their relevant documents. Copies and versions
   of a relevant document count as relevant.
4. `tools/evaluate_synthetic.py` imports the corpus into a separate, throw-away archive. It runs the same steps
   as an upload (OCR, metadata, classification, relations) and scores OCR (CER/WER by quality and layout),
   metadata (per field), classification (accuracy, coverage, group accuracy, confusion), relations
   (precision/recall per kind) and search (Recall@10, MRR@10, nDCG@10).
5. The corpus is reproducible from `--seed`, is not committed (`/data/synthetic/**` is ignored), and is never
   overwritten. Every number from it is reported as **synthetic**.
6. Two corpora with different seeds: `corpus_v1` (seed 2026) is the **development** set on which errors are
   inspected and rules are changed; `corpus_v2` (seed 7351) is the **test** set, used only to report numbers.
   Inspecting test-set errors is not allowed. Changes are kept only when they help on v1. They are then
   confirmed once on v2.

## Consequences
- Each later sprint (layout analysis, OCR routing, BM25/dense retrieval, classifier baselines,
  reclassification) is measured on the same corpus and seed, before and after. This gives the brief's ablation
  table without institutional data.
- Synthetic layouts and vocabulary are cleaner than real archives. Absolute numbers overstate real-world
  quality. Comparisons between methods on the same corpus remain valid. The public datasets are kept as an
  independent OCR check.
- Templates are written in-house, and the keyword classifier was written by the same team. Classification
  results on this corpus are therefore optimistic. This bias is reported, and the learned baselines of Sprint 8
  use a held-out split.
