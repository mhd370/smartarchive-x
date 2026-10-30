# Prioritized technical backlog

## Task 005 priority change and current delivery

The user explicitly prioritized a usable application over another research-only task. GT remains pending but does not block document ingestion. Current delivered work:

- B09 (partial): FastAPI modular API, SQLite persistence, immutable-by-application original storage, source hashes/metadata, processing status, append-only document events, download and preview. Authentication, reviewer authorization, persistent OCR workers and restart recovery are still open.
- Connected Next.js/TypeScript/Tailwind RTL application: real dashboard counts, paginated filename search/status/type filters, validated upload/progress, details, original preview/download and audit history. Explicit empty/loading/error states; no seeded statistics/documents.
- Meaningful API tests and real Edge browser tests using separate test storage. All existing research code/tests/results preserved.
- OCR-related status is `stored`, not queued/complete. All five research contributions remain planned integration/evaluation milestones; Task 005 introduces no new engine, enhancement or invented extraction/confidence.

**Next development task (Task 006):** add a bounded, persisted processing-job lifecycle linked to document/source/run versions and an existing full-page baseline adapter, with failure/timeout/retry handling and review-required results. Complete independent GT in parallel before research comparisons. Add authentication/access control and backup/reconciliation before any shared institutional deployment. Hybrid search, classification and controlled reclassification remain subsequent scope, not implicit features of filename search.

The earlier B01–B14 plan and historical task notes follow as progress context, not a requirement to delay this delivered vertical slice.

P0 blocks a trustworthy benchmark. P1 is required for the scoped demonstrator. P2 is conditional refinement. The table is the initial plan; Task 002 status below distinguishes delivered portions from remaining work. Eight-week windows are indicative for one developer, not commitments; transcription and authorization can dominate the schedule.

| ID | Priority / window | Task and acceptance evidence | Dependencies |
| --- | --- | --- | --- |
| B01 | P0 / week 1 | Agree authorized dataset, GT mapping/reading order, Arabic normalization/BOM/blank-reference policy and document-level dev/test split. Review pilot transcripts independently; validator rejects duplicate IDs, split leakage and mapping errors. | Supervisor/data access |
| B02 | P0 / week 1 | Exclusive run directories, source/derivative hashes, configuration/environment manifest, started/complete/partial/failed states; reject input/output aliasing and overwrite attempts. | None |
| B03 | P0 / week 1 | New shared page/OCR/metric adapters: stable collision-safe IDs, all TIFF pages or explicit rejection, checked I/O, canonical unrounded CER/WER/edit counts, null metrics for unavailable GT. Preserve legacy code. | B01, B02 |
| B04 | P0 / week 1 | Reconcile baseline/experiment requirements, record tested environment and Tesseract languages/config, engine preflight/timeouts, explicit page/engine failure and exit status. Paddle optional. | B02 |
| B05 | P0 / weeks 1-2 | Test metric insert/delete/substitute, Arabic/diacritics/BOM/empty GT; IDs, TIFF/PDF pages, corrupt input, missing engine, unwritable output, partial runs, byte preservation and overwrite rejection. | B01-B04 |
| B06 | P1 / week 2 | OCR Benchmark CLI/report: identical rendered pages, per-page/grouped CER/WER, explicit micro/macro aggregation, wall time, failure/GT coverage. Run full-page Tesseract before variants. No fabricated unlabeled scores. | B05, reviewed pilot GT |
| B07 | P1 / week 3 | Quality routing: retain baseline, compare routes, calibrate on dev only, freeze before test; report CER/WER/latency/route coverage and fallback reasons. | B06, stratified GT |
| B08 | P1 / week 3 | Layout reconstruction: coordinate transforms, explicit RTL order, baseline fallback, ambiguity review; assess omissions/duplicates/order against annotations. | B06 |
| B09 | P1 / week 4 | Minimal FastAPI/ingestion/metadata persistence around tested contracts: immutable originals, source-linked metadata, bounded durable jobs/status, reviewer identity, authorization and review history. | B02-B05 |
| B10 | P1 / week 5 | Reliability-gated multimodal classification: agreed taxonomy, text/visual baselines, fusion, abstention and review. Report document-held-out macro-F1, confusion matrix, accepted coverage/error and ablations. | B07-B09, labelled data |
| B11 | P1 / week 6 | Confidence-aware hybrid search: lexical/vector/fusion baselines, OCR/review evidence, page/span/original provenance, judged queries and ranking ablations; index only complete active versions. | B08-B10, query judgments |
| B12 | P1 / week 7 | Controlled reclassification: proposal/authorized approval, expected-version checks, old/new labels/reason, append-only events, index retry/rollback. Test denial, stale proposals and interrupted indexing. | B09-B11 |
| B13 | P1 / week 8 | End-to-end evaluation/demo for all five research components, original-byte and backup/restore verification, documented failures/limitations and supervisor acceptance. | B07-B12 |
| B14 | P2 / if justified | Alternate OCR/layout/model/store and performance optimization only after profiling. Do not delay the first benchmark for Paddle. | B06, measured need |

## Task 002 status

| Item | Delivered | Remaining |
| --- | --- | --- |
| B01 | gt-v1 schema/template, manual independent review workflow, source/page/hash association, split consistency checks | Authorized documents, genuine transcripts, institutional agreement on ordering/labels and split allocation |
| B02 | Exclusive UTC/UUID runs, input/prediction/reference hashes/snapshots, started/final status, configuration/environment/source hashes | Backup/restore, crash recovery and producer-side artifact transactions |
| B03 | Saved-text adapter, stable manifest IDs, canonical strict/normalized metrics and operation counts | Deterministic render/OCR adapters, TIFF/PDF page handling and original-image I/O |
| B04 | Standard-library-only evaluator, supplied historical engine metadata, explicit unknowns and validation exit status | Legacy dependency reconciliation, native OCR preflight/timeouts and producer failure states |
| B05 | New automated metric/Arabic/GT validation/run isolation/provenance/aggregation tests; legacy tests retained | Renderer/native OCR corruption/timeout/resource-limit tests |
| B06 | Saved-output benchmark CLI, page/document/corpus JSON/CSV, micro/macro/coverage reporting | Real approved-GT baseline evaluation, comparable rendering/runtime collection and grouped research analysis |

**Next: Task 003 — authorized reviewed pilot GT and deterministic page/prediction adapters**, completing remaining B01/B03-B06 before routing/enhancement comparisons. No UI/model expansion is needed. If timeline/data readiness requires reduced depth, agree explicitly with the supervisor rather than removing a research component silently.

## Task 003 status

- B01: deterministic full-source-hash IDs/page inventory, original-image relationships and pending annotation status delivered. Real authorization, independent transcripts and representative institutional sources remain pending.
- B02/B05: append-only transcription/review versions, hash-chain verification, optimistic version guards, incomplete-label gating, independent-review attestations and correction tests delivered. Authentication, backup/restore and crash recovery remain open.
- B03: historical whole-page/region/line adapters delivered with explicit bindings, source pixels, order/geometry and component-aggregate checks. Raster-frame/PDF inventory is implemented/tested. Native OCR execution, preflight/timeouts and complete invocation capture remain open.
- B06: current pilot comparisons feed unchanged strict/normalized benchmark and preserve raw bytes/provenance. Seven real predictions produce NOT_EVALUATED, not accuracy measurements. Synthetic fixtures verify the approved workflow but are not institutional GT.

**Next: Task 004 — human-labelled pilot completion and controlled baseline analysis.** Obtain independent approval and representative institutional sources first, then compare historical predictions on frozen GT. Decide whether a native OCR execution adapter is required for pilot expansion before adding routing or enhancements. Five research components remain in scope; this task implements infrastructure, not their scientific validation.

## Task 004 status and Task 005

- B01: offline blank RTL editor beside the source, read-only frozen-reference workspace, explicit annotation/coverage checklist and exact human handoff delivered. Actual transcription, authorization confirmation and independent approval remain pending; no reference was invented.
- B05: focused regressions cover blank initialization, reference escaping/pinning, source identity, no approval side effect, analysis gating, policy separation and overwrite/tamper rejection.
- B06: new comparisons generate per-Tesseract-variant/page accuracy CSV and error-analysis JSON/Markdown from existing benchmark results, with source-report/association hashes and raw snapshot checks. The real seven-variant run remains NOT_EVALUATED. No rankings or improvement claims.
- Git baseline cbea099 is accessible via the installed Git executable; no commit was made.

**Task 005 recommendation:** complete the human transcription/review steps in first_arabic_gt.md, then analyze approved baseline errors before choosing further OCR work. Expand representative authorized institutional pages. Do not add routing, new OCR models or enhancement algorithms to bypass the missing-reference boundary.
