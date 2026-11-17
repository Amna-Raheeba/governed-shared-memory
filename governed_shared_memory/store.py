"""SQLite + JSON store.

SQLite is the durable store (one file, no server); JSON is the
portable export format — ``export_json`` / ``import_json`` round-trip
every record with its provenance intact, so a memory can move between
systems without losing who wrote it.

Tables
------
- ``memories``: one row per record, including status and supersession
  links. Superseded rows are never deleted.
- ``audit``: append-only log of writes, reads, supersessions, denials
  and conflicts. The audit table is the answer to "who changed what,
  when" — it is never truncated by this library.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .records import AuditEntry, MemoryRecord

_SCHEMA = """
CREATE TABLE IF NOT EXISTS memories (
    record_id TEXT PRIMARY KEY,
    text TEXT NOT NULL,
    writer TEXT NOT NULL,
    namespace TEXT NOT NULL,
    source TEXT NOT NULL,
    confidence REAL NOT NULL,
    created_at TEXT NOT NULL,
    status TEXT NOT NULL,
    superseded_by TEXT,
    supersedes TEXT,
    superseded_at TEXT,
    supersession_reason TEXT,
    tags TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    action TEXT NOT NULL,
    actor TEXT NOT NULL,
    record_id TEXT,
    namespace TEXT,
    detail TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_memories_ns ON memories(namespace, status);
CREATE INDEX IF NOT EXISTS idx_memories_writer ON memories(writer);
"""


class Store:
    """SQLite-backed memory store."""

    def __init__(self, path: str | Path = ":memory:") -> None:
        self.path = str(path)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(_SCHEMA)
        self._migrate()
        self.conn.commit()

    def _migrate(self) -> None:
        """Add columns a pre-0.2.0 database does not have yet.

        ``CREATE TABLE IF NOT EXISTS`` never alters an existing table,
        so a database file written by v0.1.0 keeps its old shape until
        this runs. Rows that predate the columns get NULL for
        ``superseded_at`` / ``supersession_reason`` — tombstones built
        from them report "age unknown" instead of a guessed date.
        """
        columns = {row[1] for row in
                   self.conn.execute("PRAGMA table_info(memories)")}
        for column, ddl in (("superseded_at", "TEXT"),
                            ("supersession_reason", "TEXT")):
            if column not in columns:
                self.conn.execute(
                    f"ALTER TABLE memories ADD COLUMN {column} {ddl}")

    def close(self) -> None:
        self.conn.close()

    # -- records ------------------------------------------------------
    def insert(self, record: MemoryRecord) -> MemoryRecord:
        # Named columns, not positional VALUES: after a migration the
        # physical column order of an old database differs from a
        # fresh one (ALTER TABLE appends at the end), and a positional
        # insert would silently write values into the wrong columns.
        self.conn.execute(
            "INSERT INTO memories (record_id, text, writer, namespace,"
            " source, confidence, created_at, status, superseded_by,"
            " supersedes, superseded_at, supersession_reason, tags)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (record.record_id, record.text, record.writer, record.namespace,
             record.source, record.confidence, record.created_at,
             record.status, record.superseded_by, record.supersedes,
             record.superseded_at, record.supersession_reason,
             json.dumps(record.tags)),
        )
        self.conn.commit()
        return record

    def update_status(self, record_id: str, status: str,
                      superseded_by: str | None,
                      superseded_at: str | None = None,
                      supersession_reason: str | None = None) -> None:
        """Mark a record superseded — and record when and why.

        ``superseded_at`` / ``supersession_reason`` are written only
        when given, so a plain status change never overwrites them
        with NULLs.
        """
        fields = ["status=?", "superseded_by=?"]
        params: list = [status, superseded_by]
        if superseded_at is not None:
            fields.append("superseded_at=?")
            params.append(superseded_at)
        if supersession_reason is not None:
            fields.append("supersession_reason=?")
            params.append(supersession_reason)
        params.append(record_id)
        self.conn.execute(
            f"UPDATE memories SET {', '.join(fields)} WHERE record_id=?",
            params,
        )
        self.conn.commit()

    def get(self, record_id: str) -> MemoryRecord | None:
        row = self.conn.execute(
            "SELECT * FROM memories WHERE record_id=?", (record_id,)
        ).fetchone()
        return _row_to_record(row) if row else None

    def list(self, namespace: str | None = None,
             status: str | None = "active") -> list[MemoryRecord]:
        sql = "SELECT * FROM memories"
        params: list = []
        clauses: list[str] = []
        if namespace is not None:
            clauses.append("namespace=?")
            params.append(namespace)
        if status is not None:
            clauses.append("status=?")
            params.append(status)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY created_at ASC, record_id ASC"
        return [
            _row_to_record(r)
            for r in self.conn.execute(sql, params).fetchall()
        ]

    def count(self, namespace: str | None = None) -> int:
        if namespace is None:
            row = self.conn.execute("SELECT COUNT(*) FROM memories").fetchone()
        else:
            row = self.conn.execute(
                "SELECT COUNT(*) FROM memories WHERE namespace=?",
                (namespace,),
            ).fetchone()
        return int(row[0])

    # -- audit --------------------------------------------------------
    def log(self, entry: AuditEntry) -> None:
        self.conn.execute(
            "INSERT INTO audit (action, actor, record_id, namespace, detail,"
            " created_at) VALUES (?,?,?,?,?,?)",
            (entry.action, entry.actor, entry.record_id, entry.namespace,
             entry.detail, entry.created_at),
        )
        self.conn.commit()

    def audit_log(self, limit: int = 200) -> list[AuditEntry]:
        rows = self.conn.execute(
            "SELECT * FROM audit ORDER BY id ASC LIMIT ?", (limit,)
        ).fetchall()
        return [
            AuditEntry(action=r["action"], actor=r["actor"],
                       record_id=r["record_id"], namespace=r["namespace"],
                       detail=r["detail"], created_at=r["created_at"])
            for r in rows
        ]

    # -- JSON export / import ----------------------------------------
    def export_json(self, path: str | Path) -> Path:
        data = {
            "records": [r.to_dict() for r in self.list(status=None)],
            "audit": [e.to_dict() for e in self.audit_log(limit=100000)],
        }
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return path

    @classmethod
    def import_json(cls, path: str | Path,
                    dest: str | Path = ":memory:") -> "Store":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        store = cls(dest)
        for raw in data.get("records", []):
            store.insert(MemoryRecord.from_dict(raw))
        for raw in data.get("audit", []):
            store.log(AuditEntry(**raw))
        return store


def _row_to_record(row: sqlite3.Row) -> MemoryRecord:
    keys = row.keys()
    return MemoryRecord(
        text=row["text"], writer=row["writer"], namespace=row["namespace"],
        source=row["source"], confidence=row["confidence"],
        created_at=row["created_at"], record_id=row["record_id"],
        status=row["status"], superseded_by=row["superseded_by"],
        supersedes=row["supersedes"],
        superseded_at=row["superseded_at"] if "superseded_at" in keys else None,
        supersession_reason=(row["supersession_reason"]
                             if "supersession_reason" in keys else None),
        tags=json.loads(row["tags"]),
    )
