# ADR 0005 — Explainable classification with human confirmation; snapshot scope

Status: accepted (Sprint 3, v0.8.0)

## Context
Documents must be classified into institutional categories. There is no labelled corpus yet, so a trained
model cannot be evaluated honestly. Archivists need to see why a category was proposed and to correct it.

## Decision
- Baseline classifier `keywords-v1`: categories are lists of keywords maintained by administrators. Matching
  uses the search normalization and whole words with optional clitics. Scores add occurrences (capped at 3 per
  keyword), a heading bonus and a file-name bonus. Confidence compares the leader with the runner-up. Below a
  score of 3 or confidence of 0.5 the classifier abstains instead of guessing.
- The classifier only suggests. A category is final when a person confirms it; changing a confirmed category
  requires a reason. Every suggestion and decision is kept in the append-only `classifications` table, and
  the current category is a view over it, so history can never be rewritten.
- Machine suggestions are not written to the document audit log (they are in the classification history);
  human decisions are.
- Confirmed categories become labelled data. A statistical or embedding model can be added later as another
  `method` behind the same API and compared against `keywords-v1` on those labels.

## Snapshot scope (quality gate)
Per-task snapshots from Task 006 recorded every file a task left unchanged, including application code. That
would make every later change to the application fail the gate, although git already versions it. From this
sprint, `tools/check.py` verifies the Task 006+ snapshots without application paths (listed in `APPLICATION`),
so research code, inputs, results and legacy tests remain protected; snapshots 003–005 and the 108 historical
files are verified in full as before.
