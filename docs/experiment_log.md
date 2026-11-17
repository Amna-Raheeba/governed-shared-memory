# Experiment Log

## 2026-11-16 — v0.1.0 build

### What was built
Governed shared memory library, stdlib-only, offline. Package
`governed_shared_memory/` (records, access, contradictions, bm25,
store, memory, consolidation, evaluation, CLI) + Streamlit dashboard
+ 6-scenario eval task set + 67 tests.

### Measured results (all from real runs, 2026-11-16)
- `pytest -q` (bare venv, plain binary, same command CI uses):
  **67 passed**.
- `python -m governed_shared_memory evaluate`:
  recall@5 **1.00** (8/8 questions), contradiction recall **1.00**
  (2/2 planted conflicts), leak blocked **1.00** (1/1), stale leak
  **0.00**. Full table in `results/evaluation.csv`.
- Dashboard AppTest: **0 exceptions**; metrics 6 active / 2 open
  conflicts / 4 conflicted records / 0 superseded (seeded scenario).

### Bugs found while testing (fixed, with regression tests)
1. **Polarity detection missed "did not".** The detector reused the
   BM25 tokenizer, which strips stopwords — including "did" and
   "not". "saliency maps did not improve clinician trust" scored as
   positive. Fix: polarity now uses a raw tokenizer with nothing
   removed (`_raw_tokens`). Regression test:
   `test_polarity_conflict`.
2. **Slot conflicts needed 3 shared terms, but the differing value
   can never count as one.** "conference budget is $800" vs "$1200"
   shares only "conference, budget" — 2 terms — so no flag. Fix:
   slot conflicts need 2 shared non-numeric terms; polarity keeps
   the bar at 3. Regression test: `test_slot_conflict_on_money`.
3. **BM25 ties surfaced the older side of a conflict first.** In the
   eval task `cross-writer-conflict`, top-1 was "12 January" (the
   record the other writer had already contradicted). Fix: search
   now breaks score ties toward the newest record (two stable sorts
   in `GovernedMemory.search`). Regression test:
   `test_search_tie_breaks_toward_newest_record`. Note: recall@5 was
   1.00 even before the fix — the expected answer was in the top-5 —
   which is exactly why top-1 is also recorded in
   `results/evaluation.csv`.

### Honest limits (recorded, not hidden)
- The eval task set is hand-written for this system: 8 questions, 2
  planted conflicts, 1 leak attempt. Perfect scores are expected on
  scenarios built for the guarantees; this is a regression harness,
  not evidence about real agent traffic.
- Both detectors are lexical heuristics. Paraphrased disagreement
  ("the deadline moved" vs "deadline is 12 January") is missed.
- Confidence is writer-reported, not calibrated — a confident wrong
  writer still outranks a cautious right one in the view.
- BM25 is lexical: semantically similar facts in different words may
  not retrieve together.

## 2026-11-17 — v0.2.0 audit + tombstones

### Audit (completeness check before the feature)
- `pytest -q` (bare venv, plain binary, same command CI uses):
  **67 passed** before any change.
- Local vs remote file comparison (connector reads, recursive):
  **37/37 files identical** — nothing missing on either side. The
  one size mismatch (`results/evaluation.csv`, 1096 vs 1077 bytes)
  was a GitHub API reporting artifact: the contents compared equal.
- No TODOs, placeholders, or dead code (grep clean). The single
  external link in the README (multi-agent-research-assistant) points
  at a real repo.
- Dashboard AppTest before the change: **0 exceptions**; metrics 6
  active / 2 open conflicts / 4 conflicted records / 0 superseded.
- Real gap found: `supersede()` recorded neither the reason nor the
  time of a replacement — `history()` could show what changed, never
  why. That gap is what the tombstone feature closes. The store also
  had no migration path for schema changes.

### What was built
Provenance-preserving tombstones with confidence decay
(`tombstones.py`, 18 new tests): superseded records stay queryable
as history with the superseding record's id, the reason, and the
time; confidence decays deterministically on an exponential 24-hour
half-life. New queries `tombstones()` and `tombstone_history()`;
`supersede()` takes a `reason` and an optional fixed
`superseded_at`; dashboard gains a Tombstones tab (seeded scenario
now includes one real tombstone); CLI gains `history` and
`tombstones` commands; `use_container_width` deprecation fixed.

### Measured results (all from real runs, 2026-11-17)
- `pytest -q` (bare venv): **87 passed** (67 original + 18 new +
  2 dashboard-helper tests).
- `python notebooks/03_tombstone_evaluation.py` (12 seeded
  supersessions): tombstone recall **1.00** (12/12), decay exact
  **48/48** checks at 0/24/48/72 h, live-query exclusion **24/24**.
  Full table in `results/tombstone_evaluation.json/.csv`.
- `python -m governed_shared_memory demo` and `evaluate` unchanged:
  recall@5 1.00, contradiction recall 1.00, leak blocked 1.00,
  stale leak 0.00.
- Dashboard AppTest: **0 exceptions**; 5 tabs; metrics 7 active /
  2 open conflicts / 4 conflicted records / 1 superseded, plus 1
  tombstone in the new tab.

### Bugs found while testing (fixed, with regression tests)
1. **Positional INSERT wrote values into the wrong columns on
   migrated databases.** `ALTER TABLE` appends new columns at the
   end, so a v0.1.0 database's physical order is
   `..., supersedes, tags, superseded_at, supersession_reason` while
   a fresh database is `..., supersedes, superseded_at,
   supersession_reason, tags`. The 13-value positional insert put
   `tags` into `superseded_at` and vice versa, and reads back crashed
   on `json.loads(None)`. Fix: inserts now name their columns.
   Regression test:
   `test_sqlite_persistence_and_old_schema_migration`.
2. **Dashboard edit landed inside the wrong code fence.**
   `examples/sample_session.md` was edited by matching a bare
   triple-backtick, which matched the opening fence of the demo block
   instead of the closing one, and the new tombstone section landed
   inside the code block. Fix: the file was rewritten cleanly and
   re-read to verify structure.

### Honest limits (recorded, not hidden)
- The decay curve is exact because it is a formula, not a
  measurement: the 48 checks prove the implementation follows
  `original × 0.5^(age/24h)`, not that 24 hours is the right
  half-life. The half-life is a policy choice; decay models salience,
  not truth.
- Tombstone recall is measured on a seeded set built for the system
  (12 supersessions) — a regression harness, not evidence about real
  agent traffic.
- A supersession reason is only as honest as the writer that supplies
  it: nothing verifies that "corrected by user" is the true reason.
  A missing reason is stored as NULL and shown as "not recorded",
  never invented.
