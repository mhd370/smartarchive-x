# Testing and validation status

This document records Task 001. Current pilot/review/adapter results are in [Task 003 validation](task_003_validation.md); benchmark foundations are in [Task 002 validation](task_002_validation.md). Historical audit observations below are preserved.

Executed on 2026-10-27 in the supplied Windows workspace using `.venv/Scripts/python.exe`. No packages were installed and no historical experiment was rerun into its original directory.

## Results

| Check | Result | Scope/limits |
| --- | --- | --- |
| Python runtime | PASS: 3.11.9 | Local virtual environment, not global Python alias |
| `python -m pip check` | PASS: no broken requirements | Installed-package compatibility only; does not prove requirements files are complete |
| AST syntax parsing | PASS: all 8 Python sources | Six legacy scripts plus test/verifier; no bytecode rewriting required |
| `python -m unittest discover -s tests -v` | PASS: 6 tests | Arabic identity/diacritics; insert/delete/substitute denominators; whitespace-policy difference; empty reference; BOM handling; first-frame TIFF limitation |
| `python tools/verify_preservation.py` | PASS: 108 files, zero changes/missing | All pre-existing experimental sources, input/GT files and results; new files are outside the snapshot |
| Historical ZIP CRC checks | PASS: no corrupt members | v02: 15 entries; v03: 57 entries; not semantic OCR validation |
| Source versus saved quality-report hash | PASS | `sample.png` matches historical SHA-256 `f000d4598d57c79c5f3db5f308c26960c0c73170c7d30862efad6d66106b40cc` |
| Native Tesseract/version/languages | PASS | `C:/Program Files/Tesseract-OCR/tesseract.exe`, v5.5.3.20260724; ara, eng, osd |
| Baseline Tesseract smoke | PASS: process exit 0, nonempty text, no engine error | One page; GT unavailable and CER/WER explicitly null; no accuracy claim |
| Git status/diff | UNAVAILABLE | `git` not on PATH; no `.git` entry visible in workspace root; no commit or tracked-file status claimed |

Smoke artifacts were created only under `results/audit_smoke_f9a7efd21a79454cb9ff77594d5dca80/`: JSON and metrics CSV. PATH was supplied to the child process to resolve the installed Tesseract. Recorded OCR stage time was 2.0569 seconds, a single local observation rather than a performance comparison. Generated caches may be added by imports and remain ignored.

The installed PyMuPDF emits a `fitz` import deprecation warning. Existing scripts were preserved; a future adapter should use the supported import. No runtime test failure resulted.

## Environment snapshot

| Package | Installed version |
| --- | --- |
| NumPy | 2.4.6 |
| opencv-python | 4.14.0.94 |
| Pillow | 11.3.0 |
| PyMuPDF | 1.28.2 |
| pytesseract | 0.3.13 |
| packaging | 26.3 |
| pip | 26.2.2 |
| setuptools | 65.5.0 |

This snapshot records observation, not a new dependency recommendation or lock file. NumPy/OpenCV are absent from baseline requirements. Paddle/PaddleOCR are not installed in the observed package list and were not tested.

## Interpretation and untested areas

Characterization tests intentionally demonstrate legacy limitations; passing them does **not** mean those limitations are corrected. They are not acceptance tests for a future metric policy. No pre-existing test suite or CI configuration was found. No CER/WER evaluation is possible with the current unlabeled dataset. No classification, retrieval, review, API or reclassification exists to test.

PDF/corrupt-input/resource-limit paths, output-write failures, engine timeouts, fallback visibility, multiple-document identity collisions and Unicode output paths need benchmark implementation tests. Quality/layout end-to-end experiments were not rerun during this audit. Archived text correctness and visual reading order were not independently validated. Original supervisor material and dataset authorization could not be inferred from repository content.

## File changes

Updated:

- `README.md`: accurate current status, scope, setup limitations, safe run commands and documentation links.
- `.gitignore`: recursive local data/results protection, Python/tool caches, secrets and proposed storage.
- `docs/experiment_protocol.md`: dated status correction while preserving historical protocol text.

Added:

- `docs/repository_audit.md`: inventory, evidence, findings and minimum benchmark prerequisites.
- `docs/architecture.md`: proposed package tree, contracts, five research components and gradual migration.
- `docs/technical_backlog.md`: priorities, dependencies, acceptance evidence and indicative eight-week sequence.
- `docs/risks_and_decisions.md`: risks, recorded decisions and unresolved choices/owners.
- `docs/validation_status.md`: this report.
- `docs/preservation_manifest.json`: pre-edit hashes/sizes for 108 historical files.
- `tools/verify_preservation.py`: read-only byte-preservation check.
- `tests/test_legacy_contracts.py`: six characterization tests.

New local smoke outputs are listed above and remain ignored. No existing Python experiment, input image, GT file, saved output or requirement file was modified. No application scaffolding, platform feature or major refactoring was implemented.

## Completion and next action

Repository audit, proposed architecture, README/ignore update, prioritized backlog, risk/decision register and executable foundation checks are complete. Findings are documented rather than silently repaired in historical experiments. Full OCR Benchmark, canonical adapters, data transcription and platform features remain unimplemented.

Next engineering task: **B01/B02 benchmark foundation**: agree GT/metric semantics and implement exclusive run directories with lineage; then B03-B05 adapters/preflight/tests before B06 benchmark comparisons.
