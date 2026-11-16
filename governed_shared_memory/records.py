"""Memory records and provenance.

Every memory is a record with provenance attached at birth — it can
never exist without saying who wrote it, when, from what source, and
how confident that writer was. This is the load-bearing design choice:
provenance collapse (the fourth failure mode in Caura et al.) is
impossible by construction, because the fields are required, not
optional metadata a caller may forget.

A record is *active* until it is superseded. Supersession is explicit:
``superseded_by`` names the record that replaces it, and the old record
stays readable in history — it is never deleted or silently edited.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone


def new_id(text: str, writer: str, created_at: str) -> str:
    """Stable, content-addressed id: same writer + text + time = same id."""
    digest = hashlib.sha256(
        f"{writer}\0{created_at}\0{text}".encode("utf-8")
    ).hexdigest()
    return f"mem-{digest[:12]}"


@dataclass
class MemoryRecord:
    """One governed memory."""

    text: str
    writer: str  # agent id that wrote it, e.g. "planner"
    namespace: str  # "planner" (private) or "shared" (governed space)
    source: str  # where the writer got it: "user", "tool:web", "agent:critic", ...
    confidence: float = 1.0  # writer's self-reported confidence, 0..1
    created_at: str = ""  # ISO 8601 UTC; set by the store if empty
    record_id: str = ""
    status: str = "active"  # "active" | "superseded"
    superseded_by: str | None = None  # record_id of the replacement
    supersedes: str | None = None  # record_id this record replaces
    tags: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise ValueError("memory text must not be empty")
        if not self.writer.strip():
            raise ValueError("writer must not be empty")
        if not self.namespace.strip():
            raise ValueError("namespace must not be empty")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be in [0, 1]")
        if self.status not in ("active", "superseded"):
            raise ValueError(f"unknown status: {self.status!r}")
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()
        if not self.record_id:
            self.record_id = new_id(self.text, self.writer, self.created_at)

    def provenance(self) -> dict:
        """The provenance block: who, when, from where, how sure."""
        return {
            "record_id": self.record_id,
            "writer": self.writer,
            "created_at": self.created_at,
            "source": self.source,
            "confidence": self.confidence,
            "namespace": self.namespace,
            "status": self.status,
            "superseded_by": self.superseded_by,
            "supersedes": self.supersedes,
        }

    def to_dict(self) -> dict:
        return {
            **self.provenance(),
            "text": self.text,
            "tags": list(self.tags),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "MemoryRecord":
        return cls(
            text=data["text"],
            writer=data["writer"],
            namespace=data["namespace"],
            source=data["source"],
            confidence=data.get("confidence", 1.0),
            created_at=data.get("created_at", ""),
            record_id=data.get("record_id", ""),
            status=data.get("status", "active"),
            superseded_by=data.get("superseded_by"),
            supersedes=data.get("supersedes"),
            tags=list(data.get("tags", [])),
        )

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True)


@dataclass
class AuditEntry:
    """One append-only audit-log line: every governed action is recorded."""

    action: str  # "write" | "read" | "supersede" | "deny" | "conflict"
    actor: str
    record_id: str | None = None
    namespace: str | None = None
    detail: str = ""
    created_at: str = ""

    def __post_init__(self) -> None:
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return {
            "action": self.action,
            "actor": self.actor,
            "record_id": self.record_id,
            "namespace": self.namespace,
            "detail": self.detail,
            "created_at": self.created_at,
        }
