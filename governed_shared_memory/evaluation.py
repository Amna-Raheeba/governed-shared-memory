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
from pathlib import Path

from .access import Agent
from .bm25 import tokenize
from .memory import GovernedMemory


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
