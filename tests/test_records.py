"""Records: provenance is required, never optional."""
import pytest

from governed_shared_memory.records import AuditEntry, MemoryRecord, new_id


def test_record_requires_text():
    with pytest.raises(ValueError):
        MemoryRecord(text="  ", writer="planner", namespace="shared", source="user")


def test_record_requires_writer():
    with pytest.raises(ValueError):
        MemoryRecord(text="x", writer="", namespace="shared", source="user")


def test_confidence_bounds():
    with pytest.raises(ValueError):
        MemoryRecord(text="x", writer="a", namespace="shared", source="user",
                     confidence=1.5)
    with pytest.raises(ValueError):
        MemoryRecord(text="x", writer="a", namespace="shared", source="user",
                     confidence=-0.1)


def test_provenance_block_is_complete():
    rec = MemoryRecord(text="deadline is 12 January", writer="planner",
                       namespace="shared", source="user", confidence=0.8)
    prov = rec.provenance()
    assert prov["writer"] == "planner"
    assert prov["source"] == "user"
    assert prov["confidence"] == 0.8
    assert prov["namespace"] == "shared"
    assert prov["status"] == "active"
    assert prov["created_at"]  # timestamp always set
    assert prov["record_id"].startswith("mem-")


def test_id_is_content_addressed():
    ts = "2026-11-16T10:00:00+00:00"
    a = new_id("same text", "planner", ts)
    b = new_id("same text", "planner", ts)
    c = new_id("different text", "planner", ts)
    assert a == b
    assert a != c


def test_json_round_trip_keeps_provenance():
    rec = MemoryRecord(text="budget is $800", writer="researcher",
                       namespace="shared", source="tool:web",
                       confidence=0.6, tags=["budget"])
    restored = MemoryRecord.from_dict(rec.to_dict())
    assert restored == rec
    assert restored.tags == ["budget"]


def test_superseded_record_keeps_link():
    old = MemoryRecord(text="old", writer="a", namespace="shared", source="user")
    new = MemoryRecord(text="new", writer="a", namespace="shared", source="user",
                       supersedes=old.record_id)
    assert new.supersedes == old.record_id
    assert old.superseded_by is None  # store sets this on supersede


def test_audit_entry_defaults_timestamp():
    entry = AuditEntry(action="write", actor="planner")
    assert entry.created_at
    assert entry.to_dict()["action"] == "write"
