"""Contradiction detection: slot and polarity conflicts."""
from governed_shared_memory.contradictions import (
    Conflict, detect_all, detect_for_new, detect_pair,
)
from governed_shared_memory.records import MemoryRecord


def _rec(text, writer="planner"):
    return MemoryRecord(text=text, writer=writer, namespace="shared",
                        source="user")


def test_slot_conflict_on_dates():
    a = _rec("project deadline is 12 January", "planner")
    b = _rec("project deadline is 20 January", "researcher")
    conflict = detect_pair(a, b)
    assert conflict is not None
    assert conflict.kind == "slot"
    assert conflict.writer_a == "planner"


def test_slot_conflict_on_money():
    a = _rec("conference budget is $800", "planner")
    b = _rec("conference budget is $1200", "researcher")
    conflict = detect_pair(a, b)
    assert conflict is not None and conflict.kind == "slot"


def test_no_conflict_when_values_agree():
    a = _rec("project deadline is 12 January", "planner")
    b = _rec("the project deadline is 12 January", "researcher")
    assert detect_pair(a, b) is None


def test_polarity_conflict():
    a = _rec("saliency maps improved clinician trust", "researcher")
    b = _rec("saliency maps did not improve clinician trust", "critic")
    conflict = detect_pair(a, b)
    assert conflict is not None
    assert conflict.kind == "polarity"


def test_no_conflict_when_polarity_agrees():
    a = _rec("saliency maps improved clinician trust", "researcher")
    b = _rec("saliency maps also improved clinician trust", "critic")
    assert detect_pair(a, b) is None


def test_same_writer_is_never_a_conflict():
    a = _rec("project deadline is 12 January", "planner")
    b = _rec("project deadline is 20 January", "planner")
    assert detect_pair(a, b) is None


def test_too_few_shared_terms_is_not_a_conflict():
    a = _rec("deadline is 12 January", "planner")
    b = _rec("budget is $800", "researcher")
    assert detect_pair(a, b) is None


def test_detect_for_new_flags_only_cross_writer():
    existing = [
        _rec("project deadline is 12 January", "planner"),
        _rec("conference budget is $800", "researcher"),
    ]
    new = _rec("project deadline is 20 January", "researcher")
    conflicts = detect_for_new(new, existing)
    assert len(conflicts) == 1
    assert conflicts[0].kind == "slot"


def test_detect_all_finds_pairwise_conflicts():
    records = [
        _rec("project deadline is 12 January", "planner"),
        _rec("project deadline is 20 January", "researcher"),
        _rec("team meeting is every Monday", "critic"),
    ]
    assert len(detect_all(records)) == 1


def test_conflict_serialises():
    conflict = Conflict(kind="slot", record_a="a", record_b="b",
                        writer_a="planner", writer_b="researcher",
                        shared_terms=["project"], reason="r")
    data = conflict.to_dict()
    assert data["kind"] == "slot" and data["record_a"] == "a"
