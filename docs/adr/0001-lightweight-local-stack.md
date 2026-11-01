# ADR 0001 — Lightweight local stack instead of the full service stack

- Status: accepted (2026-10-30)
- Context: the plan proposes PostgreSQL, Redis, Celery, MinIO, OpenSearch, Qdrant and Neo4j. The project is
  built and demonstrated by one developer on one Windows laptop within six weeks. The supervisor evaluates
  features and results, not the specific infrastructure.
- Decision: keep one FastAPI process with SQLite (WAL), write-once file storage, an in-process worker that
  uses a SQLite table as a persistent queue, SQLite FTS5 (BM25) for lexical search, a local vector index for
  dense retrieval and relation tables for the folder/knowledge graph.
- Consequences: no services to install or keep running; every feature in the plan stays implementable.
  Single-writer SQLite limits concurrency to a small institution; repositories are isolated so a later move
  to PostgreSQL/pgvector changes persistence code, not the API or the research components.
