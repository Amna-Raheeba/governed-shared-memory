"""Provenance-preserving tombstones with confidence decay (v0.2.0)."""
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from governed_shared_memory.access import AccessDenied, Agent
from governed_shared_memory.evaluation import evaluate_tombstones
from governed_shared_memory.memory import GovernedMemory
from governed_shared_memory.records import MemoryRecord
from governed_shared_memory.store import Store
from governed_shared_memory.tombstones import (
    DEFAULT_HALF_LIFE_SECONDS,
    Tombstone,
    decay_confidence,
    from_record,
)

BASE = datetime(2026, 11, 17, tzinfo=timezone.utc)


def _mem():
    mem = GovernedMemory()
    for agent in [Agent("planner", "writer"), Agent("researcher", "writer"),
                  Agent("reader", "reader"), Agent("admin", "admin")]:
        mem.register(agent)
    return mem


def _supersede(mem, text_old="budget is $500", text_new="budget is $800",
               reason="corrected by user", stamp=None, confidence=0.8):
    old, _ = mem.write("planner", text_old, "shared", "user",
                       confidence=confidence)
    new = mem.supersede("planner", old.record_id, text_new, "user",
                        reason=reason,
                        superseded_at=stamp or BASE.isoformat())
    return old, new


# -- decay curve ------------------------------------------------------

def test_decay_curve_exact_at_fixed_offsets():
    # Half-life 24h: 0.8 -> 0.8, 0.4, 0.2, 0.1 at 0/24/48/72 hours.
    for hours, expected in ((0, 0.8), (24, 0.4), (48, 0.2), (72, 0.1)):
        actual = decay_confidence(0.8, hours * 3600)
        assert actual == pytest.approx(expected, abs=1e-12)


def test_decay_is_deterministic_for_same_inputs():
    assert decay_confidence(0.9, 3600) == decay_confidence(0.9, 3600)
    assert decay_confidence(0.9, 3600, half_life_seconds=3600) == 0.45


def test_decay_half_life_parameter_respected():
    # Half-life 1h: after 1h the confidence halves, after 2h quarters.
    assert decay_confidence(1.0, 3600, half_life_seconds=3600) == 0.5
    assert decay_confidence(1.0, 7200, half_life_seconds=3600) == 0.25


def test_decay_zero_or_negative_age_returns_original():
    assert decay_confidence(0.7, 0) == 0.7
    assert decay_confidence(0.7, -100) == 0.7


def test_decay_rejects_bad_inputs():
    with pytest.raises(ValueError):
        decay_confidence(1.5, 100)
    with pytest.raises(ValueError):
        decay_confidence(0.5, 100, half_life_seconds=0)
    with pytest.raises(ValueError):
        decay_confidence(0.5, 100, half_life_seconds=-5)


# -- tombstone creation -------------------------------------------------

def test_supersede_records_reason_and_time():
    mem = _mem()
    old, new = _supersede(mem, stamp=BASE.isoformat())
    stored = mem.store.get(old.record_id)
    assert stored.status == "superseded"
    assert stored.superseded_by == new.record_id
    assert stored.superseded_at == BASE.isoformat()
    assert stored.supersession_reason == "corrected by user"
    assert stored.is_tombstone
    mem.close()


def test_supersede_without_reason_stores_none():
    mem = _mem()
    old, _ = mem.write("planner", "budget is $500", "shared", "user")
    mem.supersede("planner", old.record_id, "budget is $800", "user")
    stored = mem.store.get(old.record_id)
    assert stored.supersession_reason is None
    assert stored.superseded_at is not None  # defaults to now
    mem.close()


def test_supersede_audit_log_includes_reason():
    mem = _mem()
    old, _ = mem.write("planner", "budget is $500", "shared", "user")
    mem.supersede("planner", old.record_id, "budget is $800", "user",
                  reason="user confirmed the later figure")
    supersede_entries = [e for e in mem.audit_log() if e.action == "supersede"]
    assert len(supersede_entries) == 1
    assert "user confirmed the later figure" in supersede_entries[0].detail
    mem.close()


def test_from_record_rejects_live_record():
    record = MemoryRecord(text="budget is $800", writer="planner",
                          namespace="shared", source="user")
    with pytest.raises(ValueError):
        from_record(record)


def test_tombstone_fields_and_decay():
    mem = _mem()
    old, new = _supersede(mem, stamp=BASE.isoformat(), confidence=0.8)
    stone = mem.tombstones("admin", "shared")[0]
    assert isinstance(stone, Tombstone)
    assert stone.record_id == old.record_id
    assert stone.text == "budget is $500"
    assert stone.superseded_by == new.record_id
    assert stone.superseded_at == BASE.isoformat()
    assert stone.supersession_reason == "corrected by user"
    assert stone.original_confidence == 0.8
    # At supersession time: no decay yet. 24h later: halved.
    assert stone.decayed_confidence(BASE.isoformat()) == 0.8
    assert stone.decayed_confidence(
        (BASE + timedelta(hours=24)).isoformat()) == pytest.approx(0.4)
    # Age is unknown for pre-0.2.0 rows: no decay, original returned.
    legacy = Tombstone(record_id="mem-legacy", text="old fact",
                       writer="planner", namespace="shared", source="user",
                       original_confidence=0.8, superseded_by="mem-new",
                       superseded_at=None, supersession_reason=None,
                       created_at=BASE.isoformat())
    assert legacy.age_seconds() is None
    assert legacy.decayed_confidence() == 0.8
    mem.close()


def test_tombstone_to_dict_round_trips():
    mem = _mem()
    _supersede(mem, stamp=BASE.isoformat())
    stone = mem.tombstones("admin", "shared")[0]
    data = stone.to_dict(at=(BASE + timedelta(hours=48)).isoformat())
    assert data["decayed_confidence"] == pytest.approx(0.2)
    assert data["age_seconds"] == 48 * 3600
    assert data["supersession_reason"] == "corrected by user"
    mem.close()


# -- history and listing -----------------------------------------------

def test_tombstone_history_returns_chain_oldest_first():
    mem = _mem()
    first, _ = mem.write("planner", "budget is $500", "shared", "user",
                         confidence=0.8)
    second = mem.supersede("planner", first.record_id, "budget is $800",
                           "user", reason="first correction",
                           superseded_at=BASE.isoformat())
    third = mem.supersede("planner", second.record_id, "budget is $1200",
                          "user", reason="second correction",
                          superseded_at=(BASE + timedelta(hours=1)).isoformat())
    chain = mem.tombstone_history("admin", third.record_id)
    assert [t.record_id for t in chain] == [first.record_id,
                                            second.record_id]
    assert [t.supersession_reason for t in chain] == [
        "first correction", "second correction"]
    assert [t.superseded_by for t in chain] == [second.record_id,
                                                 third.record_id]
    # The live head is not a tombstone.
    assert third.record_id not in [t.record_id for t in chain]
    mem.close()


def test_tombstones_listed_newest_superseded_first():
    mem = _mem()
    _supersede(mem, text_old="budget is $500", text_new="budget is $800",
               reason="first", stamp=BASE.isoformat())
    _supersede(mem, text_old="deadline is 12 January",
               text_new="deadline is 20 January", reason="second",
               stamp=(BASE + timedelta(hours=5)).isoformat())
    stones = mem.tombstones("admin", "shared")
    assert len(stones) == 2
    assert stones[0].supersession_reason == "second"
    assert stones[1].supersession_reason == "first"
    mem.close()


def test_tombstones_respect_private_namespace_access():
    mem = _mem()
    old, _ = mem.write("planner", "private draft figures", "planner", "user")
    mem.supersede("planner", old.record_id, "private final figures", "user",
                  reason="draft finalised")
    with pytest.raises(AccessDenied):
        mem.tombstones("researcher", "planner")
    assert len(mem.tombstones("planner", "planner")) == 1
    assert len(mem.tombstones("admin", "planner")) == 1
    mem.close()


# -- live queries never return tombstones -------------------------------

def test_live_queries_exclude_tombstones():
    mem = _mem()
    old, _ = _supersede(mem)
    assert old.record_id not in {
        r.record_id for r in mem.list_active("admin", "shared")}
    hits = mem.search("admin", "budget is $500", "shared", top_k=10)
    assert all(r.record_id != old.record_id for r, _ in hits)
    assert all("800" in r.text for r, _ in hits)
    # ... but the tombstone is still retrievable as history.
    assert mem.tombstones("admin", "shared")[0].record_id == old.record_id
    mem.close()


# -- persistence ---------------------------------------------------------

def test_json_round_trip_preserves_tombstone_fields(tmp_path):
    mem = _mem()
    old, _ = _supersede(mem, stamp=BASE.isoformat())
    path = tmp_path / "export.json"
    mem.export_json(path)
    data = json.loads(path.read_text())
    row = next(r for r in data["records"]
               if r["record_id"] == old.record_id)
    assert row["superseded_at"] == BASE.isoformat()
    assert row["supersession_reason"] == "corrected by user"
    restored = GovernedMemory.import_json(path, agents=[
        Agent("planner", "writer"), Agent("admin", "admin")])
    stone = restored.tombstones("admin", "shared")[0]
    assert stone.supersession_reason == "corrected by user"
    assert stone.decayed_confidence(
        (BASE + timedelta(hours=24)).isoformat()) == pytest.approx(0.4)
    mem.close()
    restored.close()


def test_sqlite_persistence_and_old_schema_migration(tmp_path):
    # A v0.1.0 database: the old 11-column schema, no tombstone columns.
    db = tmp_path / "old.db"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE memories (record_id TEXT PRIMARY KEY, text TEXT,"
        " writer TEXT, namespace TEXT, source TEXT, confidence REAL,"
        " created_at TEXT, status TEXT, superseded_by TEXT,"
        " supersedes TEXT, tags TEXT)")
    conn.execute(
        "CREATE TABLE audit (id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " action TEXT, actor TEXT, record_id TEXT, namespace TEXT,"
        " detail TEXT, created_at TEXT)")
    conn.commit()
    conn.close()
    mem = GovernedMemory(db, [Agent("planner", "writer"),
                              Agent("admin", "admin")])
    old, _ = mem.write("planner", "budget is $500", "shared", "user")
    mem.supersede("planner", old.record_id, "budget is $800", "user",
                  reason="migrated db still records reasons")
    stone = mem.tombstones("admin", "shared")[0]
    assert stone.supersession_reason == "migrated db still records reasons"
    assert stone.superseded_at is not None
    mem.close()


# -- seeded evaluation ---------------------------------------------------

def test_seeded_tombstone_evaluation_is_perfect():
    report = evaluate_tombstones(n_seeded=12)
    summary = report.summary()
    assert summary["tombstone_recall"] == 1.0
    assert summary["decay_exact_rate"] == 1.0
    assert summary["live_exclusion_rate"] == 1.0
    assert summary["decay_checks"] == 12 * 4  # 0/24/48/72h per record
    assert summary["live_exclusion_checks"] == 12 * 2  # list + search
