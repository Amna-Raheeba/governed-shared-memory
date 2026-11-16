#!/usr/bin/env python3
"""Notebook 02 — run the eval task set and write results/evaluation.csv.

Run: python notebooks/02_evaluation.py
"""
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from governed_shared_memory.evaluation import run_evaluation

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    report = run_evaluation(ROOT / "data" / "eval_tasks.json")
    out = ROOT / "results" / "evaluation.csv"
    out.parent.mkdir(exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["task_id", "question", "expected", "hit",
                         "stale_hit", "retrieved_top1"])
        for r in report.task_results:
            writer.writerow([r.task_id, r.question, r.expected, r.hit,
                             r.stale_hit, r.retrieved[0] if r.retrieved else ""])
        writer.writerow([])
        for key, value in report.summary().items():
            writer.writerow([key, value])
    print(json.dumps(report.summary(), indent=2))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
