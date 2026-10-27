# SmartArchive-X

Intelligent Arabic institutional document archiving graduation project. **Current status: OCR experiments, benchmark foundations and a pending-GT pilot with historical prediction adapters; not a complete archival application.** Target: Windows 11, Python 3.11.9, one developer, approximately eight weeks.

## Research scope

1. Quality-Aware OCR Routing.
2. Layout-Aware Text Reconstruction.
3. Reliability-Gated Multimodal Document Classification.
4. Confidence-Aware Hybrid Search and Indexing.
5. Controlled Document Reclassification.

Original preservation, metadata, human review and traceable search support these components. The scope above comes from the supplied brief. The supervisor's original document is absent; historical numbered source-section references are unverified.

## Existing functionality

| Script | Implemented experiment | Limitations |
| --- | --- | --- |
| `src/run_ocr.py` | PDF/image baseline, Tesseract and optional Paddle adapter, hashes, word boxes, latency, CER/WER when GT exists | Reused outputs overwritten; Paddle unvalidated |
| `compare_ocr.py` | Original/enhanced/fixed-column OCR | Sample-specific crops, fixed output path, processing on import |
| `quality_analyzer.py` | Heuristic quality features, enhancement candidates, optional OCR, original byte copy/hash | Score is not calibrated reliability or OCR accuracy |
| `layout_ocr.py` | Two-column geometry and RTL region OCR | Spanning headings not reliably handled |
| `layout_ocr_v02.py` | Header heuristic, reconstruction, baseline-difference diagnostics | Differences are not verified omissions |
| `layout_ocr_v03.py` | Region versus line OCR, optional GT metrics | Imports v02; possible text loss; skip-ocr may still invoke OCR |

One input image and saved results exist. The dataset CSV contains only its header; no ground-truth transcripts exist. **No scientifically validated OCR improvement has been established.** Character counts, image scores and OCR confidence cannot establish accuracy.

Task 002 adds `src/smartarchive/evaluation/`: approved-GT validation, strict/normalized CER/WER with operation counts, isolated runs, provenance and page/document JSON/CSV reports. See the [benchmark guide and manual GT workflow](docs/ocr_benchmark.md).

```powershell
.\.venv\Scripts\python.exe tools/benchmark_ocr.py --manifest docs/examples/sample_benchmark.json
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_benchmark.py -v
```

The benchmark needs Python 3.11 only. The sample reports `NOT_EVALUATED` because GT is absent. Full installation/test commands and templates are in the guide.

Task 003 adds a deterministic [pilot manifest](docs/pilot/dataset.json), seven explicit historical whole-page/region/line bindings, and immutable transcription revisions with independent review/approval. No real transcription or approval has been invented. The one sample is literary/educational, not representative institutional evidence. See the [pilot workflow](docs/pilot_workflow.md) for exact inspection, manual submission, review, approval and comparison commands.

```powershell
.\.venv\Scripts\python.exe tools/pilot_ocr.py inspect
.\.venv\Scripts\python.exe tools/pilot_ocr.py inventory --check
.\.venv\Scripts\python.exe tools/pilot_ocr.py compare
```

The pilot decodes images with existing Pillow (PDFs use existing PyMuPDF). It never invokes OCR and does not add dependencies. Pending/unapproved GT yields `NOT_EVALUATED`. [Task 003 validation](docs/task_003_validation.md) records verification and changed files.

FastAPI, durable archiving, metadata workflows, calibrated routing, classification, hybrid retrieval, authenticated review and controlled reclassification are **proposed and unimplemented**. Local GT review attestations are now supported by the benchmark.

Read the [audit](docs/repository_audit.md), [architecture and proposed directory structure](docs/architecture.md), [backlog](docs/technical_backlog.md), [risks and decisions](docs/risks_and_decisions.md), and [validation status](docs/validation_status.md).

## Setup in PowerShell

Run from the repository root:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip check
```

The baseline requirements include Pillow, PyMuPDF and pytesseract. **NumPy and OpenCV are required by the quality/layout experiments but absent from the baseline requirements.** Both are installed in the audited environment; see validation status for versions. Dependency reconciliation is a benchmark prerequisite. No dependencies were added during this audit.

Tesseract is a separate native installation. Verify its version and Arabic/English language data:

```powershell
& 'C:\Program Files\Tesseract-OCR\tesseract.exe' --version
& 'C:\Program Files\Tesseract-OCR\tesseract.exe' --list-langs
$env:PATH = 'C:\Program Files\Tesseract-OCR;' + $env:PATH
```

The PATH assignment affects the current session. The baseline resolves Tesseract through PATH; other scripts expose a tesseract argument. Paddle is optional, requires its compatible runtime/models in addition to `requirements-paddle.txt`, and was not tested. Do not require it for the first benchmark.

## Safe experimental runs

**Never reuse an existing output directory.** Legacy scripts do not enforce this. Keep outputs separate from inputs and use a new GUID per invocation. Do not rerun `compare_ocr.py` until its fixed output path is isolated.

```powershell
$baselineOutput = 'results/manual_baseline_' + [guid]::NewGuid().ToString('N')
.\.venv\Scripts\python.exe src/run_ocr.py --input data/input --output $baselineOutput --engines tesseract
$layoutOutput = 'results/manual_layout_' + [guid]::NewGuid().ToString('N')
.\.venv\Scripts\python.exe layout_ocr_v02.py --input data/input/sample.png --output $layoutOutput --skip-ocr
```

Use authorized samples. Historical baseline GT naming is `<source_stem>__p001.txt`; v03 uses `page_001.txt`. These scripts remain unchanged. The new benchmark uses explicit source/page-bound sidecars and versioned policies in its guide. Missing GT means unavailable metrics, never zero error.

## Foundation checks

```powershell
.\.venv\Scripts\python.exe tools/verify_preservation.py
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

The first compares pre-audit hashes of experimental sources, inputs and results; it is not a backup. Tests cover benchmark metrics/validation/provenance plus preserved legacy characterization. They do not establish OCR accuracy. Inputs, GT and outputs remain ignored and need a separate backup.

## Next engineering task

Task 004 should complete authorization and actual independent transcription/review, expand toward representative institutional pages and analyze pinned historical baselines. Source inventory, versioned review and historical adapters are implemented; human labels and native OCR execution adapters remain outstanding. No routing thresholds or enhancements should be promoted from one unlabeled page.
