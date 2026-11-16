"""Command-line interface for governed shared memory.

    python -m governed_shared_memory demo
    python -m governed_shared_memory evaluate
    python -m governed_shared_memory write --agent planner --namespace shared \\
        --text "project deadline is 12 January" --source user
    python -m governed_shared_memory search --agent planner --query deadline
    python -m governed_shared_memory conflicts --agent admin
    python -m governed_shared_memory consolidate --agent admin
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .access import Agent
from .consolidation import consolidate
from .evaluation import run_evaluation
from .memory import GovernedMemory

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = ROOT / "memory.db"

DEMO_AGENTS = [
    Agent("planner", "writer"),
    Agent("researcher", "writer"),
    Agent("critic", "writer"),
    Agent("admin", "admin"),
]


def _open(db: Path) -> GovernedMemory:
    mem = GovernedMemory(db, DEMO_AGENTS)
    return mem


def cmd_demo(_args: argparse.Namespace) -> int:
    """A three-agent scenario that exercises all four guarantees."""
    mem = GovernedMemory()
    for agent in DEMO_AGENTS:
        mem.register(agent)
    rec, conflicts = mem.write(
        "planner", "project deadline is 12 January", "shared", "user")
    print(f"planner wrote {rec.record_id} ({len(conflicts)} conflicts)")
    rec2, conflicts = mem.write(
        "researcher", "project deadline is 20 January", "shared",
        "agent:planner")
    print(f"researcher wrote {rec2.record_id} ({len(conflicts)} conflicts)")
    for conflict in conflicts:
        print(f"  CONFLICT [{conflict.kind}]: {conflict.reason}")
    rec3, _ = mem.write(
        "planner", "planner private note: draft budget figures",
        "planner", "user")
    try:
        mem.list_active("researcher", "planner")
    except PermissionError as exc:
        print(f"  leak blocked: {exc}")
    new = mem.supersede(
        "planner", rec.record_id, "project deadline is 20 January", "user")
    print(f"planner superseded {rec.record_id} with {new.record_id}")
    view = consolidate(mem.store.list(namespace="shared", status=None), "shared")
    print(json.dumps(view.summary(), indent=2))
    mem.close()
    return 0


def cmd_evaluate(_args: argparse.Namespace) -> int:
    report = run_evaluation(ROOT / "data" / "eval_tasks.json")
    print(json.dumps(report.summary(), indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="governed-shared-memory")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("demo", help="run the three-agent demo scenario")
    sub.add_parser("evaluate", help="run the eval task set")

    p_write = sub.add_parser("write", help="write a memory")
    p_write.add_argument("--agent", required=True)
    p_write.add_argument("--namespace", default="shared")
    p_write.add_argument("--text", required=True)
    p_write.add_argument("--source", default="user")
    p_write.add_argument("--confidence", type=float, default=1.0)
    p_write.add_argument("--db", default=str(DEFAULT_DB))

    p_search = sub.add_parser("search", help="BM25 search active memories")
    p_search.add_argument("--agent", required=True)
    p_search.add_argument("--query", required=True)
    p_search.add_argument("--namespace", default="shared")
    p_search.add_argument("--top-k", type=int, default=5)
    p_search.add_argument("--db", default=str(DEFAULT_DB))

    p_conf = sub.add_parser("conflicts", help="list open conflicts")
    p_conf.add_argument("--agent", default="admin")
    p_conf.add_argument("--namespace", default="shared")
    p_conf.add_argument("--db", default=str(DEFAULT_DB))

    p_con = sub.add_parser("consolidate", help="show consolidated view")
    p_con.add_argument("--agent", default="admin")
    p_con.add_argument("--namespace", default="shared")
    p_con.add_argument("--db", default=str(DEFAULT_DB))

    args = parser.parse_args(argv)
    if args.command == "demo":
        return cmd_demo(args)
    if args.command == "evaluate":
        return cmd_evaluate(args)

    mem = _open(Path(args.db))
    try:
        if args.command == "write":
            record, conflicts = mem.write(
                args.agent, args.text, args.namespace, args.source,
                confidence=args.confidence)
            print(json.dumps({**record.to_dict(),
                              "conflicts": [c.to_dict() for c in conflicts]},
                             indent=2))
        elif args.command == "search":
            for record, score in mem.search(args.agent, args.query,
                                            args.namespace, top_k=args.top_k):
                print(f"{score:.3f} [{record.writer}] {record.text}")
        elif args.command == "conflicts":
            for conflict in mem.open_conflicts(args.agent, args.namespace):
                print(f"[{conflict.kind}] {conflict.reason}")
        elif args.command == "consolidate":
            view = consolidate(
                mem.store.list(namespace=args.namespace, status=None),
                args.namespace)
            print(json.dumps(view.to_dict(), indent=2))
    finally:
        mem.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
