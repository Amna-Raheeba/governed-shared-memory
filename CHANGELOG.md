# Changelog

## 0.2.0 — 2026-11-17
- Provenance-preserving tombstones with confidence decay
  (`tombstones.py`): superseded records stay queryable as history
  carrying the superseding record's id, the supersession reason, and
  the supersession time; confidence decays deterministically on an
  exponential 24-hour half-life (`decayed = original × 0.5^(age/24h)`).
  New queries: `tombstones(agent, namespace)` and
  `tombstone_history(agent, record_id)` (full chain, oldest first).
  Live queries never return a tombstone as a current fact.
- `supersede()` now takes a `reason` (recorded on the old record and
  in the audit log) and an optional fixed `superseded_at` for
  deterministic replays; `MemoryRecord` gains `superseded_at`,
  `supersession_reason`, and `is_tombstone`.
- Store migration: pre-0.2.0 SQLite files gain the two new columns
  automatically; tombstones built from legacy rows report their
  original confidence (age unknown) instead of a decay from a guessed
  date. Fixed a real bug the migration test caught: positional
  `INSERT` wrote values into the wrong columns on migrated databases
  (ALTER TABLE appends at the end) — inserts now name their columns.
- Dashboard: new "Tombstones — what we used to believe" tab with the
  decayed-confidence table and per-record chain view; seeded scenario
  now includes one real tombstone (offsite moved Lahore → Karachi).
  Fixed the `use_container_width` deprecation (now `width="stretch"`).
- CLI: new `history` and `tombstones` commands; demo supersession now
  carries a reason.
- Seeded tombstone evaluation (`evaluation.py`,
  `notebooks/03_tombstone_evaluation.py`): recall 1.00 (12/12),
  decay exact 48/48, live exclusion 24/24.
- 87 tests (18 new), green locally and in CI.

## 0.1.0 — 2026-11-16
- First release: governed shared memory for multi-agent LLM systems.
- Per-agent private namespaces + governed shared space (`access.py`):
  roles reader < writer < admin; denied reads/writes audit-logged.
- Contradiction detection on write (`contradictions.py`): slot conflicts
  (date/money/number values) + polarity conflicts, adapted from the
  evidence-graph detector in multi-agent-research-assistant.
- Provenance on every record (`records.py`): writer, timestamp, source,
  confidence are required fields; content-addressed ids.
- Explicit supersession (`memory.py`): old records marked superseded,
  never deleted; `history()` follows the supersession chain.
- Contradiction-aware consolidation (`consolidation.py`): active +
  open conflicts + superseded, as a view — nothing is edited.
- Pure-Python BM25 retrieval (`bm25.py`) with recency tie-break.
- SQLite + JSON store (`store.py`) with append-only audit log.
- LongMemEval/LoCoMo-style eval harness (`evaluation.py`,
  `data/eval_tasks.json`): 6 scenarios, 8 questions — recall@5 1.00,
  contradiction recall 1.00 (2/2), leak blocked 1.00 (1/1),
  stale leak 0.00.
- Streamlit dashboard (`dashboard/`): consolidated view, write form,
  BM25 search, audit log — verified with AppTest, 0 exceptions.
- CLI (`python -m governed_shared_memory`): demo, evaluate, write,
  search, conflicts, consolidate.
- 67 tests, green locally (plain `pytest`, bare venv) and in CI.
