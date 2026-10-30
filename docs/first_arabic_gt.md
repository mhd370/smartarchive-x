# Task 004 — first Arabic transcription and review

Engineering preparation is complete; the real page still needs a human transcription and independent approval. No OCR output has been used as a reference. The supervisor's five research components remain the target; this task improves evaluation readiness, not OCR routing/models or the full platform.

## Exact source and current boundary

- Source: `data/input/sample.png`, page 1, 665×708 pixels.
- Source SHA-256: `f000d4598d57c79c5f3db5f308c26960c0c73170c7d30862efad6d66106b40cc`.
- Document ID: `doc-f000d4598d57c79c5f3db5f308c26960c0c73170c7d30862efad6d66106b40cc`.
- Current GT: PENDING, version 0. The original inventory's authorization field is also pending confirmation.
- The page is Arabic literary/educational text with two columns and a spanning heading. It is a layout pilot, not representative institutional evidence.

## 1. Inspect and open the manual workspace

From the repository root in PowerShell, using the existing Python 3.11 environment:

```powershell
.\.venv\Scripts\python.exe tools/pilot_ocr.py inventory --check
.\.venv\Scripts\python.exe tools/pilot_ocr.py inspect
$documentId = (Get-Content docs/pilot/dataset.json -Raw | ConvertFrom-Json).documents[0].document_id
.\.venv\Scripts\python.exe tools/pilot_ocr.py workspace --document $documentId --page 1
```

The command prints a new `workspace.html` path. Open that exact path with `Invoke-Item`. A prepared blank workspace from this task is available at:

```powershell
Invoke-Item 'results/transcription/20261027T225721Z_e5c3fe6667ff4c3d8cbad6ea9baba8ca/workspace.html'
```

The offline page displays a zoomable source beside a blank RTL editor. No server, package installation, network request or OCR invocation is needed. It cannot submit, review or approve GT. It does not save edits automatically; download drafts regularly before closing. The page uses the existing Pillow-decoded source preview and records source/pixel/preview hashes in `workspace.json`. Current human GT, when present, can populate a working copy; it is never populated from predictions.

## 2. Human transcription — stop automation here

First confirm that you may use this source. Type directly from the image, independently of OCR. Confirm the page's actual reading order: spanning heading first, then the right column top-to-bottom, then the left column top-to-bottom. Preserve logical Arabic characters; never reverse characters to imitate RTL. Keep visible diacritics, punctuation, numerals and mixed Arabic/English text. Use one line break per transcribed source line and a consistent declared boundary between columns. Do not silently repair source spelling or guess illegible words.

Verify every heading, body line, column, stanza number and punctuation mark. If any text/order is unresolved, retain an incomplete draft. Character/line counters only help navigation; they cannot establish completeness. Completeness remains a human attestation enforced by the existing `--complete` gate, not a machine claim.

Use **Download UTF-8 text (no BOM)**. The selector explicitly chooses LF or CRLF export; the browser textarea uses LF internally. These are export choices for the working copy, not changes to stored GT. Choose a consistent annotation convention, not formatting chosen to improve a score. Strict metrics count actual line endings and trailing whitespace; normalized metrics follow the unchanged normalization policy.

Save the downloaded file somewhere you can identify. Copy that exact new download into a uniquely named local working file:

```powershell
New-Item -ItemType Directory -Path data/ground_truth/manual -Force
$download = Read-Host 'Full path of the UTF-8 transcript you just downloaded'
$manualText = Join-Path (Get-Location) ('data/ground_truth/manual/page001_' + [guid]::NewGuid().ToString('N') + '.txt')
Copy-Item -LiteralPath $download -Destination $manualText
Get-FileHash -LiteralPath $manualText -Algorithm SHA256
```

If the browser adds a numeric suffix to a download, use the actual newest file path. You may instead create the working file in an editor and save UTF-8 without BOM. No application can prove independent manual work from the file alone; do not attest OCR-generated text as independent GT.

## 3. Submit the completed manual page

Replace `YOUR_ACTUAL_ID` with your real local identifier. Run only after manual verification; omit `--complete` for unresolved/incomplete text.

```powershell
.\.venv\Scripts\python.exe tools/pilot_ocr.py submit --document $documentId --page 1 --expected-version 0 --text $manualText --transcriber 'YOUR_ACTUAL_ID' --reading-order 'spanning heading, top to bottom' 'right column, top to bottom' 'left column, top to bottom' --reason 'First independent manual transcription' --manual --complete
```

This reuses gt-v1, immutable Task 003 revisions and the draft state. It validates UTF-8/no BOM, nonempty text, source/page association, ordered labels and the expected version. It snapshots bytes and hashes them. It does not approve anything. A correction uses the current expected version and a correction reason, creates a new draft and requires new review/approval. See [pilot workflow](pilot_workflow.md).

## 4. Independent human review and approval

Arrange a different authorized person, such as your supervisor, to review the entire frozen version against the original. Do not invent a second identity. Generate a read-only source/reference view:

```powershell
.\.venv\Scripts\python.exe tools/pilot_ocr.py workspace --document $documentId --page 1 --review-only
```

Open the printed HTML path. It shows the submitted version, status, source hash, reference hash, declared order and read-only reference. Its directory includes exact `reference_snapshot.txt` bytes and the sidecar snapshot. Browser text controls display normalized line endings; the raw snapshot/hash is authoritative for byte-level inspection. The workspace cannot record approval. If corrections are needed, submit a new revision and regenerate this view before reviewing it.

Only after independent verification, record the decisions using the same real reviewer identity and the version actually inspected:

```powershell
.\.venv\Scripts\python.exe tools/pilot_ocr.py review --document $documentId --page 1 --expected-version 1 --reviewer 'INDEPENDENT_REVIEWER_ACTUAL_ID' --attest
.\.venv\Scripts\python.exe tools/pilot_ocr.py approve --document $documentId --page 1 --expected-version 1 --reviewer 'INDEPENDENT_REVIEWER_ACTUAL_ID' --attest
.\.venv\Scripts\python.exe tools/pilot_ocr.py inspect
```

Use version 2 or later if you corrected the initial submission. Existing workflow checks enforce distinct transcriber/reviewer, complete labels, draft -> reviewed -> approved order, version/hash consistency and review timestamps. Identities remain local attestations rather than authenticated accounts.

## 5. Compare all seven saved predictions

```powershell
.\.venv\Scripts\python.exe tools/pilot_ocr.py compare
```

The unchanged seven historical adapters and benchmark policies are reused. Each command creates a new bundle and evaluation directory. It imports saved text and never reruns OCR. Missing, pending or merely reviewed GT remains NOT_EVALUATED; only an approved reference can produce numerical accuracy.

Besides existing `report.json`, `pages.csv` and `summaries.csv`, each new pilot comparison now writes:

- `accuracy_by_page.csv`: document/page, Tesseract variant, engine version where known, policy, status, CER/WER and S/D/I counts. Missing accuracy is empty, not zero.
- `error_analysis.json`: exact copied benchmark measurements, coverage, report/association hashes and snapshot-verified line-ending diagnostics for evaluated pages only.
- `error_analysis.md`: readable policy-separated measurements, operation counts and interpretation limits.

All seven variants use Tesseract, with unknown historical engine version. These are per-variant/page comparisons, not seven distinct engines. Operation counts transform reference into prediction. They do not prove why an error occurred, and strict/normalized gaps combine multiple normalization effects. Review visual errors against the source before diagnosing layout omissions. No automatic ranking/winner selection is added.

## Verified example and next task

The actual pending-GT run is under `results/pilot/20261027T225721Z_a68702c8aeb14b13a183cd0b4ffa9e75/evaluation/20261027T225721Z_8d9e53f2d381470b83e9f072978337a1/`. All seven entries and error analysis remain NOT_EVALUATED. The blank workspace does not constitute GT, and no real CER/WER has been calculated.

[Task 004 validation](task_004_validation.md) records tests, preservation, Git access and changed files. Task 005 should first complete the human steps above, then inspect the frozen baseline metrics and source-linked errors; expand to representative authorized institutional pages before drawing general conclusions or adding routing/enhancement behavior.
