# Dashboard

Streamlit app for governed shared memory. Runs the real pipeline: the
seeded scenario writes into a live `GovernedMemory`, and every tab
reads from it.

## Run

```bash
pip install streamlit
streamlit run dashboard/app.py
```

## Tabs

1. **Consolidated view** — four headline numbers (active memories,
   open conflicts, conflicted records, superseded), the open-conflict
   table, active memories newest first, and superseded memories with
   their replacement.
2. **Write a memory** — pick a writer, a namespace and a text; the
   app writes through `GovernedMemory.write` and shows any conflicts
   flagged on write, or the denial if the write is not allowed.
3. **Search** — BM25 search over the shared namespace as `admin`.
4. **Tombstones — what we used to believe** — every superseded record
   in shared memory with its replacement, the supersession reason and
   time, and its confidence decayed to now (24-hour half-life); pick
   one to see its whole supersession chain, oldest first.
5. **Audit log** — every write, read, supersession, denial and
   conflict, newest last.

## Seeded scenario

Seven memories from three writers: two writers disagree on the
project deadline (slot conflict), two disagree on saliency maps and
clinician trust (polarity conflict), one private planner note that
other agents cannot read, and shared facts about budget and venue —
plus one tombstone: the team offsite moved from Lahore to Karachi
("venue changed by organiser"). Expected headline numbers: 7 active,
2 open conflicts, 4 conflicted records, 1 superseded.

## Tests

`dashboard/helpers.py` is pure Python (no streamlit import) and is
unit-tested in `tests/test_dashboard_helpers.py`. The app itself is
verified with Streamlit's AppTest (0 exceptions on launch).
