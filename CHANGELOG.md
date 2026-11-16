# Changelog

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
