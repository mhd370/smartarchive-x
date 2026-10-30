# Task 004 — validation and human handoff

Date: 2026-10-27. Engineering preparation is delivered. **Actual human transcription and independent approval are the stopping boundary.** The real source has no submitted reference; no numerical real OCR accuracy is verified.

## Repository/source inspection

Read the pilot workflow, benchmark policy, Task 003 validation, target architecture and current source/tests before editing. Pilot source: `data/input/sample.png`, page 1, 665×708, SHA-256 `f000d4598d57c79c5f3db5f308c26960c0c73170c7d30862efad6d66106b40cc`. Live GT is PENDING/version 0, and the GT directory still contains only its original keep file. The source is literary/educational, so institutional generalization remains unsupported.

Git is installed at `C:/Program Files/Git/cmd/git.exe` although absent from the shell PATH. Repository access, clean initial status and baseline HEAD were confirmed: `cbea099719e6a6c97839907c141bccfa791a7440` (`chore: establish SmartArchive-X engineering baseline`). No commit, reset, cleanup or Git configuration change was performed. Read-only checks used `GIT_OPTIONAL_LOCKS=0`.

## Delivered behavior

- `workspace` creates an offline, self-contained source/RTL-editor HTML page in a new UUID run directory. The real first workspace is blank; no OCR text is read to prefill it. Existing human GT can seed a working copy.
- `workspace --review-only` requires an existing submission, then displays its version/hash/order and read-only text beside the source. Exact raw reference/sidecar bytes are copied for inspection. The page has no submission/approval endpoint or approval button.
- Workspaces show source identity, zoom controls, annotation guidance, manual-completeness limits and explicit UTF-8/no-BOM LF/CRLF downloads. There is no autosave or server. GUI opening/download remains a human action.
- The existing gt-v1 schema, version history, completeness attestation, independent-review gate and approval transitions are reused unchanged. Empty/malformed text, mismatched source and unapproved GT retain existing validation behavior. Semantic completeness cannot be certified from character counts.
- New pilot comparisons add `accuracy_by_page.csv`, `error_analysis.json` and `error_analysis.md`. They copy benchmark rates/operation counts without recomputing CER/WER, separate strict/normalized policies, verify evaluated text-snapshot hashes and record source-report/association hashes. They identify engine/variant/page, coverage and interpretation limits. No ranking is introduced.
- Existing seven historical adapters and raw prediction bytes remain unchanged. All work stays inside evaluation; no OCR engine, router, production frontend or new dependency is added.

## Verified checks

| Check | Result |
| --- | --- |
| Full test discovery | **84 passed**, zero failures: 76 existing tests plus 8 focused Task 004 regressions |
| New workspace tests | Blank initialization, no GT/approval side effect, source identity, exclusive directories, read-only reference, HTML escaping and byte pinning pass |
| New analysis tests | Pending scores/counts absent, approved-only gate, copied policy-separated metrics, snapshot-hash rejection and overwrite rejection pass |
| Original preservation manifest | **108 unchanged** |
| Task 003 pre-edit snapshot | **141 unchanged** |
| Task 004 scoped pre-edit snapshot | **189 unchanged**; deliberately excludes the CLI integration file; documentation changes reviewed through Git |
| Inventory recomputation | PASS: actual source and related original copies still match |
| Installed dependencies | `pip check` passes; no packages installed |
| Git access/baseline/diff | PASS; `diff --check` passes; no changes to baseline OCR experiments, metrics, runner or GT approval implementation |
| Real pending comparison | Seven NOT_EVALUATED entries, fourteen policy rows with absent CER/WER; error-analysis status NOT_EVALUATED |
| Syntax/links/artifact hashes | Python syntax and documentation JSON parse; local documentation links and generated workspace/report hashes verified |

The original PyMuPDF `fitz` deprecation warning remains. Git also reports the existing Windows LF-to-CRLF checkout policy for some edited files; no whitespace error or configuration change was introduced. Characterization/Task 002/Task 003 tests were preserved byte-for-byte. Approved test fixtures are synthetic temporary text, not real reference annotations.

HTML construction, source embedding, escaping, read-only controls and provenance are tested. A live browser interaction/download was **not** automated or observed, and no browser was launched by the agent. The user must open the offline page and perform transcription. Local attested identities are not authenticated accounts.

## Actual artifacts

Prepared blank editor:

`results/transcription/20261027T225721Z_e5c3fe6667ff4c3d8cbad6ea9baba8ca/workspace.html`

Its directory also has `source_page.png` and `workspace.json` with source/pixel/preview/HTML hashes and code/environment provenance. It contains no reference snapshot because no GT exists.

Seven-variant comparison and analysis:

`results/pilot/20261027T225721Z_a68702c8aeb14b13a183cd0b4ffa9e75/evaluation/20261027T225721Z_8d9e53f2d381470b83e9f072978337a1/`

All entries retain `NOT_EVALUATED / MISSING_GROUND_TRUTH`; analysis declares accuracy/error patterns unavailable. The source/predictions are preserved, no GT version was created and no experiment path was reused. New results remain Git-ignored.

## Created/modified files

Created:

- `src/smartarchive/evaluation/review_workspace.py`: offline editor and frozen-reference view.
- `src/smartarchive/evaluation/error_analysis.py`: approved-only summaries and per-engine/variant/page CSV.
- `tests/test_task004.py`: eight regressions for the new behavior.
- `docs/first_arabic_gt.md`: exact source identity, annotation convention and PowerShell handoff.
- `docs/task_004_preservation.json`: scoped pre-edit byte hashes; a verifier, not a backup.
- `docs/task_004_validation.md`: this report.

Modified: `src/smartarchive/evaluation/pilot_cli.py` (workspace command and analysis hook), `README.md`, `docs/pilot_workflow.md`, `docs/ocr_benchmark.md`, `docs/architecture.md`, `docs/technical_backlog.md`, `docs/validation_status.md`.

No historical OCR script/output, input file, previous test, metric implementation, schema, GT history logic or baseline commit was changed. Source previews are new derivatives, not replacements for original bytes.

## Reproduce verification

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe tools/verify_preservation.py
.\.venv\Scripts\python.exe tools/verify_snapshot.py
.\.venv\Scripts\python.exe tools/verify_snapshot.py --manifest docs/task_004_preservation.json
.\.venv\Scripts\python.exe tools/pilot_ocr.py inventory --check
.\.venv\Scripts\python.exe tools/pilot_ocr.py inspect
.\.venv\Scripts\python.exe -m pip check
$env:GIT_OPTIONAL_LOCKS = '0'
& 'C:/Program Files/Git/cmd/git.exe' status --short
& 'C:/Program Files/Git/cmd/git.exe' diff --check
```

## Human boundary and Task 005

Stop automated work before actual transcription/review. Follow [first Arabic GT instructions](first_arabic_gt.md): open the workspace, independently type the source, submit the exact UTF-8 draft, arrange independent human review, record approval for that version, then run `tools/pilot_ocr.py compare`. Until then retain NOT_EVALUATED, not invented scores.

Task 005 should complete that human-labelled pilot and analyze pinned errors with the source visible; expand to authorized representative institutional pages before any generalization or routing/enhancement claim. Unknown historical engine versions, incomplete original invocation provenance, single-page scope, unauthenticated identities, input/resource limits and backup/recovery remain limitations. All five supervisor components remain in scope; this task validates no research improvement.
