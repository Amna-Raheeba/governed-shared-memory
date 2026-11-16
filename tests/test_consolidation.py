"""Consolidation: the team's belief state, conflicts included."""
from governed_shared_memory.consolidation import consolidate
from governed_shared_memory.records import MemoryRecord


def _rec(text, writer, status="active", rid=""):
    return MemoryRecord(text=text, writer=writer, namespace="shared",
                        source="user", status=status,
                        record_id=rid or None)


def test_summary_counts():
    records = [
        _rec("project deadline is 12 January", "planner", rid="mem-aaa"),
        _rec("project deadline is 20 January", "researcher", rid="mem-bbb"),
        _rec("team meeting is every Monday", "planner", rid="mem-ccc"),
        _rec("old budget is $500", "planner", status="superseded",
             rid="mem-ddd"),
    ]
    view = consolidate(records, "shared")
    summary = view.summary()
    assert summary["active"] == 3
    assert summary["superseded"] == 1
    assert summary["open_conflicts"] == 1
    assert summary["conflicted_records"] == 2
    assert summary["unconflicted_active"] == 1


def test_no_conflicts_when_writers_agree():
    records = [
        _rec("team meeting is every Monday", "planner", rid="mem-aaa"),
        _rec("workshop venue is Karachi", "researcher", rid="mem-bbb"),
    ]
    view = consolidate(records, "shared")
    assert view.conflicts == []
    assert view.summary()["open_conflicts"] == 0


def test_conflicted_ids_cover_both_sides():
    records = [
        _rec("project deadline is 12 January", "planner", rid="mem-aaa"),
        _rec("project deadline is 20 January", "researcher", rid="mem-bbb"),
    ]
    view = consolidate(records, "shared")
    assert view.conflicted_ids == {"mem-aaa", "mem-bbb"}


def test_superseded_records_listed_separately():
    old = _rec("budget is $500", "planner", status="superseded",
               rid="mem-old")
    new = _rec("budget is $800", "planner", rid="mem-new")
    view = consolidate([old, new], "shared")
    assert [r.record_id for r in view.superseded] == ["mem-old"]
    assert [r.record_id for r in view.active] == ["mem-new"]


def test_to_dict_round_trips_summary():
    records = [_rec("team meeting is every Monday", "planner", rid="mem-aaa")]
    view = consolidate(records, "shared")
    data = view.to_dict()
    assert data["namespace"] == "shared"
    assert data["active"][0]["text"] == "team meeting is every Monday"
