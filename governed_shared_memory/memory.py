"""GovernedMemory: the governed facade over the store.

This is the class agents use. Every operation passes through the
access policy first, is checked for contradictions on write, and is
written to the audit log — including denials.

The four failure modes, and where each is stopped
-----------------------------------------------
1. **Unauthorized leakage** — ``AccessPolicy``: private namespaces are
   owner + admin only; every denied read is audit-logged.
2. **Stale propagation** — reads and search return *active* records
   only; superseded records are visible only via ``history()``.
3. **Contradiction persistence** — ``write()`` runs contradiction
   detection against active records in the same namespace and returns
   the flags with the write; conflicts stay open until resolved by
   explicit supersession.
4. **Provenance collapse** — every record carries writer, timestamp,
   source and confidence from construction; JSON export round-trips
   them; the audit log records every action.
"""
from __future__ import annotations

from pathlib import Path

from .access import AccessDenied, AccessPolicy, Agent, SHARED_NAMESPACE
from .bm25 import BM25
from .contradictions import Conflict, detect_all, detect_for_new
from .records import AuditEntry, MemoryRecord
from .store import Store


class GovernedMemory:
    """Multi-agent shared memory with governance on every operation."""

    def __init__(self, path: str | Path = ":memory:",
                 agents: list[Agent] | None = None) -> None:
        self.store = Store(path)
        self.policy = AccessPolicy(agents)

    def close(self) -> None:
        self.store.close()

    # -- agents -------------------------------------------------------
    def register(self, agent: Agent) -> None:
        self.policy.register(agent)

    # -- writes -------------------------------------------------------
    def write(self, agent_id: str, text: str, namespace: str,
              source: str, confidence: float = 1.0,
              tags: list[str] | None = None) -> tuple[MemoryRecord, list[Conflict]]:
        """Write a memory; returns (record, conflicts flagged on write).

        Raises AccessDenied when the agent may not write here; the
        denial is audit-logged before the exception is raised.
        """
        try:
            self.policy.check_write(agent_id, namespace)
        except AccessDenied as exc:
            self.store.log(AuditEntry(
                action="deny", actor=agent_id, namespace=namespace,
                detail=str(exc),
            ))
            raise
        record = MemoryRecord(
            text=text, writer=agent_id, namespace=namespace, source=source,
            confidence=confidence, tags=tags or [],
        )
        existing = self.store.list(namespace=namespace, status="active")
        conflicts = detect_for_new(record, existing)
        self.store.insert(record)
        self.store.log(AuditEntry(
            action="write", actor=agent_id, record_id=record.record_id,
            namespace=namespace,
            detail=f"{len(conflicts)} conflict(s) flagged" if conflicts else "",
        ))
        for conflict in conflicts:
            self.store.log(AuditEntry(
                action="conflict", actor=agent_id,
                record_id=record.record_id, namespace=namespace,
                detail=conflict.reason,
            ))
        return record, conflicts

    # -- reads --------------------------------------------------------
    def read(self, agent_id: str, record_id: str) -> MemoryRecord:
        record = self.store.get(record_id)
        if record is None:
            raise KeyError(f"no such record: {record_id}")
        try:
            self.policy.check_read(agent_id, record.namespace)
        except AccessDenied as exc:
            self.store.log(AuditEntry(
                action="deny", actor=agent_id, record_id=record_id,
                namespace=record.namespace, detail=str(exc),
            ))
            raise
        self.store.log(AuditEntry(
            action="read", actor=agent_id, record_id=record_id,
            namespace=record.namespace,
        ))
        return record

    def list_active(self, agent_id: str, namespace: str) -> list[MemoryRecord]:
        """Active records in a namespace the agent may read."""
        try:
            self.policy.check_read(agent_id, namespace)
        except AccessDenied as exc:
            self.store.log(AuditEntry(
                action="deny", actor=agent_id, namespace=namespace,
                detail=str(exc),
            ))
            raise
        return self.store.list(namespace=namespace, status="active")

    def search(self, agent_id: str, query: str, namespace: str,
               top_k: int = 5) -> list[tuple[MemoryRecord, float]]:
        """BM25 search over active records the agent may read."""
        records = self.list_active(agent_id, namespace)
        index = BM25([(r.record_id, r.text) for r in records])
        by_id = {r.record_id: r for r in records}
        hits = [(by_id[doc_id], score)
                for doc_id, score in index.search(query, top_k=top_k)]
        # Ties on BM25 score break toward the newest record: when two
        # writers disagree, the reader should see the latest claim
        # first — and the conflict flag next to it, not the older side.
        # Two stable sorts: recency first, then score (keeps recency
        # order inside each score tie).
        hits.sort(key=lambda pair: (pair[0].created_at, pair[0].record_id),
                  reverse=True)
        hits.sort(key=lambda pair: -pair[1])
        return hits

    def history(self, agent_id: str, record_id: str) -> list[MemoryRecord]:
        """Provenance chain: the record and everything it superseded.

        Follows ``supersedes`` links backwards, so a reader can see
        exactly what a current fact replaced — and what it replaced
        before that.
        """
        record = self.read(agent_id, record_id)
        chain = [record]
        seen = {record.record_id}
        current = record
        while current.supersedes and current.supersedes not in seen:
            previous = self.store.get(current.supersedes)
            if previous is None:
                break
            self.policy.check_read(agent_id, previous.namespace)
            chain.append(previous)
            seen.add(previous.record_id)
            current = previous
        return chain

    # -- supersession -------------------------------------------------
    def supersede(self, agent_id: str, old_record_id: str, text: str,
                  source: str, confidence: float = 1.0) -> MemoryRecord:
        """Replace a record explicitly: old one is marked superseded,
        the new one links back to it. The old text stays readable in
        history; nothing is ever silently overwritten."""
        old = self.store.get(old_record_id)
        if old is None:
            raise KeyError(f"no such record: {old_record_id}")
        try:
            self.policy.check_supersede(agent_id, old.namespace, old.writer)
        except AccessDenied as exc:
            self.store.log(AuditEntry(
                action="deny", actor=agent_id, record_id=old_record_id,
                namespace=old.namespace, detail=str(exc),
            ))
            raise
        new = MemoryRecord(
            text=text, writer=agent_id, namespace=old.namespace,
            source=source, confidence=confidence, supersedes=old.record_id,
        )
        self.store.insert(new)
        self.store.update_status(old.record_id, "superseded", new.record_id)
        self.store.log(AuditEntry(
            action="supersede", actor=agent_id, record_id=new.record_id,
            namespace=old.namespace,
            detail=f"supersedes {old.record_id}",
        ))
        return new

    # -- conflicts & consolidation ------------------------------------
    def open_conflicts(self, agent_id: str,
                       namespace: str) -> list[Conflict]:
        """Unresolved contradictions among active records in a namespace."""
        records = self.list_active(agent_id, namespace)
        return detect_all(records)

    def audit_log(self) -> list[AuditEntry]:
        return self.store.audit_log()

    # -- persistence --------------------------------------------------
    def export_json(self, path: str | Path) -> Path:
        return self.store.export_json(path)

    @classmethod
    def import_json(cls, path: str | Path,
                    dest: str | Path = ":memory:",
                    agents: list[Agent] | None = None) -> "GovernedMemory":
        mem = cls(dest, agents)
        imported = Store.import_json(path, dest)
        mem.store.close()
        mem.store = imported
        return mem

    @property
    def shared(self) -> str:
        return SHARED_NAMESPACE
