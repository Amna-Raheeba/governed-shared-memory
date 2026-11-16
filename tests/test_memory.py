"""GovernedMemory: the four guarantees, end to end."""
import json
from pathlib import Path

import pytest

from governed_shared_memory.access import AccessDenied, Agent
from governed_shared_memory.memory import GovernedMemory


def _mem():
    mem = GovernedMemory()
    for agent in [Agent("planner", "writer"), Agent("researcher", "writer"),
                  Agent("reader", "reader"), Agent("admin", "admin")]:
        mem.register(agent)
    return mem


def test_write_returns_record_with_provenance():
    mem = _mem()
    record, conflicts = mem.write("planner", "deadline is 12 January",
                                  "shared", "user")
    assert record.writer == "planner"
    assert record.namespace == "shared"
    assert record.status == "active"
    assert conflicts == []
    mem.close()


def test_write_flags_conflict_but_still_stores():
    mem = _mem()
    mem.write("planner", "project deadline is 12 January", "shared", "user")
    record, conflicts = mem.write("researcher",
                                  "project deadline is 20 January",
                                  "shared", "user")
    assert len(conflicts) == 1
    assert conflicts[0].kind == "slot"
    assert mem.store.get(record.record_id) is not None
    mem.close()


def test_private_read_by_other_agent_denied_and_logged():
    mem = _mem()
    mem.write("planner", "private draft figures", "planner", "user")
    with pytest.raises(AccessDenied):
        mem.list_active("researcher", "planner")
    denies = [e for e in mem.audit_log() if e.action == "deny"]
    assert len(denies) == 1
    assert denies[0].actor == "researcher"
    mem.close()


def test_reader_cannot_write():
    mem = _mem()
    with pytest.raises(AccessDenied):
        mem.write("reader", "sneaky note", "shared", "user")
    mem.close()


def test_search_returns_active_only():
    mem = _mem()
    old, _ = mem.write("planner", "project deadline is 12 January",
                       "shared", "user")
    mem.supersede("planner", old.record_id,
                  "project deadline is 20 January", "user")
    results = mem.search("admin", "project deadline", "shared")
    assert len(results) == 1
    assert "20 January" in results[0][0].text
    mem.close()


def test_supersede_marks_old_and_links_new():
    mem = _mem()
    old, _ = mem.write("planner", "budget is $500", "shared", "user")
    new = mem.supersede("planner", old.record_id, "budget is $800", "user")
    assert new.supersedes == old.record_id
    stored_old = mem.store.get(old.record_id)
    assert stored_old.status == "superseded"
    assert stored_old.superseded_by == new.record_id
    mem.close()


def test_supersede_others_record_denied_for_writer():
    mem = _mem()
    old, _ = mem.write("planner", "budget is $500", "shared", "user")
    with pytest.raises(AccessDenied):
        mem.supersede("researcher", old.record_id, "budget is $800", "user")
    mem.close()


def test_supersede_others_record_allowed_for_admin():
    mem = _mem()
    old, _ = mem.write("planner", "budget is $500", "shared", "user")
    new = mem.supersede("admin", old.record_id, "budget is $800", "user")
    assert new.supersedes == old.record_id
    mem.close()


def test_history_follows_supersession_chain():
    mem = _mem()
    first, _ = mem.write("planner", "budget is $500", "shared", "user")
    second = mem.supersede("planner", first.record_id, "budget is $800", "user")
    third = mem.supersede("planner", second.record_id, "budget is $1200", "user")
    chain = mem.history("admin", third.record_id)
    assert [r.record_id for r in chain] == [
        third.record_id, second.record_id, first.record_id,
    ]
    mem.close()


def test_open_conflicts_lists_unresolved():
    mem = _mem()
    mem.write("planner", "project deadline is 12 January", "shared", "user")
    mem.write("researcher", "project deadline is 20 January", "shared", "user")
    conflicts = mem.open_conflicts("admin", "shared")
    assert len(conflicts) == 1
    mem.close()


def test_conflict_resolved_by_supersession():
    mem = _mem()
    old, _ = mem.write("planner", "project deadline is 12 January",
                       "shared", "user")
    mem.write("researcher", "project deadline is 20 January", "shared", "user")
    assert len(mem.open_conflicts("admin", "shared")) == 1
    mem.supersede("planner", old.record_id,
                  "project deadline is 20 January", "user")
    assert mem.open_conflicts("admin", "shared") == []
    mem.close()


def test_search_tie_breaks_toward_newest_record():
    mem = _mem()
    mem.write("planner", "project deadline is 12 January", "shared", "user")
    mem.write("researcher", "project deadline is 20 January", "shared",
              "user")
    results = mem.search("admin", "project deadline", "shared")
    assert "20 January" in results[0][0].text
    mem.close()


def test_read_unknown_record_raises_key_error():
    mem = _mem()
    with pytest.raises(KeyError):
        mem.read("admin", "mem-doesnotexist")
    mem.close()


def test_json_export_import_round_trip(tmp_path):
    mem = _mem()
    record, _ = mem.write("planner", "budget is $800", "shared", "user",
                          confidence=0.7)
    path = tmp_path / "export.json"
    mem.export_json(path)
    data = json.loads(path.read_text())
    assert data["records"][0]["record_id"] == record.record_id
    assert data["records"][0]["confidence"] == 0.7
    restored = GovernedMemory.import_json(path, agents=[
        Agent("planner", "writer"), Agent("admin", "admin")])
    fetched = restored.read("admin", record.record_id)
    assert fetched.text == "budget is $800"
    assert fetched.writer == "planner"
    mem.close()
    restored.close()


def test_audit_log_records_writes_and_supersedes():
    mem = _mem()
    old, _ = mem.write("planner", "budget is $500", "shared", "user")
    mem.supersede("planner", old.record_id, "budget is $800", "user")
    actions = [e.action for e in mem.audit_log()]
    assert actions.count("write") == 1
    assert actions.count("supersede") == 1
    mem.close()


def test_sqlite_persistence_across_reopen(tmp_path):
    db = tmp_path / "mem.db"
    mem = GovernedMemory(db, [Agent("planner", "writer")])
    mem.write("planner", "persistent fact", "shared", "user")
    mem.close()
    reopened = GovernedMemory(db, [Agent("planner", "writer"),
                                   Agent("admin", "admin")])
    results = reopened.search("admin", "persistent fact", "shared")
    assert len(results) == 1
    reopened.close()
