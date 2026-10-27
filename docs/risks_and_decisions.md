# Risks and unresolved decisions

Date: 2026-10-27. Mitigations are planned unless explicitly recorded as delivered.

| Risk | Impact | Response / evidence needed |
| --- | --- | --- |
| One sample, no GT | No defensible improvement, calibration or generalization | Authorized representative documents and independent transcripts; document-level splits |
| Enhancement/line instability | Missing/duplicated text propagates to classification/search | Retain originals/candidates, CER/WER and layout evaluation, baseline/review fallback |
| Eight weeks, solo developer | Five research components plus app exceed capacity | Modular monolith, bounded prototypes, weekly gates; explicit supervisor agreement if scope depth changes |
| Ignored local artifacts | Machine loss/deletion destroys evidence | External controlled backup; hashes detect but do not restore |
| Uncalibrated confidence | False acceptance or biased ranking | Evaluate accepted coverage/error and confidence-policy retrieval ablations |
| Private records | Unauthorized storage/search/original access | Authorized local samples and consistent access control before institutional use; no uploads in this audit |
| Dependency/render drift | Nonrepeatable metrics | Record renderer/DPI/config/native languages, environment and derivative hashes |
| Partial jobs/index changes | Stale classifications and search results | Versioned active state, idempotent retries, persistent events/outbox |
| Arabic/mixed layout | Tokenization/order distorts results | Explicit conventions, annotated layouts and judged queries |

## Decisions recorded

Task 003 adds a deterministic one-page inventory and hash/pixel-validated historical bindings. The sample is literary/educational; representativeness and institutional authorization remain unresolved. Local review now has immutable revisions/events and latest-revision gating, but identity is still an unauthenticated human attestation. An old frozen benchmark remains historical evidence for its pinned reference; current official comparisons must prepare a new pilot bundle. No genuine GT or accuracy claim is delivered by this task.

- Preserve all experimental sources and outputs in place; no major refactor.
- Proposed modular monolith; no new runtime dependencies added.
- First benchmark targets installed Tesseract; Paddle optional and unvalidated.
- Image scores, text length and raw OCR confidence do not justify promotion.
- All five research components remain in the proposed architecture/backlog.

## Open decisions

Task 002 establishes versioned evaluator policies and a local review-attestation contract; see [benchmark guide](ocr_benchmark.md). Empty approved references have undefined rates with counts retained; strict and normalized results are reported separately. Source/page IDs, transcript hashes and distinct transcriber/reviewer fields are validated. Institutional acceptance of those policies, real reviewer authorization and genuine GT collection remain unresolved. Local manifests cannot prove human identity or that an OCR output really came from its declared page/engine.

| Decision | Owner / deadline | Candidate direction, not implemented |
| --- | --- | --- |
| Original research document/acceptance criteria | Developer + supervisor / week 1 | Supplied five-part scope until reconciled; numbered legacy mappings unverified |
| Dataset authorization, taxonomy and split | Developer + institution/supervisor / B01 | Authorized pilot, document-held-out split; dataset size subject to research needs |
| GT order, blank pages, BOM/Unicode and Arabic WER tokenization | Developer + transcript reviewer / before B03 | Preserve Arabic letters/diacritics; whitespace-only primary policy candidate; alternate normalization separate |
| OCR/classifier thresholds | Developer / after dev evaluation | Abstain/review until calibrated; no test-set tuning |
| Metadata fields and correction permissions | Developer + institution / before B09 | Human-reviewed fields with provenance |
| DB, lexical tokenizer and vector model/store | Developer / B09-B11 | Local files/SQLite candidates; measure Arabic retrieval before choosing semantic stack |
| Visual model and fusion gate | Developer / B10 | Simple text/visual baselines; assess labels, compute and model licensing |
| Confidence ranking treatment/query judgments | Developer + query reviewer / B11 | Expose evidence; evaluate fusion/filters before numerical confidence weights |
| Reviewer identity/auth, retention and backups | Developer + institution / before institutional use | Explicit roles and controlled local storage; backup destination unresolved |
| Reclassification authority/rollback semantics | Developer + supervisor / B12 | Human approval, expected version and new event on rollback |

No external paper, current dependency documentation or supervisor source was supplied/read. These are local-code-based engineering proposals, not validated backend/model recommendations.
