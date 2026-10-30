# Task 005 — first working full-stack archive

The first local vertical slice is implemented and verified: browser upload -> validated original storage -> SQLite record/audit -> searchable document list -> details/preview -> unchanged original download -> persisted dashboard counts after refresh. OCR results are deliberately unavailable. No research metric or improvement is claimed.

## Actual validation results

| Check | Verified result |
| --- | --- |
| Full Python suite | **103 passed**: 84 unchanged research/workflow tests + 19 new API tests; zero failures/errors |
| TypeScript | `next typegen && tsc --noEmit` passed |
| Production build | Next.js **16.4.3**, supported Webpack build passed; dashboard/documents/upload static shells and dynamic detail route generated |
| Real browser integration | **4 passed** in Microsoft Edge via Playwright **1.64.1** |
| Lockfile validation | `npm ci --dry-run --ignore-scripts --offline` passed after clean dependency/lockfile repair |
| Dependency tree | npm direct dependencies resolved; Python `pip check` passed |
| Preservation | Original 108-file check, previous snapshots and Task 005's **220 pre-task source/test/tool/data/result files** unchanged |
| Git | Repository accessible with installed Git; no commit, staging update, reset or cleanup performed |

The browser tests exercised the actual frontend/API, not mocked success endpoints. They uploaded the existing Arabic `data/input/sample.png` under a test filename into unique test storage. Assertions covered real API 201, source SHA-256, image preview decoding, actual browser download with byte/hash equality, audit event, Arabic filename search, PDF/image filtering, dashboard count after page refresh and mobile menu/viewport behavior. Separate tests deliberately aborted the statistics request (visible error, no fabricated count) and rejected an unsupported client file before upload.

API tests cover PNG/JPEG/WebP/multipage TIFF, original PDF/page count/byte ranges, byte preservation, app restart persistence, actual statistics, pagination/filtering, literal search and injection strings, duplicates without overwrite, unsafe client paths, empty/corrupt/unsupported/encrypted inputs, MIME/extension mismatch, file/request/unknown-length body limits, pixel/page limits, CORS/origin rejection, append-only audit and original-metadata triggers, transactional audit failure and changed-original refusal.

Actual image and PDF preview/download are browser-verified. The additional PDF test generates a synthetic PDF, verifies that the page-preview image decodes in Edge and downloads the unchanged PDF. API tests cover PDF page rendering, page bounds, byte ranges and original preservation. Preview is a bounded PNG derivative, not a browser PDF plugin or extracted text. No actual OCR processing or classification was tested because none is connected.

## Browser findings and repairs

Initial runs exposed two test assumptions (Arabic numerals versus the browser's Latin numerals, and refresh racing an unfinished SPA navigation), which were corrected without weakening count/persistence checks. Browser checks also found a real RTL mobile overflow: an absolutely positioned screen-reader table header escaped its static scroll container. The container now establishes positioning, and the closed mobile navigation is removed from layout/tab order. Final mobile screenshots are 390 CSS pixels wide, with document-table overflow contained inside its scroller. A final alert locator was scoped away from Next's separate route announcer. The complete final suite passes.

Visual PDF inspection caught an empty plugin-based iframe even though its visibility assertion passed. The application now renders PDF pages through existing PyMuPDF as bounded PNG previews with page controls, preserving the restrictive original-content headers and unchanged download. The browser assertion now requires a decoded preview image, and the final PDF screenshot visibly shows the test-page text. This repair adds no OCR engine or dependency.

Initial npm downloads timed out and left an incomplete generated dependency tree/lockfile. Generated files were preserved under ignored `.tools/` backups, then clean installation repaired the lock. The missing native SWC package was retrieved from the official registry and verified against its published SHA-512 before restoring only generated `node_modules`. The portable Node **24.22.1** archive was verified against official SHA-256 checksums. Scripts use Webpack for consistent Windows execution; no binary or dependency directory is committed. These repairs do not alter application logic or research data.

The installed Starlette TestClient warns that its `httpx` adapter is deprecated; it remains functional and tested with httpx 0.28.1. The old `fitz` research import warning is unchanged. Edge test-server shutdown occasionally logs Windows connection-reset callbacks, and Node logs NO_COLOR/FORCE_COLOR warnings; neither is a failed test or persisted-data error.

## Local evidence and running application

Evidence directory:

`results/task005_verification_4c0779e9a5f94c31a2cb8b67a23602b4/`

It contains desktop/mobile dashboard, image-detail and rendered PDF screenshots, downloaded image/PDF originals and `verification.json` with test counts and file hashes. The downloaded image bytes match source SHA-256 `f000d4598d57c79c5f3db5f308c26960c0c73170c7d30862efad6d66106b40cc`; the browser also verifies the generated PDF's byte hash. Earlier verification directories remain untouched. Evidence contains test-only data; it is not seeded into the user's archive.

The local backend was started at **http://127.0.0.1:8000** and the production-built frontend at **http://127.0.0.1:3000**. HTTP health/route checks passed. Default application storage remains empty (total_documents=0 and total_bytes=0); browser-test uploads are isolated under `.tools/e2e-storage/<uuid>/`. No fake document/statistic is inserted to make the default dashboard look populated. Long-running server sessions may end when the environment closes; startup instructions below reproduce them.

## Installed versions

Python 3.11.9; FastAPI 0.162.0; Uvicorn 0.54.0; python-multipart 0.0.32; httpx 0.28.1; Pillow 11.3.0; PyMuPDF 1.28.2. JavaScript: Node 24.22.1, npm 11.19.1, Next 16.4.3, React/React DOM 19.3.1, TypeScript 5.9.3, Tailwind/@tailwindcss/postcss 4.3.3, Playwright 1.64.1. The committed JavaScript lockfile pins transitive packages; Python requirements pin direct application/test dependencies, not the entire transitive environment.

## Startup — Windows PowerShell

From repository root, first install if needed:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe tools/frontend.py ci
```

Terminal 1:

```powershell
.\.venv\Scripts\python.exe -m uvicorn smartarchive.api.app:app --app-dir src --host 127.0.0.1 --port 8000
```

Terminal 2:

```powershell
$env:NEXT_PUBLIC_API_URL = 'http://127.0.0.1:8000'
.\.venv\Scripts\python.exe tools/frontend.py run dev
```

Open http://127.0.0.1:3000. Do not start a second frontend on port 3000 while the already-started production preview occupies it; stop that session with Ctrl+C first. Full prerequisites, environment variables, API endpoints, build commands and browser-test instructions are in [web_application.md](web_application.md).

## Created/modified files

Created backend: `src/smartarchive/config.py`; `domain/__init__.py`, `domain/documents.py`; `persistence/__init__.py`, `persistence/database.py`, `persistence/storage.py`; `services/__init__.py`, `services/documents.py`; `api/__init__.py`, `api/app.py`, `api/schemas.py`, `api/middleware.py`.

Created frontend: `frontend/package.json`, `package-lock.json`, `tsconfig.json`, `next.config.ts`, `postcss.config.mjs`, `.env.example`, `playwright.config.ts`; `lib/api.ts`, `lib/use-api.ts`, `lib/format.ts`; `components/icons.tsx`, `components/ui.tsx`, `components/shell.tsx`; `app/layout.tsx`, `app/globals.css`, dashboard/upload/document-list/detail routes and loading/error/not-found boundaries; `tests/archive.spec.ts`. Next generates ignored `next-env.d.ts` and build output.

Other additions: `requirements-api.txt`, `requirements-dev.txt`, root `.env.example`, `tools/frontend.py`, `tests/test_api.py`, `docs/web_application.md`, `docs/task_005_preservation.json`, `docs/task_005_validation.md` and ignored runtime/evidence files.

Modified: `README.md`, `.gitignore`, `docs/architecture.md`, `docs/technical_backlog.md`, `docs/validation_status.md`. Pre-existing staged Task 004 edits were retained; the index was not changed. All prior Python sources/tools/tests and historical documents/results remain unchanged, including benchmark metrics, GT schema/approval logic and seven historical adapters. No automatic commit.

## Known limitations and Task 006

- Loopback, unauthenticated local prototype: no public deployment, real user identity/permissions, antivirus scan, isolated parser process, quotas/rate limits or TLS configuration. CORS and origin checks do not replace authentication.
- Original immutability is enforced by application write-once paths, metadata triggers and delivery hash checks, not OS write-once storage. Audit triggers are not cryptographic tamper-proofing against a privileged host user.
- Filesystem publication and SQLite commit are not one atomic distributed transaction. Failure/crash may leave originals/staging files for reconciliation. No automatic cleanup, recovery, backup/restore or migration framework yet. Store on local NTFS or another hard-link-capable filesystem.
- No OCR engine runs after upload, no persistent job queue, and no text/confidence/classification is invented. Search is filename-only. Preview is a paged PNG derivative for PDF/image sources; the unchanged full original is downloadable. Native PDF plugins are not relied on.
- No real GT is approved and no OCR accuracy gain is claimed. Existing research workflows remain available and unchanged.

Task 006 should implement bounded persisted OCR jobs with explicit source/run/artifact versions, an existing full-page baseline adapter, honest failure/timeout/retry states and human-review-required results. Complete independent GT in parallel for evaluation. Before shared institutional use, add authentication/access control and backup/reconciliation. Keep all five supervisor contributions as later evidence-backed integrations rather than labelling this filename archive a hybrid-search/classification system.
