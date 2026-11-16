"""Contradiction-aware consolidation.

Consolidation answers one question: *what does the team currently
believe?* The answer is a view, not a rewrite:

- **Active memories** — every record with status ``active``, with its
  provenance, newest first.
- **Open conflicts** — every unresolved contradiction among them,
  grouped by the records involved. A conflicted fact is shown *with
  both sides*, never resolved by picking the newer one.
- **Superseded memories** — listed separately, with their replacement
  linked, so a reader can audit what changed.

Nothing here deletes or edits a record. Resolving a conflict means
calling :meth:`GovernedMemory.supersede` — an explicit, governed,
audit-logged act — and the next consolidation shows the result.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .contradictions import Conflict, detect_all
from .records import MemoryRecord


@dataclass
class ConsolidatedView:
    """The team's current belief state for one namespace."""

    namespace: str
    active: list[MemoryRecord] = field(default_factory=list)
    conflicts: list[Conflict] = field(default_factory=list)
    superseded: list[MemoryRecord] = field(default_factory=list)

    @property
    def conflicted_ids(self) -> set[str]:
        ids: set[str] = set()
        for conflict in self.conflicts:
            ids.add(conflict.record_a)
            ids.add(conflict.record_b)
        return ids

    def summary(self) -> dict:
        return {
            "namespace": self.namespace,
            "active": len(self.active),
            "superseded": len(self.superseded),
            "open_conflicts": len(self.conflicts),
            "conflicted_records": len(self.conflicted_ids),
            "unconflicted_active": len(self.active) - len(self.conflicted_ids),
        }

    def to_dict(self) -> dict:
        return {
            **self.summary(),
            "active": [r.to_dict() for r in self.active],
            "conflicts": [c.to_dict() for c in self.conflicts],
            "superseded": [r.to_dict() for r in self.superseded],
        }


def consolidate(records: list[MemoryRecord], namespace: str) -> ConsolidatedView:
    """Build the consolidated view for one namespace's records."""
    active = [r for r in records if r.status == "active"]
    superseded = [r for r in records if r.status == "superseded"]
    active.sort(key=lambda r: (r.created_at, r.record_id), reverse=True)
    superseded.sort(key=lambda r: (r.created_at, r.record_id), reverse=True)
    return ConsolidatedView(
        namespace=namespace,
        active=active,
        conflicts=detect_all(active),
        superseded=superseded,
    )
