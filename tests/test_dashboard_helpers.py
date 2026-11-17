"""Dashboard helpers: shaping only, no streamlit."""
from datetime import datetime, timedelta, timezone

from governed_shared_memory.consolidation import consolidate
from governed_shared_memory.records import AuditEntry, MemoryRecord
from governed_shared_memory.tombstones import Tombstone
from dashboard.helpers import (
    audit_rows, conflict_rows, memory_rows, summary_cards, tombstone_rows,
)


def _rec(text, writer, status="active", rid="mem-x"):
    return MemoryRecord(text=text, writer=writer, namespace="shared",
                        source="user", status=status, record_id=rid)


def test_memory_rows_include_provenance():
    rows = memory_rows([_rec("budget is $800", "planner")])
    assert rows[0]["writer"] == "planner"
    assert rows[0]["source"] == "user"
    assert rows[0]["status"] == "active"


def test_conflict_rows_name_both_writers():
    records = [
        MemoryRecord(text="project deadline is 12 January", writer="planner",
                     namespace="shared", source="user", record_id="mem-a"),
        MemoryRecord(text="project deadline is 20 January",
                     writer="researcher", namespace="shared", source="user",
                     record_id="mem-b"),
    ]
    view = consolidate(records, "shared")
    rows = conflict_rows(view)
    assert len(rows) == 1
    # a/b order follows recency, so assert the pair, not the order.
    assert {rows[0]["writer_a"], rows[0]["writer_b"]} == {
        "planner", "researcher"}


def test_summary_cards_match_view():
    records = [_rec("team meeting is every Monday", "planner")]
    view = consolidate(records, "shared")
    cards = summary_cards(view)
    assert cards == {"active": 1, "open_conflicts": 0,
                     "conflicted_records": 0, "superseded": 0}


def test_audit_rows_shape():
    entries = [AuditEntry(action="deny", actor="researcher",
                          namespace="planner", detail="no read access")]
    rows = audit_rows(entries)
    assert rows[0]["action"] == "deny"
    assert rows[0]["actor"] == "researcher"


def test_memory_rows_empty_for_no_records():
    assert memory_rows([]) == []


def test_tombstone_rows_show_reason_and_decayed_confidence():
    base = datetime(2026, 11, 17, tzinfo=timezone.utc)
    stone = Tombstone(
        record_id="mem-old", text="team offsite is Lahore",
        writer="planner", namespace="shared", source="user",
        original_confidence=0.8, superseded_by="mem-new",
        superseded_at=base.isoformat(),
        supersession_reason="venue changed by organiser",
        created_at=base.isoformat())
    rows = tombstone_rows(
        [stone], at=(base + timedelta(hours=24)).isoformat())
    assert len(rows) == 1
    assert rows[0]["reason"] == "venue changed by organiser"
    assert rows[0]["original_confidence"] == 0.8
    assert rows[0]["decayed_confidence"] == 0.4
    assert rows[0]["superseded_by"] == "mem-new"


def test_tombstone_rows_unknown_reason_and_time():
    stone = Tombstone(
        record_id="mem-legacy", text="old fact", writer="planner",
        namespace="shared", source="user", original_confidence=0.8,
        superseded_by="mem-new", superseded_at=None,
        supersession_reason=None,
        created_at="2026-11-16T00:00:00+00:00")
    rows = tombstone_rows([stone])
    assert rows[0]["reason"] == "not recorded"
    assert rows[0]["superseded_at"] == "unknown"
    assert rows[0]["decayed_confidence"] == 0.8
