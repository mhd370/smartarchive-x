# Proposed engineering architecture

## Task 005 implemented vertical slice

The user's Task 005 priority change advances the local application now; pending GT does not block upload/storage/preview work. The historical target design below remains a roadmap. Implemented application boundaries are:

```text
src/smartarchive/
  config.py                      # local paths, upload limits, explicit CORS origins
  domain/documents.py            # lifecycle vocabulary and application errors
  persistence/database.py        # SQLite repositories, transactions, audit/immutability triggers
  persistence/storage.py         # bounded type validation, exclusive original publication, hashes
  services/documents.py          # ingestion and document lookup; no OCR execution
  api/app.py                     # FastAPI factory, lifespan and document endpoints
  api/schemas.py                 # typed public response contracts
  api/middleware.py              # pre-parser request size/origin checks
  evaluation/                    # Task 002–004 research modules, unchanged
frontend/
  app/                           # RTL dashboard, documents, upload and details routes
  components/                    # shared shell, feedback, status and table components
  lib/                           # typed API client, loading/cancellation hook and formatting
  tests/                         # real Edge end-to-end flow against isolated API/storage
storage/                         # ignored runtime state, separate from research data/results
  archive.sqlite3
  originals/<uuid>/original.ext
```

FastAPI sync endpoints delegate ingestion to a service and local adapters. SQLite connections are short-lived/per-operation; upload record and audit event commit together. Original bytes are streamed into a request-owned staging file, validated and published without overwrite under a generated UUID. A filesystem/DB crash gap remains: an orphan original is retained for reconciliation rather than deleted on ambiguous failure. The API rechecks file hash/size before delivery. This is application-level immutability, not a write-once storage device.

The Next app is an independent client of actual API endpoints; counts/search filters are server-derived. Upload success comes only from API 201. No fixture data seeds default storage. The API reports `stored / OCR_NOT_CONFIGURED`, with unavailable extraction/confidence/classification, rather than pretending a job ran. The status enum reserves future job states but no background queue is implemented. Production document IDs are UUIDs; research page IDs remain unchanged. A later processing adapter must explicitly associate them by source identity/run provenance.

All original experiments, GT approval/version control, benchmark metrics and historical predictions remain independent. No research threshold is promoted into application logic. The existing five components will attach as versioned processing/review/indexing services; this slice implements the preservation/metadata/traceability foundation they need. Authentication, real human-review UI, bounded persistent OCR jobs and recovery remain future work.

See [application startup/API documentation](web_application.md) and [Task 005 validation](task_005_validation.md) for exact implemented behavior and limits. Local servers bind loopback; unauthenticated access is not an institutional deployment model.

## Earlier target design and progress notes

Date: 2026-10-27. This is a target design, **not implemented application functionality**. No experimental source is moved or refactored in this audit.

Task 002 update: `src/smartarchive/evaluation/` now implements the saved-text benchmark portion of the proposed package. It contains metrics, validation, run tracking and CLI orchestration, with a repository-local launcher in `tools/benchmark_ocr.py`. No other proposed package areas are implemented. This is the incremental transition described below; historical scripts remain independent. See [benchmark guide](ocr_benchmark.md) for implemented contracts and policies.

Task 003 extends that same evaluation boundary with `pilot.py` (source/page inventory), `ground_truth.py` (append-only local revisions/review attestations), `historical.py` (explicit saved-output adapters) and `pilot_cli.py`. No major structural change, OCR execution, production review service or other platform area is introduced. GT sidecars remain gt-v1; history is stored alongside them. See [pilot workflow](pilot_workflow.md).

Task 004 adds `review_workspace.py` for offline source/RTL-text HTML workspaces and `error_analysis.py` for describing existing benchmark measurements. Both remain within evaluation; they introduce no server, package dependency, new metric policy or approval mechanism. CLI `workspace` prepares files only, and `compare` adds non-overwriting analysis artifacts. This is a local research aid, not the platform frontend.

## Approach and migration

Use a modular monolith: thin FastAPI routes, application services, domain contracts and replaceable processing/storage adapters. Avoid microservices, distributed queues and multiple databases for an eight-week solo project. Add dependencies only when implementing the corresponding feature.

Keep all six experimental scripts and outputs at their existing paths. Add benchmark modules beside them. Extract useful logic only after characterization and parity checks; preserve legacy code for historical reproducibility. Do not import `compare_ocr.py` as a library because it executes at import time.

## Proposed structure

Only documentation, characterization tests and a preservation verifier are added now. The `smartarchive` and `storage` trees below are proposals; no application placeholders are created.

```text
SmartArchive-X_POC/
  compare_ocr.py                  # existing experiment
  quality_analyzer.py             # existing experiment
  layout_ocr.py                   # existing experiment
  layout_ocr_v02.py               # existing experiment
  layout_ocr_v03.py               # existing experiment
  src/
    run_ocr.py                   # existing baseline
    smartarchive/                # PROPOSED package
      api/                      # FastAPI routes and request/response models
      domain/                   # documents, pages, artifacts, decisions
      services/                 # ingestion, processing, review, reclassification
      processing/               # rendering, quality, routing, layout, reconstruction
      ocr/                      # engine protocol and Tesseract/optional Paddle adapters
      classification/           # text/image evidence and reliability gate
      retrieval/                # chunks, lexical/vector adapters, fusion, provenance
      evaluation/               # GT policy, CER/WER, benchmark and reports
      persistence/              # file store, metadata repository, audit events
      config.py                 # explicit paths and versioned settings
  tests/                         # characterization now; service/integration later
  tools/                         # preservation verification now
  docs/                          # audit, protocol, architecture, backlog, decisions
  data/input/                    # existing originals
  data/ground_truth/             # independently reviewed references
  results/                       # preserve historical directories
    benchmark/<run_id>/          # PROPOSED exclusive run outputs
  storage/                       # PROPOSED immutable originals and derivatives
```

Dependency direction: API/CLI -> application services -> domain/contracts. Infrastructure implements contracts. Domain must not import FastAPI, OCR native libraries or database clients. Evaluation shares prediction contracts but GT never enters inference or test-set threshold tuning.

## Lifecycle and research components

1. **Ingestion and metadata:** retain exact original bytes, hash and original filename/type; assign stable document ID independent of stem. Reject source/output aliasing. A rendered image is a derivative, not the original. Preserve authorization and metadata provenance. Identical content may share storage while remaining separate institutional records.
2. **Quality-Aware OCR Routing:** render all pages with DPI, renderer version and hashes. Compute quality features as observations. Retain full-page baseline and candidate outputs with versioned routing reasons. Keep baseline/review fallback until thresholds are empirically validated.
3. **Layout-Aware Text Reconstruction:** store region/line/word boxes, raw text and explicit reading order separately from reconstructed text. Canonical bbox is pixel xyxy, top-left origin, right/bottom exclusive, with page dimensions and crop/scale transforms. Evaluate overlap duplicates and omitted spans. Do not reverse Arabic characters; mixed Latin/Arabic and tables need agreed ordering conventions. Ambiguity enters review.
4. **Reliability-Gated Multimodal Document Classification:** consume text and visual evidence with separate reliability measures. Store predicted class, evidence, raw scores, model/policy version and gate outcome: accept, abstain or review. Missing/unreliable OCR cannot silently become reliable input. Taxonomy and labels precede implementation; confidence is not calibrated probability by default.
5. **Confidence-Aware Hybrid Search and Indexing:** retain versioned chunks with document/page/region/span references, text artifact ID and OCR/review status. Compare lexical, semantic and fused rankings. Start with simple rank-fusion as a candidate; evaluate confidence filters/weights before adopting them. Return excerpt, page, region when available, original link and indexed version. OCR confidence is distinct from relevance.
6. **Controlled Document Reclassification:** create pending proposal against expected document version. Authorized human approval records actor, reason, old/new labels, evidence and policy/model version. Use optimistic concurrency and append-only events. Activate metadata/index as one logical version. If indexing fails, keep prior active version, expose pending state and retry idempotently. Rollback creates a new event/version. A metadata outbox record can coordinate retries before a queue is justified.

Future minimum contracts: Document, Page, Artifact, ProcessingRun, OCRResult, Region, MetadataField, ClassificationDecision, ReviewDecision, IndexVersion, SearchHit, ReclassificationEvent. Derived records include source IDs/hashes, schema/config/tool versions, status and errors. Keep raw evidence separate from accepted decisions; failed OCR is not successful empty text.

## Execution and storage candidates

FastAPI validates/submits work; CPU-heavy OCR must not block an async handler. Begin with a bounded local worker and persistent job state. Add timeouts, idempotent retries and restart recovery before claiming durable background processing. Reviewer identity and access control must cover search, review and original downloads before institutional use.

Local immutable files and SQLite are initial candidates, subject to concurrency requirements and backup design. SQLite FTS is a possible lexical baseline, but Arabic tokenization requires evaluation. Embedding model/vector store, classifier and gate thresholds remain undecided. No such dependency is added by this audit.

## Evidence gates

| Research component | Required validation |
| --- | --- |
| Quality routing | Paired fixed versus routed CER/WER, latency and route coverage; dev-only threshold tuning |
| Layout reconstruction | Matched reading-order GT, ordering/coverage checks, CER/WER, omitted/duplicated span review |
| Multimodal classification | Document-held-out macro-F1/confusion matrix, accepted coverage/error, text/visual/fused ablations |
| Hybrid search | Judged queries, Recall@k and nDCG@k or MRR, lexical/vector/hybrid and confidence-policy ablations, provenance checks |
| Reclassification | Authorization, stale-version rejection, audit completeness, interrupted indexing, retry and rollback tests |

Report failures, exclusions, dataset sizes and uncertainty. An eight-week demonstrator may limit implementation depth; it must not silently drop any of the five research components.
