# SmartArchive-X

Intelligent Arabic institutional document archiving graduation project. **Current status: first local full-stack archive application plus preserved OCR research tools.** FastAPI + SQLite backend; Next.js + TypeScript + Tailwind Arabic RTL frontend. Target: Windows 11, Python 3.11.9, one developer, approximately eight weeks.

## Run the web application

From the repository root, install dependencies:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe tools/frontend.py ci
```

Node.js LTS is required; the helper also detects the local portable runtime under `.tools/`. Run these in two PowerShell terminals:

```powershell
# Terminal 1 — API
.\.venv\Scripts\python.exe -m uvicorn smartarchive.api.app:app --app-dir src --host 127.0.0.1 --port 8000
```

```powershell
# Terminal 2 — frontend
$env:NEXT_PUBLIC_API_URL = 'http://127.0.0.1:8000'
.\.venv\Scripts\python.exe tools/frontend.py run dev
```

Open **http://127.0.0.1:3000**. Upload an authorized PDF/image, find it in Documents, preview/download its unchanged original and refresh the dashboard to see persisted counts. Metadata/audit live in `storage/archive.sqlite3`; originals live in `storage/originals/`. No fake documents or statistics are seeded.

Uploads are stored and validated; **OCR/classification are not connected**, so extraction/confidence results remain unavailable. This is a loopback-only prototype without authentication, not a public institutional deployment. See [startup/configuration/API documentation](docs/web_application.md) and [Task 005 validation](docs/task_005_validation.md).

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

Task 004 adds an offline, source-side RTL transcription workspace and read-only frozen-reference view. New pilot comparisons include per-variant/page accuracy CSV and error-analysis JSON/Markdown, using unchanged metrics and GT approval logic. **Human transcription and independent approval are still required; no real accuracy is available.** Follow the [first Arabic GT handoff](docs/first_arabic_gt.md) for exact PowerShell steps. Git access and baseline `cbea099` are confirmed via `C:/Program Files/Git/cmd/git.exe`; no commit is created by these tasks.

```powershell
.\.venv\Scripts\python.exe tools/pilot_ocr.py inspect
.\.venv\Scripts\python.exe tools/pilot_ocr.py inventory --check
.\.venv\Scripts\python.exe tools/pilot_ocr.py compare
```

The pilot decodes images with existing Pillow (PDFs use existing PyMuPDF). It never invokes OCR and does not add dependencies. Pending/unapproved GT yields `NOT_EVALUATED`. [Task 003 validation](docs/task_003_validation.md) records verification and changed files.

Task 005 implements FastAPI ingestion, SQLite document/audit persistence, original storage and the connected web interface. OCR routing, extraction workflows, classification, hybrid retrieval, authenticated review and controlled reclassification remain **unimplemented application features**. Local GT review attestations continue to work in the separate benchmark tools.

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

Task 006 should connect a versioned, bounded OCR processing job and human-review state to the stored-document lifecycle, while completing approved GT for objective evaluation. Preserve full-page baseline/fallback and traceability; do not invent confidence or claim improvements without evidence. Institutional deployment also requires authentication/access control and backup/recovery.
