"""Notebook 03: tombstone evaluation — seeded supersession measurement.

Run from the repo root:

    python notebooks/03_tombstone_evaluation.py

Builds 12 supersessions with known reasons and fixed supersession
times, then measures tombstone recall, decay-curve exactness at
0/24/48/72 hours, and live-query exclusion — and writes
results/tombstone_evaluation.json and results/tombstone_evaluation.csv.
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from governed_shared_memory.evaluation import evaluate_tombstones

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    report = evaluate_tombstones(n_seeded=12)
    summary = report.summary()
    print(json.dumps(summary, indent=2))

    out = ROOT / "results"
    out.mkdir(parents=True, exist_ok=True)
    (out / "tombstone_evaluation.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8")
    with open(out / "tombstone_evaluation.csv", "w", newline="",
              encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["metric", "value"])
        for key, value in summary.items():
            writer.writerow([key, value])
    print("Results written to results/tombstone_evaluation.json "
          "and results/tombstone_evaluation.csv")


if __name__ == "__main__":
    main()
