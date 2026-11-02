# ADR 0006 — Verified backups, safe restore, integrity reconciliation, evaluation on reviewed data

Status: accepted (Sprint 4, v0.9.0)

## Decision
- A backup is a single zip: SQLite online-backup snapshot (consistent while the API runs), every original
  referenced by that snapshot, and a manifest with SHA-256 and size of each member. A backup is refused if any
  original is missing or does not match its recorded hash, so a backup never silently carries damage.
- Verification recomputes every hash, runs `PRAGMA integrity_check` on the snapshot and checks each document's
  original against the database row.
- Restore writes only into a new or empty folder, after verification, and re-hashes what it wrote. Switching
  the running archive to it is an explicit operator step (`SMARTARCHIVE_STORAGE_DIR`). Nothing overwrites live data.
- The integrity check reports, never repairs: deleting or "fixing" originals automatically could destroy evidence.
- Evaluation uses data the archive already holds: corrected pages (post-editing CER/WER, policy normalized-v1
  from the research metrics module) and confirmed categories (coverage, accuracy, per-category P/R/F1,
  confusion). Both reports state their bias; neither replaces an independent test set.

## Consequences
- Backups in `storage/backups` share the disk with the archive; the UI and README tell the operator to copy
  them elsewhere. `SMARTARCHIVE_BACKUP_DIR` can point to another drive.
- Backup size grows with the archive (originals are stored uncompressed inside the zip); incremental backups
  are a later optimisation.
