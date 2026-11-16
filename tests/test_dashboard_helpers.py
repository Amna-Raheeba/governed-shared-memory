"""Dashboard helpers: shaping only, no streamlit."""
from governed_shared_memory.consolidation import consolidate
from governed_shared_memory.records import AuditEntry, MemoryRecord
from dashboard.helpers import (
    audit_rows, conflict_rows, memory_rows, summary_cards,
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
