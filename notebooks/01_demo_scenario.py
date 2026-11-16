#!/usr/bin/env python3
"""Notebook 01 — demo scenario: all four failure modes in one run.

Run: python notebooks/01_demo_scenario.py
Writes the consolidated view to results/demo_view.json.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from governed_shared_memory.access import Agent
from governed_shared_memory.consolidation import consolidate
from governed_shared_memory.memory import GovernedMemory

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    mem = GovernedMemory()
    for agent in [Agent("planner", "writer"), Agent("researcher", "writer"),
                  Agent("critic", "writer"), Agent("admin", "admin")]:
        mem.register(agent)

    # 1. Contradiction persistence: two writers, one fact.
    mem.write("planner", "project deadline is 12 January", "shared", "user")
    _, conflicts = mem.write("researcher", "project deadline is 20 January",
                             "shared", "agent:planner")
    print(f"conflicts on write: {len(conflicts)}")
    for c in conflicts:
        print(f"  [{c.kind}] {c.reason}")

    # 2. Unauthorized leakage: researcher tries planner's private space.
    mem.write("planner", "planner private note: draft budget figures",
              "planner", "user")
    try:
        mem.list_active("researcher", "planner")
        print("LEAK: read succeeded (this must not happen)")
    except PermissionError as exc:
        print(f"leak blocked: {exc}")

    # 3. Stale propagation + explicit supersession.
    old, _ = mem.write("planner", "conference budget is $500", "shared",
                       "user")
    mem.supersede("planner", old.record_id, "conference budget is $800",
                  "user")
    hits = mem.search("admin", "conference budget", "shared")
    print(f"search 'conference budget': {[r.text for r, _ in hits]}")

    # 4. Provenance: every record carries writer/source/confidence.
    view = consolidate(mem.store.list(namespace="shared", status=None),
                       "shared")
    out = ROOT / "results" / "demo_view.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(view.to_dict(), indent=2), encoding="utf-8")
    print(json.dumps(view.summary(), indent=2))
    print(f"wrote {out}")
    mem.close()


if __name__ == "__main__":
    main()
