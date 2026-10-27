# OCR Benchmark Foundations — Task 002

Task 003 update: the unchanged evaluator is now fed by [pilot inventory, versioned human review and historical prediction adapters](pilot_workflow.md). Use `tools/pilot_ocr.py compare` to prepare current page-bound predictions and latest GT. Existing Task 002 entry points/policies remain compatible. The pilot still has no human-approved real transcript.

Implemented: saved-text evaluation, versioned strict/normalized CER/WER with operation counts, approved-GT validation, isolated runs, provenance and page/document/corpus reports. Python 3.11 standard library only; no OCR engine is invoked and no winner is selected. This supports future quality-routing/layout experiments. Classification, retrieval and controlled reclassification remain planned, together with the other research components.

## Installation and Windows PowerShell

Run from the repository root. Use the existing `.venv`; for a fresh benchmark-only environment create it with `py -3.11 -m venv .venv`. No pip installation is needed for this benchmark or its new tests.

```powershell
.\.venv\Scripts\python.exe tools/benchmark_ocr.py --help
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_benchmark.py -v
.\.venv\Scripts\python.exe tools/benchmark_ocr.py --manifest docs/examples/sample_benchmark.json
```

The full suite also imports historical code requiring the existing image dependencies. They are installed in the audited environment. For a fresh full-test environment, the locally tested versions can be installed explicitly:

```powershell
.\.venv\Scripts\python.exe -m pip install Pillow==11.3.0 PyMuPDF==1.28.2 pytesseract==0.3.13 numpy==2.4.6 opencv-python==4.14.0.94
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe tools/verify_preservation.py
```

No native OCR executable, model download, GPU, package installation or PYTHONPATH setting is needed by the benchmark. The launcher locates `src/` relative to itself. With `src` on PYTHONPATH, `python -m smartarchive.evaluation.runner` is also supported.

CLI: required `--manifest PATH`; optional `--output-root PATH` (default `results/benchmark`), `--policies strict-v1 normalized-v1` (both by default). Exit 0 includes valid all-NOT_EVALUATED runs; it does not imply accuracy was measured. Validation/I/O failures exit 2.

## Ground truth and manual review

Each page has UTF-8 **without BOM** text and a `gt-v1` JSON sidecar. See [schema](ground_truth.schema.json) and [incomplete template](templates/ground_truth.page.template.json). There is deliberately no example institutional transcription. The runtime uses explicit standard-library validation, not a JSON Schema dependency; it additionally verifies actual hashes and source/page association.

1. Obtain authorization and assign a stable document ID, one-based original page number and document-level pilot/dev/test split. All variants must represent the same complete page. The evaluator checks declared IDs/hashes, but cannot verify page content without rendering.
2. Copy the template into a local GT directory. Transcribe manually from the source in an editor. **Never label OCR output as verified GT.** Resolve illegible text with a reviewer; unresolved pages stay unapproved. No guessed words or hidden exclusion mask.
3. Preserve logical Arabic text, visible punctuation and diacritics. Do not reverse characters. Agree on reading order before evaluation. For an inspected two-column page, a possible order is spanning header, complete right column top-to-bottom, complete left column top-to-bottom. Record actual ordered region descriptions in `reading_order`, including tables/footnotes/mixed-language blocks as needed. This array documents transcript sequence; it does not rearrange the text.
4. Fill source hash, document ID/page, relative `text_path`, final text hash, transcriber ID and reading order. Keep review status `draft` and reviewer/time null during writing.
5. A different person checks the entire transcription and ordering. `reviewed` records review but remains excluded from scoring. Set `approved`, reviewer ID and an ISO-8601 timestamp with timezone only after corrections. The final hash pins exact bytes, including line endings. Any edit requires re-review and a new hash.
6. Reference the sidecar in a new manifest. This is a local attestation workflow, not authenticated identity/signature enforcement; reviewer authentication remains future work. No real transcript was approved by this task.

Useful commands, with manual transcription/review between steps:

```powershell
New-Item -ItemType Directory -Path data/ground_truth/sample-001
Copy-Item docs/templates/ground_truth.page.template.json data/ground_truth/sample-001/page_001.json
# Create page_001.txt manually in an editor; do not paste an OCR prediction.
(Get-FileHash data/input/sample.png -Algorithm SHA256).Hash.ToLowerInvariant()
(Get-FileHash data/ground_truth/sample-001/page_001.txt -Algorithm SHA256).Hash.ToLowerInvariant()
[DateTimeOffset]::UtcNow.ToString('o')
```

Paste hashes/time into the sidecar at the appropriate step. PowerShell 5 `Set-Content -Encoding UTF8` writes a BOM; use an editor's UTF-8-without-BOM setting. The evaluator rejects BOMs explicitly instead of stripping them silently.

Human-verified blank page: set `is_blank: true` and use a zero-byte transcript. Whitespace-only files do not qualify. Nonblank references must have non-whitespace content. Approved empty references have null CER/WER with `UNDEFINED_EMPTY_REFERENCE`, retaining insertion counts; no artificial denominator of 1. A normalization-empty reference has the same rate behavior.

## Metric policy

CER = code-point Levenshtein distance / reference code-point count. WER = token Levenshtein distance / reference token count. Operations transform reference into hypothesis. Ties prefer substitution, deletion, insertion; equal symbols match. Another optimal alignment may have different operation categories. Rates are not capped at 1 or rounded before aggregation. Code points are not grapheme clusters.

| Choice | strict-v1 | normalized-v1 |
| --- | --- | --- |
| Unicode | No changes | Compatibility-fold only Arabic presentation blocks U+FB50–FDFF and U+FE70–FEFF per character, then global NFC |
| Arabic marks | Preserve | Remove U+0610–061A, 064B–065F, 0670, 06D6–06DC, 06DF–06E4, 06E7–06E8, 06EA–06ED |
| Tatweel U+0640 | Preserve | Remove |
| Hamza/alef, ya/maqsura, ta marbuta | Preserve distinctions | Preserve distinctions; NFC composes canonical letter+mark sequences before mark removal |
| CER whitespace | Preserve CR/LF, trailing spaces/newlines and all other code points | Collapse Unicode whitespace to ASCII space; trim edges |
| Punctuation, case, digits | Preserve | Preserve, including Arabic versus Latin forms |
| Non-Arabic compatibility forms | Preserve | Preserve; no global NFKC |
| WER tokens | Python Unicode whitespace split | Same split after normalization |

Strict WER ignores whitespace-only differences through tokenization, while strict CER measures them. Punctuation stays attached to words; no Arabic linguistic tokenizer is implied. Mark removal is a sensitivity policy, not a claim that diacritics are irrelevant. Always report policy IDs; policy changes need new versions.

Identical normalization is applied to reference and hypothesis. Raw byte snapshots are preserved separately; JSON includes the derived `reference_evaluated`/`hypothesis_evaluated` strings. Nothing edits the input files.

Document/corpus aggregation sums **page-level** operations and denominators per variant/policy; no cross-page alignment. Micro rate = sum edits / sum reference units. Macro rate = mean of defined page rates; `defined_page_rates` reports its denominator. Blank-page insertions contribute to micro totals even though their page rates are undefined. Zero total reference units gives null micro rate. Missing/unapproved/invalid pages are excluded and counted separately. Different variant coverage must be considered before comparison.

## Input manifest

[sample_benchmark.json](examples/sample_benchmark.json) points to existing full-page/RTL-region outputs and declares GT unavailable. Historical version/runtime are unknown, stored as null; current Tesseract version is never substituted for an unknown historical version.

Top level: `schema_version: "benchmark-v1"`, nonempty `entries` array. Unknown fields are rejected. Required entry fields:

| Field | Contract |
| --- | --- |
| document_id, page, split | Nonempty ID, positive integer, pilot/dev/test; one source hash/split per document |
| source_path, source_sha256 | Existing original file, matching lowercase SHA-256 |
| variant | Stable label; engine/language/config/preprocessing consistent within run |
| prediction_path | Nonempty UTF-8 text without BOM/unsupported controls |
| ground_truth_path | null when unavailable; otherwise valid sidecar path |
| engine | Object: name string; version string or null for unknown |
| language | Nonempty description such as ara or ara+eng |
| configuration | Object: PSM/OEM/DPI/renderer where known; state unknowns explicitly |
| preprocessing | Object describing historical processing, including unknowns |
| ocr_runtime_seconds | Finite nonnegative number or null; distinct from evaluator wall time |

Manifest paths resolve relative to its file; GT text paths resolve relative to the sidecar. Absolute paths are allowed. Duplicate document/page/variant and identical source bytes across splits are errors. Byte-different scans of the same document still need human leakage review. To evaluate real GT, create a new local manifest replacing null with approved sidecar paths. Do not alter historical predictions to repair encoding; separately identify/document any derivative.

## Status and artifacts

- Declared GT null: `NOT_EVALUATED / MISSING_GROUND_TRUTH`.
- Valid draft/reviewed GT: `NOT_EVALUATED / GROUND_TRUTH_NOT_APPROVED`.
- Missing configured file, invalid encoding/JSON, empty nonblank reference, changed transcript hash, invalid review, mismatched source/page, duplicate or empty prediction: `VALIDATION_ERROR`, exit 2. A missing configured GT file differs from explicitly unavailable GT.

Empty predictions are rejected as ambiguous artifacts. The metric API can score empty hypotheses as deletions, but a future OCR adapter must distinguish failed OCR from successfully empty recognition explicitly.

Each exclusive UTC/UUID run directory contains `started.json`, exact `input_manifest.json`, final `report.json`, `pages.csv`, `summaries.csv`, and numbered entry directories with exact `prediction.txt`, plus `reference.txt`/`ground_truth.json` when valid GT is supplied. Draft/reference bytes are retained too. A forced directory collision fails without overwrite. Output I/O interruption may leave started/partial artifacts; resolve the cause and start a new run, never reuse that directory.

Provenance: run ID, UTC timestamps, evaluator wall time, source/prediction/GT/manifest hashes, paths, input engine/version/language/config/preprocessing/runtime, Python/platform/Unicode database and evaluator source hashes. Sources are hashed rather than copied. Page assignment and historical engine metadata remain supplied assertions; text files alone cannot prove them.

## Limits and Task 003

No approved real GT exists; synthetic tests validate arithmetic/workflows, not OCR quality. Reading order is human-declared, not geometrically assessed. Exact Levenshtein is quadratic time with linear-row memory; large-page throughput has not been established.

Task 003 delivers deterministic source/page inventory (including TIFF/PDF page checks), immutable manual-review version history and seven historical prediction bindings. Actual independent transcripts and institutional pilot expansion remain pending. Native OCR execution/failure/timeout adapters remain future work. See its workflow/validation report before current comparisons. No enhancement/routing gains are claimed here.
