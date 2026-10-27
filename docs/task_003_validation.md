# Task 003 — implementation and validation

Date: 2026-10-27. Task 002 metric/runner code, all existing tests, historical OCR sources and every prior output remain unchanged. No packages installed, OCR rerun, genuine transcript created, review approved or commit attempted.

## Delivered

- Deterministic [pilot manifest](pilot/dataset.json): one source document, one 665×708 page, original SHA-256, full-hash ID, decoded page hash/dimensions and decoder versions. GT/reading-order status is PENDING; authorization is PENDING_CONFIRMATION. Five saved original-image copies match its page pixels. Visual inspection identified a literary/educational two-column page with a spanning heading, not a representative institutional dataset.
- [Historical bindings](pilot/historical_bindings.json): seven explicit whole-page/region/line associations across the three preserved layout experiments, validated against source bytes, page pixels, IDs, geometry and available aggregate evidence.
- Immutable manual transcription revisions and independent draft -> reviewed -> approved attestations, timestamps/identities, source/text hashes, completeness checks, version guards, correction reasons and hash-linked history. The latest correction resets the gate; older approvals are retained but not selected by the current pilot comparison.
- Task 002 integration with byte-identical prediction snapshots and separate strict/normalized reports. No rankings or winner selection.
- [PowerShell workflow](pilot_workflow.md): inspection, manual submission, independent review, approval, correction and comparison commands.
- [Unevaluated example](examples/pilot_unevaluated_summary.json) derived from a real run; no reference text or numerical accuracy was invented.

## Verified checks

| Check | Result |
| --- | --- |
| Full unittest discovery | **76 passed**, zero failures: 33 new pilot tests, 37 existing benchmark tests, 6 existing legacy tests |
| Synthetic review lifecycle | Draft/reviewed excluded, approved evaluated; correction preserves history and resets gate; stale versions, incomplete labels, missing attestations, wrong reviewer and modified snapshots rejected |
| Association/order validation | Wrong pages/pixels, ambiguous identical pages, filename inference, duplicate IDs/bindings, invalid boxes/order, missing/duplicate line labels and inconsistent aggregates rejected |
| Unicode/metrics | Existing policy tests preserved; new mixed-Arabic/presentation-form/diacritic regression uses unchanged metrics; raw CRLF snapshots retained |
| Multipage inventory | Synthetic two-frame TIFF and two-page PDF recorded correctly; malformed raster rejected |
| Deterministic inventory check | PASS against actual source and related image copies |
| Original preservation verifier | **108 files unchanged** |
| Task 003 pre-edit snapshot | **141 files unchanged**, including all Task 002 code/tests and earlier benchmark outputs |
| Installed dependency consistency | `pip check`: no broken requirements; no new dependency added |
| Actual pending-GT comparison | Seven imports succeeded; all NOT_EVALUATED; page metrics absent and summary rates null |
| Syntax / documentation / JSON | Python and documentation JSON parsed, local links verified |
| Git | Not available on PATH; no commit or tracked-file status asserted |

The legacy PyMuPDF `fitz` deprecation warning remains unchanged and did not fail tests. The new PDF inventory uses `pymupdf`. Tests that exercise approval use only synthetic temporary fixtures, never the real sample or its OCR as GT. The full CLI submit/review/approve/compare path is tested with synthetic inputs.

During initial adapter execution, a producer-consistency check correctly failed on Windows CRLF versus in-memory LF counts. The check was corrected to compare a declared transient LF view while retaining every raw byte in imports and metrics. The final seven-import run passes. No historical text or Task 002 policy was changed to make it pass.

## Actual example run

Bundle: `results/pilot/20261027T214440Z_cd0ab1bf37724801b071af1d2bfd0842/`.

Report: `results/pilot/20261027T214440Z_cd0ab1bf37724801b071af1d2bfd0842/evaluation/20261027T214440Z_4ee5808f664a45f69c84df6328aadac3/report.json`.

The bundle contains exact imported prediction bytes, `benchmark.json` and `associations.json` (dataset/bindings, input evidence hashes, GT version/status and adapter limitations). The evaluator adds its usual manifest/raw snapshots, environment/source hashes, page CSV, summary CSV and JSON report. All seven entries use `MISSING_GROUND_TRUTH`; `data/ground_truth/` still contains only its original `.gitkeep`. The tracked example summary records the source report path and SHA-256 for inspection.

New bundles are ignored local artifacts. Original images and OCR text are neither moved nor rewritten. v3 region component OCR was never saved separately, so only its metadata ordering/geometry and aggregate length can be checked; this limitation is explicit in provenance. Historical invocation settings are labelled defaults/unknowns rather than reconstructed as known facts.

## Created and modified files

Created:

- `src/smartarchive/evaluation/pilot.py`: deterministic all-page inventory, pixel fingerprinting and dataset validation.
- `src/smartarchive/evaluation/ground_truth.py`: immutable revision/review workflow and current-state validation.
- `src/smartarchive/evaluation/historical.py`: explicit v1/v2/v3 saved prediction adapters and benchmark bundle preparation.
- `src/smartarchive/evaluation/pilot_cli.py`: inventory/inspect/submit/review/approve/compare commands.
- `tools/pilot_ocr.py`: repository-local launcher.
- `tools/verify_snapshot.py`: read-only pre-task preservation verifier.
- `tests/test_pilot.py`: 33 synthetic tests, including CLI lifecycle.
- `docs/pilot/dataset.json`, `docs/pilot/historical_bindings.json`: inventory and explicit associations.
- `docs/task_003_preservation.json`: pre-edit hashes of 141 existing code/test/tool/data/result files; detects changes but is not a backup.
- `docs/examples/pilot_unevaluated_summary.json`: actual-run derived example.
- `docs/pilot_workflow.md`, `docs/task_003_validation.md`: operational instructions and this report.

Updated: `README.md`, `docs/ocr_benchmark.md`, `docs/architecture.md`, `docs/technical_backlog.md`, `docs/risks_and_decisions.md`, `docs/validation_status.md`, `docs/task_002_validation.md`. Updates identify implemented versus pending work and link the current workflow/status. Task 002 schema, metrics, validation/runner, examples and tests remain compatible and unchanged.

## Reproduce verification

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe tools/verify_preservation.py
.\.venv\Scripts\python.exe tools/verify_snapshot.py
.\.venv\Scripts\python.exe tools/pilot_ocr.py inventory --check
.\.venv\Scripts\python.exe tools/pilot_ocr.py inspect
.\.venv\Scripts\python.exe tools/pilot_ocr.py compare
.\.venv\Scripts\python.exe -m pip check
```

Every `compare` creates a new bundle. For evaluated reports, follow the manual transcription/review/approval steps in the workflow guide; no such real approval has occurred here.

## Outstanding work and Task 004

No real CER/WER, improvement claim, representative institutional dataset or actual human-verified transcript is delivered. Authorization, independent review and convention acceptance require humans. Local identity is an attestation, not authenticated access; hashes/history are not tamper-proof storage. Native OCR execution/timeouts, complete producer invocation capture, input resource bounds, interrupted-workflow recovery, backup/restore and performance validation remain open. Archived benchmark manifests pin older approved versions; prepare a fresh pilot comparison for current official results.

Task 004 should complete the authorized human-labelled pilot, expand toward representative institutional pages, freeze approved references and analyze historical baseline errors before any routing/enhancement changes. The supervisor's five research components remain the target; this task supplies evaluation infrastructure rather than implementing or validating them.
