# Task 002 implementation and validation

Historical Task 002 record. See [Task 003 validation](task_003_validation.md) for the current pilot inventory, versioned GT workflow and adapters; Task 002 code/tests remain unchanged.

Date: 2026-10-27. The new benchmark evaluates saved text only. No historical OCR script/output, input image, legacy characterization test, requirement file or preservation manifest was rewritten. No packages installed and no commit attempted. Git remains unavailable on PATH.

## Delivered files

Created:

- `src/smartarchive/__init__.py` and `src/smartarchive/evaluation/__init__.py`: minimal package boundaries.
- `src/smartarchive/evaluation/metrics.py`: versioned normalization, deterministic edit operations, CER/WER and explicit empty denominators.
- `src/smartarchive/evaluation/validation.py`: UTF-8/JSON/hash/field validation, explicit errors.
- `src/smartarchive/evaluation/tracking.py`: exclusive run allocation, environment/source hashes, timestamps and exclusive JSON writes.
- `src/smartarchive/evaluation/runner.py`: saved-text CLI, approved GT gate, snapshots, document/corpus aggregation and CSV/JSON reports.
- `tools/benchmark_ocr.py`: repository-local launcher.
- `tests/test_benchmark.py`: synthetic metric, normalization, validation, isolation and provenance tests.
- `docs/ground_truth.schema.json`, `docs/templates/ground_truth.page.template.json`: GT schema and intentionally incomplete manual template; no institutional transcription invented.
- `docs/examples/sample_benchmark.json`: source/page-bound existing predictions, GT explicitly absent.
- `docs/ocr_benchmark.md`: exact policies, installation, PowerShell commands, GT workflow, manifest contract and limitations.
- `docs/task_002_validation.md`: this report.

Updated: `README.md`, `docs/architecture.md`, `docs/technical_backlog.md`, `docs/risks_and_decisions.md`, `docs/validation_status.md`. These document implemented portions versus the remaining platform/research work. No application areas outside evaluation were scaffolded.

## Verified checks

| Check | Result |
| --- | --- |
| Full unittest discovery | 43 passed: 37 benchmark tests plus 6 unchanged legacy characterization tests; zero failures |
| Benchmark-only tests with Python `-S` | 37 passed, verifying tests do not need site-packages/models |
| Legacy preservation verifier | 108 historical source/input/GT/result hashes match; zero failures |
| `pip check` | No broken installed requirements; historical dependency-file incompleteness remains |
| Sample benchmark with Python `-S` | Completed without site-packages, OCR engine or model invocation; both entries NOT_EVALUATED |
| Python syntax / documentation links / JSON assets | All 16 Python files parsed; documentation JSON parsed; local links valid |
| Git | Unavailable; no tracked-file/diff/commit claim |

The legacy suite emits the existing PyMuPDF `fitz` deprecation warning. This is not a test failure; legacy sources remain unchanged. Negative-path tests intentionally create malformed files in temporary directories and assert validation/nonzero exit behavior. Temporary fixtures are synthetic test data, not approved institutional references.

## Sample artifacts and interpretation

Two local demonstration runs were created while developing the task, each in a distinct directory:

- `results/benchmark/20261027T212458Z_51adf127b02c41eea63c21eefdeb7ea2/`
- `results/benchmark/20261027T212803Z_a4de388bc6fc46afb981b5ef46330620/`

Final verified sample: `results/benchmark/20261027T212856Z_d9f9fdbbf5a341c3a6367f85679feb6e/`. Independent JSON/CSV assertions confirmed two NOT_EVALUATED entries, four page/policy CSV rows and no numerical CER/WER in page or summary reports. Each invocation used a fresh directory. Historical engine version/runtime remain explicitly unknown. New result directories remain Git-ignored.

Run artifacts include exact prediction bytes, manifest bytes, source/prediction hashes, environment and evaluator code hashes, per-page statuses, and document/corpus coverage. Synthetic approved fixtures verify score calculation, reference snapshots, changed-reference rejection and aggregate formulas. They do not prove real OCR accuracy or actual human review identity.

## Exact commands

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -S -m unittest discover -s tests -p test_benchmark.py -v
.\.venv\Scripts\python.exe tools/verify_preservation.py
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -S tools/benchmark_ocr.py --manifest docs/examples/sample_benchmark.json
```

See the benchmark guide for fresh-environment setup and the manual GT workflow. `-S` disables site-packages for the model-independent checks; full legacy tests intentionally use the installed image libraries.

## Not verified / outstanding

No genuine approved GT exists, so no real CER/WER, OCR improvement or model comparison is verified. Institutional authorization, agreed reading order, taxonomy and supervisor policy acceptance remain external tasks. Human review is an attestation, not authenticated identity enforcement. Saved-text manifests cannot prove the original engine/page association. Renderer behavior, multipage TIFF/PDF handling, native OCR timeouts/failures, backup/restore, throughput and crash recovery remain unimplemented or untested. A failed output write can leave a started/partial run; never reuse it.

Task 003 recommendation: collect/review the authorized pilot and implement deterministic source/page/prediction adapters with explicit renderer/config/runtime/failure provenance, then run controlled baselines. Continue to defer enhancement/routing decisions until labelled evidence exists.
