# Local full-stack application (Task 005, extended in Tasks 006 and 007)

Task 007 (Sprint 2) added Arabic text search and human page review; see the API rows marked *(007)* and [ADR 0004](adr/0004-arabic-search-and-page-review.md). Task 008 (Sprint 3) added classification, rows marked *(008)*, [ADR 0005](adr/0005-explainable-classification.md). Task 009 (Sprint 4) added operations and evaluation, rows marked *(009)*, [ADR 0006](adr/0006-backup-integrity-evaluation.md). Task 010 (Sprint 5) added folders, metadata and relations, rows marked *(010)*, [ADR 0007](adr/0007-folders-metadata-duplicates.md).

Task 006 added sign-in, roles and the OCR pipeline; every endpoint except `/api/health` and `/api/auth/*` now requires a session. Roles: admin (everything), archivist (upload, run OCR), reviewer (read, review in later tasks), viewer (read/download).

This application implements ingestion, persistent document records, original preview/download, filename search, dashboard counts and append-only document audit. It uses FastAPI/Python 3.11, SQLite and local files, with Next.js/TypeScript/Tailwind for an Arabic-first RTL interface. Existing experiments, GT approval tools, historical adapters and metric policies remain independent and unchanged.

OCR execution, confidence scoring, classification, semantic retrieval and reclassification are not connected. A successful upload has status `stored`, reason `OCR_NOT_CONFIGURED`; it has no extracted text or confidence. No background OCR queue is simulated.

## Install on Windows PowerShell

Run from `C:\Users\lenovo\Desktop\SmartArchive-X_POC`. Use the existing `.venv`. On a fresh checkout create it with `py -3.11 -m venv .venv`. Install Node.js LTS if `node --version` is unavailable; the current Next.js minimum is 20.9 per its [official installation guide](https://nextjs.org/docs/app/getting-started/installation). The local setup uses a checksum-verified official portable Node 24 distribution under ignored `.tools/`.

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe tools/frontend.py ci
```

`requirements-api.txt` installs backend runtime dependencies; `requirements-dev.txt` also includes HTTP API testing and the image packages already needed by preserved research tests. The original requirements files remain unchanged. `frontend/package-lock.json` pins the JavaScript dependency tree. No service subscription, external database, font CDN or paid API is used.

`tools/frontend.py` locates Node on PATH or the local portable runtime, invokes npm without shell quoting and disables Next telemetry for its child process. It uses existing OS proxy settings if present and defaults to IPv4-first networking on Windows to avoid this machine's registry timeout. It does not change system settings, persist credentials or disable TLS validation. Standard `npm.cmd ci` / `npm.cmd run dev` from `frontend/` also work when Node/npm networking is configured normally.

## Start the backend — terminal 1

```powershell
Set-Location 'C:\Users\lenovo\Desktop\SmartArchive-X_POC'
$env:SMARTARCHIVE_STORAGE_DIR = Join-Path (Get-Location) 'storage'
$env:SMARTARCHIVE_MAX_UPLOAD_MB = '32'
$env:SMARTARCHIVE_CORS_ORIGINS = 'http://localhost:3000,http://127.0.0.1:3000'
.\.venv\Scripts\python.exe -m uvicorn smartarchive.api.app:app --app-dir src --host 127.0.0.1 --port 8000
```

API docs: `http://127.0.0.1:8000/docs`. Health: `http://127.0.0.1:8000/api/health`. The database and original-file directories are initialized on startup. To enable source reload, add `--reload --reload-dir src`. Stop with Ctrl+C.

## Start the frontend — terminal 2

```powershell
Set-Location 'C:\Users\lenovo\Desktop\SmartArchive-X_POC'
.\.venv\Scripts\python.exe tools/frontend.py run dev
```

Open **http://127.0.0.1:3000**. Dashboard, Documents, Upload and Document Details use the live API. The dashboard does not substitute zeros when requests fail. Search is explicitly filename search, not OCR or hybrid search. Upload progress measures transfer; 100% transfer is followed by server validation and is not displayed as saved until the API returns 201.

To verify the user flow: upload an authorized PDF/image, open its details, check the preview and SHA-256, download the original, and refresh the dashboard. Counts are read from SQLite after refresh. Stop with Ctrl+C.

Production build/local preview:

```powershell
.\.venv\Scripts\python.exe tools/frontend.py run typecheck
.\.venv\Scripts\python.exe tools/frontend.py run build
.\.venv\Scripts\python.exe tools/frontend.py run start
```

The browser only talks to the frontend origin; Next forwards `/api/*` to `SMARTARCHIVE_API_ORIGIN` (read at start-up). `NEXT_PUBLIC_API_URL` is compiled into the client bundle and is only needed for a direct-API setup. Use TLS before any network deployment.

The scripts use the supported Webpack builder on Windows. Initial optional SWC compiler downloads were interrupted on this machine; the official native package was restored only after verifying its npm SHA-512 integrity. No compiler binary or `node_modules` is committed. If a fresh install reports a missing compiler, retry the dependency install and follow the official [SWC loading guidance](https://nextjs.org/docs/messages/failed-loading-swc); do not disable TLS or change OCR code to work around a web-toolchain failure.

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `SMARTARCHIVE_STORAGE_DIR` | repository `storage/` | SQLite plus original files; keep separate from research data/results |
| `SMARTARCHIVE_MAX_UPLOAD_MB` | 32 | File limit, configurable 1–128 MiB; request envelope gets 1 MiB overhead allowance |
| `SMARTARCHIVE_CORS_ORIGINS` | localhost/127.0.0.1:3000 | Explicit browser origins; wildcard rejected |
| `SMARTARCHIVE_API_ORIGIN` | http://127.0.0.1:8000 | FastAPI origin that Next forwards `/api/*` to; the browser uses one address (no CORS, first-party cookies) |
| `NEXT_PUBLIC_API_URL` | empty (same origin) | Optional direct API origin for the browser, without `/api` suffix |
| `SMARTARCHIVE_NEXT_DIR` | .next | Optional separate Next build directory, used by browser tests |
| `SMARTARCHIVE_TESSERACT_CMD` | auto (`PATH`, then `C:\Program Files\Tesseract-OCR\tesseract.exe`) | Tesseract executable (Task 006) |
| `SMARTARCHIVE_OCR_LANGUAGES` | `ara+eng` | Requested languages; only installed ones are used and the actual set is recorded per run |
| `SMARTARCHIVE_OCR_AUTO` | true | Queue OCR automatically after each upload |
| `SMARTARCHIVE_OCR_WORKER` | true | Run the background OCR worker inside the API process |
| `SMARTARCHIVE_SECURE_COOKIES` | false | Set true only when served over HTTPS |

Root `.env.example` documents backend variables; they are read from the environment, not automatically loaded from `.env`. `frontend/.env.example` can be copied to `.env.local` for Next, or set variables in the PowerShell session as above. Never store credentials in public frontend variables.

## API contract

| Method/path | Behavior |
| --- | --- |
| GET `/api/auth/status` | Public: `setup_required` (no users yet) and whether the caller is signed in |
| POST `/api/auth/setup` | Public, only while no user exists: create the first admin and sign in |
| POST `/api/auth/login` / `/api/auth/logout` | Start/end a server session (HttpOnly `sa_session` cookie); 5 failures lock the account for 15 min |
| GET `/api/auth/me` | Current user, role and permissions |
| GET/POST `/api/users`, PATCH `/api/users/{uuid}` | Admin only: list, create, change role/active/name/password; changes revoke the user's sessions; the last active admin is protected |
| GET `/api/health` | Public: database availability, upload limits/types, actual OCR engine and installed languages |
| GET `/api/statistics` | Persisted counts by lifecycle state and total original bytes |
| POST `/api/documents` | Multipart `file`; validate, preserve, insert record and upload audit transaction; 201 |
| GET `/api/documents` | `q` literal filename search; `status`, `kind=pdf/image`, `limit=1..100`, `offset` |
| GET `/api/documents/{uuid}` | Metadata; append viewed event |
| GET `/api/documents/{uuid}/status` | Persisted state/reason, latest run, extracted text and mean confidence of the latest completed run; classification still null |
| GET `/api/documents/{uuid}/ocr` | Engine info, all runs (versions) and per-page quality analysis of the shown run |
| POST `/api/documents/{uuid}/ocr` | Archivist/admin: queue a new run (409 while one is queued/running, 503 without an engine) |
| GET `/api/documents/{uuid}/ocr/pages/{n}` | Lines with normalised boxes (0..1 of the page), word boxes and engine confidences; `run_id` selects an older version |
| GET `/api/search` *(007)* | `q` (1–200 chars), `limit` 1–50, `offset`: documents whose page text contains every term, or whose file name does; pages with highlighted excerpts and whether the text is OCR or reviewed |
| GET `/api/review/queue` *(007)* | Reviewer/archivist/admin: pages of the latest completed run flagged for review and not yet corrected, lowest confidence first |
| GET `/api/documents/{uuid}/pages/{n}/text` *(007)* | Approved page text (latest revision, else OCR), its source, current version and revision history |
| POST `/api/documents/{uuid}/pages/{n}/text` *(007)* | Reviewer/archivist/admin: `{text, expected_version, note}` saves a new revision; 409 if someone saved first or the document is being processed |
| GET `/api/documents/{uuid}/pages/{n}/revisions/{v}` *(007)* | Full text of an earlier revision |
| GET `/api/categories` *(008)* | Categories with keywords and confirmed/suggested counts |
| POST `/api/categories`, PATCH `/api/categories/{id}` *(008)* | Admin: create (`id`, `name`, `description`, `keywords`), edit or deactivate |
| GET `/api/documents/{uuid}/classification` *(008)* | State (`confirmed`/`suggested`/`uncertain`/`none`), latest suggestion with evidence and scores, latest decision, history, `sequence` |
| POST `/api/documents/{uuid}/classification` *(008)* | Reviewer/archivist/admin: `{category_id, expected_sequence, reason}`; reason required to change a confirmed category; 409 on stale sequence |
| POST `/api/documents/{uuid}/classification/suggest` *(008)* | Reviewer/archivist/admin: recompute the suggestion now |
| GET `/api/classification/queue` *(008)* | Documents with an unconfirmed suggestion or no category; `category` filter also on `/api/documents` (`none` = unclassified) and `/api/search` |
| GET `/api/classifier` *(013)* | Reader: active suggestion method, model card (classes, examples, training time, source) and confirmed documents per category |
| POST `/api/admin/classifier/train` *(013)* | Admin: train `tfidf-svm-v1` on confirmed categories (422 `not_enough_examples` below 3 per category for 2 categories), recompute open suggestions; security event `classifier.trained` ([ADR 0010](adr/0010-learned-classifier.md)) |
| GET/POST `/api/admin/backups` *(009)* | Admin: list backups / create a verified backup zip |
| POST `/api/admin/backups/{name}/verify`, GET `.../download` *(009)* | Admin: verify every member and the database / download the zip |
| POST `/api/admin/integrity` *(009)* | Admin: reconcile originals with the database; report only |
| GET `/api/evaluation` *(009)* | Reviewer/archivist/admin: OCR post-editing CER/WER and classification accuracy from reviewed data |
| GET/POST `/api/folders` *(010)* | Folder tree with counts / create (`name`, `parent_id`; archivist, admin) |
| PATCH `/api/documents/{uuid}/folder` *(010)* | Move a document (`folder_id` or null); POST `/api/documents` accepts form field `folder_id`; `/api/documents?folder=` includes sub-folders |
| GET `/api/documents/{uuid}/metadata`, PUT `.../metadata/{field}` *(010)* | Extracted/corrected number, date, sender, recipient, subject, amount; reviewers edit |
| GET `/api/documents/{uuid}/relations`, POST `/api/relations/{id}/review` *(010)* | Duplicate/version links; reviewers confirm or reject |
| GET `/api/category-groups` *(010)* | Level-1 groups; categories carry `group_id` |
| GET `/api/documents/{uuid}/audit` | Ordered append-only event history |
| GET `/api/documents/{uuid}/download` | Integrity-checked unchanged original as attachment |
| GET `/api/documents/{uuid}/content` | Integrity-checked original inline; supports PDF byte ranges |
| GET `/api/documents/{uuid}/preview?page=1` | PDF/image page as a PNG derivative, bounded to 1800×2400; original unchanged; page bounds validated |

Records include UUID, sanitized display filename, original byte size, detected/validated MIME, SHA-256, actual page/frame count, UTC timestamps and status. Internal storage keys are not exposed in JSON. Invalid UUID/query/file inputs return explicit 4xx errors; corrupt/missing stored originals return 409 instead of being served.

## Upload/persistence guarantees and boundaries

- Allowlist PDF, PNG, JPEG, WebP and TIFF. SVG, HTML, executables, empty/corrupt files, declared MIME mismatches and mismatched extension/content are rejected. Client validation is advisory; the API repeats validation.
- Bound both declared and unknown-length request bodies before multipart parsing; stream the selected file to a request-owned staging path while hashing. Image decoding is limited by pixels/frame count; PDFs must be parseable, unencrypted and within the page limit (200). There is no OCR during upload.
- Client filenames are display metadata only. Original files use generated UUID directories and exclusive creation. Publication uses a same-filesystem hard link, never overwriting an existing destination. Use a local filesystem supporting hard links (e.g. NTFS).
- SQLite records and upload audit insertion share one transaction. Audit UPDATE/DELETE and original metadata UPDATE are rejected by triggers. Actor `local` means a local unauthenticated session, not a verified human identity.
- No API deletes/replaces originals. Preview/download rechecks source size/hash; page previews are derivatives. PDF pages are rendered using existing PyMuPDF rather than relying on a browser plugin. Original content is served with nosniff/sandbox headers, which can block native PDF plugins; the UI uses the PNG page route and an unchanged attachment download. This is application-level immutability/integrity checking, not OS write-once media or tamper-proof auditing.
- If filesystem publication succeeds but metadata/audit transaction fails, the original is retained and the request returns 503. A process crash can leave an orphan or staging file. Do not delete these automatically; reconcile by UUID/logs before retrying. Distributed transaction/crash recovery is not implemented.
- Both servers bind loopback by default. CORS is limited and unexpected browser mutation origins are rejected. Authentication, institutional authorization, antivirus scanning, sandboxed document parsing, quotas/rate limiting, backup/restore and TLS deployment are still required before serving an untrusted network. Do not expose this unauthenticated prototype publicly.

## Tests

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe tools/verify_preservation.py
.\.venv\Scripts\python.exe tools/verify_snapshot.py --manifest docs/task_005_preservation.json
.\.venv\Scripts\python.exe tools/frontend.py run typecheck
.\.venv\Scripts\python.exe tools/frontend.py run build
.\.venv\Scripts\python.exe tools/frontend.py run test:e2e
```

Browser tests use installed Microsoft Edge by default, isolated ports 3001/8001, a separate Next output directory and unique `.tools/e2e-storage/` directories. They upload the existing Arabic image as real test input and generate a clearly synthetic PDF to verify rendering/download; test documents do not seed the user's default `storage/`. Screenshots/downloads/traces are local ignored artifacts in `frontend/test-results/`. If Edge is absent, set `SMARTARCHIVE_BROWSER_CHANNEL=chrome` for an installed Chrome. Do not start unrelated servers on test ports.

The implementation follows FastAPI's [documented multipart upload API](https://fastapi.tiangolo.com/tutorial/request-files/). Actual execution results and any runtime limitations are recorded in [Task 005 validation](task_005_validation.md). Existing OCR research/GT workflows remain in their own guides.
