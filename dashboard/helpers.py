"""Data-shaping helpers for the Streamlit dashboard.

Pure Python on purpose — no streamlit import — so the shaping logic
is unit-tested in ``tests/test_dashboard_helpers.py`` and the app file
stays a thin presentation layer.
"""
from __future__ import annotations

from typing import Any

from governed_shared_memory.consolidation import ConsolidatedView
from governed_shared_memory.records import AuditEntry, MemoryRecord
from governed_shared_memory.tombstones import Tombstone


def memory_rows(records: list[MemoryRecord]) -> list[dict[str, Any]]:
    """One row per record: the fields a human scans first."""
    return [
        {
            "id": r.record_id,
            "text": r.text,
            "writer": r.writer,
            "namespace": r.namespace,
            "source": r.source,
            "confidence": round(r.confidence, 2),
            "status": r.status,
            "created_at": r.created_at,
            "supersedes": r.supersedes or "",
            "superseded_by": r.superseded_by or "",
        }
        for r in records
    ]


def conflict_rows(view: ConsolidatedView) -> list[dict[str, Any]]:
    """One row per open conflict, with both writers named."""
    return [
        {
            "kind": c.kind,
            "record_a": c.record_a,
            "writer_a": c.writer_a,
            "record_b": c.record_b,
            "writer_b": c.writer_b,
            "reason": c.reason,
        }
        for c in view.conflicts
    ]


def summary_cards(view: ConsolidatedView) -> dict[str, int]:
    """The four numbers the overview page leads with."""
    summary = view.summary()
    return {
        "active": summary["active"],
        "open_conflicts": summary["open_conflicts"],
        "conflicted_records": summary["conflicted_records"],
        "superseded": summary["superseded"],
    }


def tombstone_rows(tombstones: list[Tombstone],
                   at: str | None = None) -> list[dict[str, Any]]:
    """One row per tombstone: what we believed, when it changed, why,
    and how much confidence it still carries at the reference time."""
    return [
        {
            "id": t.record_id,
            "text": t.text,
            "writer": t.writer,
            "superseded_by": t.superseded_by or "",
            "superseded_at": t.superseded_at or "unknown",
            "reason": t.supersession_reason or "not recorded",
            "original_confidence": round(t.original_confidence, 2),
            "decayed_confidence": round(t.decayed_confidence(at), 3),
        }
        for t in tombstones
    ]


def audit_rows(entries: list[AuditEntry]) -> list[dict[str, Any]]:
    return [
        {
            "action": e.action,
            "actor": e.actor,
            "record_id": e.record_id or "",
            "namespace": e.namespace or "",
            "detail": e.detail,
            "created_at": e.created_at,
        }
        for e in entries
    ]
