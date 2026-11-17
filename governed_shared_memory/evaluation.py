"""LongMemEval / LoCoMo-style evaluation harness.

The task set (``data/eval_tasks.json``) is hand-written and fully
documented: each task is a short multi-session scenario — agents write
memories across sessions, facts get updated, some writers contradict
each other, one agent tries to read another's private namespace — and
then questions are asked. Nothing here is a real benchmark: it is a
regression harness that measures whether the four governance
guarantees hold on scenarios designed to break them.

Metrics reported (all computed from real runs, never estimated):
- ``recall@k``: fraction of questions whose expected answer appears
  in the top-k retrieved *active* records.
- ``contradiction_recall``: fraction of planted cross-writer conflicts
  the detector flags.
- ``leak_blocked``: fraction of unauthorized read attempts denied.
- ``stale_leak``: fraction of questions where a superseded record —
  not its replacement — appears in the top-k (should be 0).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .access import Agent
from .bm25 import tokenize
from .memory import GovernedMemory
from .tombstones import DEFAULT_HALF_LIFE_SECONDS


@dataclass
class TaskResult:
    task_id: str
    question: str
    expected: str
    retrieved: list[str]
    hit: bool
    stale_hit: bool

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id, "question": self.question,
            "expected": self.expected, "retrieved": self.retrieved,
            "hit": self.hit, "stale_hit": self.stale_hit,
        }


@dataclass
class EvalReport:
    task_results: list[TaskResult] = field(default_factory=list)
    planted_conflicts: int = 0
    conflicts_flagged: int = 0
    leak_attempts: int = 0
    leaks_blocked: int = 0

    @property
    def recall_at_k(self) -> float:
        if not self.task_results:
            return 0.0
        return sum(r.hit for r in self.task_results) / len(self.task_results)

    @property
    def contradiction_recall(self) -> float:
        if not self.planted_conflicts:
            return 0.0
        return self.conflicts_flagged / self.planted_conflicts

    @property
    def leak_blocked_rate(self) -> float:
        if not self.leak_attempts:
            return 0.0
        return self.leaks_blocked / self.leak_attempts

    @property
    def stale_leak_rate(self) -> float:
        if not self.task_results:
            return 0.0
        return sum(r.stale_hit for r in self.task_results) / len(self.task_results)

    def summary(self) -> dict:
        return {
            "questions": len(self.task_results),
            "recall_at_k": round(self.recall_at_k, 4),
            "planted_conflicts": self.planted_conflicts,
            "conflicts_flagged": self.conflicts_flagged,
            "contradiction_recall": round(self.contradiction_recall, 4),
            "leak_attempts": self.leak_attempts,
            "leaks_blocked": self.leaks_blocked,
            "leak_blocked_rate": round(self.leak_blocked_rate, 4),
            "stale_leak_rate": round(self.stale_leak_rate, 4),
        }

    def to_dict(self) -> dict:
        return {
            **self.summary(),
            "tasks": [r.to_dict() for r in self.task_results],
        }


def _answer_tokens(expected: str) -> set[str]:
    return {t for t in tokenize(expected) if len(t) > 1}


# -- tombstone evaluation -------------------------------------------
# Seeded measurement for the v0.2.0 tombstone feature. Twelve
# supersessions are built with known reasons and fixed supersession
# times, then three things are measured — all from real runs:
# - ``tombstone_recall``: fraction of seeded superseded records
#   retrievable through ``tombstones()``.
# - ``decay_exact``: fraction of fixed-offset decay checks whose
#   decayed confidence equals ``original * 0.5 ** (age / half_life)``
#   to within 1e-9 — the decay curve is a claim, so it is checked
#   exactly, not approximately.
# - ``live_exclusion_rate``: fraction of checks where a live query
#   (``list_active`` / ``search``) does NOT return a tombstoned
#   record as a current fact.


@dataclass
class TombstoneReport:
    seeded_supersessions: int = 0
    tombstones_found: int = 0
    decay_checks: int = 0
    decay_exact: int = 0
    live_exclusion_checks: int = 0
    live_exclusion_passed: int = 0

    @property
    def tombstone_recall(self) -> float:
        if not self.seeded_supersessions:
            return 0.0
        return self.tombstones_found / self.seeded_supersessions

    @property
    def decay_exact_rate(self) -> float:
        if not self.decay_checks:
            return 0.0
        return self.decay_exact / self.decay_checks

    @property
    def live_exclusion_rate(self) -> float:
        if not self.live_exclusion_checks:
            return 0.0
        return self.live_exclusion_passed / self.live_exclusion_checks

    def summary(self) -> dict:
        return {
            "seeded_supersessions": self.seeded_supersessions,
            "tombstones_found": self.tombstones_found,
            "tombstone_recall": round(self.tombstone_recall, 4),
            "decay_checks": self.decay_checks,
            "decay_exact": self.decay_exact,
            "decay_exact_rate": round(self.decay_exact_rate, 4),
            "live_exclusion_checks": self.live_exclusion_checks,
            "live_exclusion_passed": self.live_exclusion_passed,
            "live_exclusion_rate": round(self.live_exclusion_rate, 4),
        }


def evaluate_tombstones(
    n_seeded: int = 12,
    half_life_seconds: float = DEFAULT_HALF_LIFE_SECONDS,
) -> TombstoneReport:
    """Seeded tombstone measurement on a fresh in-memory store.

    Each seeded record starts at confidence 0.8 and is superseded at
    a fixed time with a recorded reason; decay is then checked at
    0 / 24 / 48 / 72 hours after supersession against the exact
    half-life curve (0.8, 0.4, 0.2, 0.1).
    """
    base = datetime(2026, 11, 17, tzinfo=timezone.utc)
    mem = GovernedMemory()
    for agent in [Agent("planner", "writer"), Agent("researcher", "writer"),
                  Agent("admin", "admin")]:
        mem.register(agent)
    report = TombstoneReport()
    seeded_ids: list[str] = []
    for i in range(n_seeded):
        old, _ = mem.write(
            "planner", f"seeded budget is ${100 + i}", "shared", "user",
            confidence=0.8)
        stamp = (base + timedelta(hours=i)).isoformat()
        mem.supersede("planner", old.record_id,
                      f"seeded budget is ${200 + i}", "user",
                      reason=f"correction {i}", superseded_at=stamp)
        seeded_ids.append(old.record_id)
        report.seeded_supersessions += 1

    # 1. Tombstone recall: every seeded supersession retrievable.
    found = {t.record_id for t in mem.tombstones("admin", "shared")}
    report.tombstones_found = sum(1 for rid in seeded_ids if rid in found)

    # 2. Decay curve: exact at fixed offsets after supersession.
    stones = {t.record_id: t for t in mem.tombstones("admin", "shared")}
    for i, rid in enumerate(seeded_ids):
        stone = stones[rid]
        superseded_at = base + timedelta(hours=i)
        for hours in (0, 24, 48, 72):
            at = superseded_at + timedelta(hours=hours)
            expected = 0.8 * 0.5 ** (hours * 3600 / half_life_seconds)
            actual = stone.decayed_confidence(at.isoformat(),
                                              half_life_seconds)
            report.decay_checks += 1
            if abs(actual - expected) < 1e-9:
                report.decay_exact += 1

    # 3. Live-query exclusion: no tombstone in active lists or search.
    active_ids = {r.record_id for r in mem.list_active("admin", "shared")}
    for rid in seeded_ids:
        report.live_exclusion_checks += 1
        if rid not in active_ids:
            report.live_exclusion_passed += 1
    for i, rid in enumerate(seeded_ids):
        hits = mem.search("admin", f"seeded budget is ${100 + i}", "shared",
                          top_k=20)
        report.live_exclusion_checks += 1
        if all(r.record_id != rid for r, _ in hits):
            report.live_exclusion_passed += 1
    mem.close()
    return report


def run_evaluation(task_file: str | Path, top_k: int = 5) -> EvalReport:
    """Run every task in the JSON task file against a fresh memory."""
    tasks = json.loads(Path(task_file).read_text(encoding="utf-8"))
    report = EvalReport()

    for task in tasks:
        mem = GovernedMemory()
        for agent in task.get("agents", []):
            mem.register(Agent(agent["id"], agent.get("role", "writer")))
        written: dict[str, str] = {}  # label -> record_id
        superseded_ids: set[str] = set()
        for step in task.get("sessions", []):
            action = step["action"]
            if action == "write":
                record, _ = mem.write(
                    step["agent"], step["text"], step["namespace"],
                    step.get("source", "user"),
                    confidence=step.get("confidence", 1.0),
                    tags=step.get("tags", []),
                )
                if "label" in step:
                    written[step["label"]] = record.record_id
            elif action == "supersede":
                old_id = written[step["old_label"]]
                superseded_ids.add(old_id)
                record = mem.supersede(
                    step["agent"], old_id, step["text"],
                    step.get("source", "user"),
                    confidence=step.get("confidence", 1.0),
                )
                if "label" in step:
                    written[step["label"]] = record.record_id
            elif action == "leak_attempt":
                report.leak_attempts += 1
                try:
                    mem.list_active(step["agent"], step["namespace"])
                except PermissionError:
                    report.leaks_blocked += 1
            elif action == "conflict_check":
                report.planted_conflicts += 1
                conflicts = mem.open_conflicts(
                    step.get("agent", "admin"), step["namespace"])
                if conflicts:
                    report.conflicts_flagged += 1

        for question in task.get("questions", []):
            namespace = question.get("namespace", "shared")
            agent = question.get("agent", "admin")
            hits = mem.search(agent, question["query"], namespace, top_k=top_k)
            retrieved_texts = [r.text for r, _ in hits]
            expected = question["expected"]
            tokens = _answer_tokens(expected)
            hit = any(
                tokens and tokens <= set(tokenize(t))
                for t in retrieved_texts
            )
            stale = any(
                r.record_id in superseded_ids for r, _ in hits
            )
            report.task_results.append(TaskResult(
                task_id=task["id"], question=question["query"],
                expected=expected, retrieved=retrieved_texts,
                hit=hit, stale_hit=stale,
            ))
        mem.close()
    return report
