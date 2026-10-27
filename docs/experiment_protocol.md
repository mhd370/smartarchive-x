# Experiment POC-001: Arabic OCR baseline

> Audit update (2026-10-27): one sample image and experimental results now exist,
> but no ground-truth transcripts or measured CER/WER are present. The historical
> status below describes the initial POC, not the current repository. Numbered
> research-source mappings remain unverified because the original document is
> not included. See repository_audit.md and technical_backlog.md before new runs.

**Status:** Ready for real inputs; no real samples supplied, so no measured accuracy yet.

## Research questions
- RQ1: How do available Arabic OCR baselines differ on our target institutional documents?
- RQ2: How do quality and page layout affect CER, WER, reading order and processing time?
- RQ3 (next phase): Can routing based on quality/layout improve performance against fixed OCR baselines?

## Planned dataset
- Start: 10–20 authorized pages as engineering smoke/feasibility.
- Expand: 100–200 manually transcribed pages from the dean's recommended scope for actual evaluation, stratified by type, layout and quality.
- Preserve original file and SHA-256, do not upload private institutional records to third-party services without permission.

## Execution & quality gates
1. Input integrity: hash preserved, page numbers stable, valid page renders.
2. Extraction: every engine either produces raw text/boxes or logs a failure without hiding it.
3. Evaluation: manually verified transcription and matching reading order before CER/WER; GT missing means NULL metric.
4. Reproducibility: keep seed when training begins; log version/hardware/config/latency and dataset split.
5. Baseline analysis: grouped CER/WER and time by layout and scan quality; include examples of errors.
6. Advancement gate: decide OCR router only after controlled comparisons, not arbitrary 0.80/0.55 thresholds.

## Traceability
- Source sections 7.1–7.4: preprocessing/layout engines
- Section 8: realistic datasets and transcription
- Section 10: proposed adaptive routing
- Sections 20–23: tests, comparisons, CER/WER and resource use

## Limitations
- This v0.1 script does not implement image enhancement, confidence calibration, layout reading-order evaluation, cross-page entities, model tuning, or adaptive routing.
- WER on Arabic can vary with tokenization, and CER changes under normalization; this initial evaluation uses only whitespace normalization and must report that choice.
- Source proposes a wider evaluation than this POC and needs subsequent engineering/research milestones.
