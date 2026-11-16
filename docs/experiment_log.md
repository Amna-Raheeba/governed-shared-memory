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
