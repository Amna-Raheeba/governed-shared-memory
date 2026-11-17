"""Governed shared memory for multi-agent LLM systems.

A stdlib-only, offline library: per-agent private namespaces plus one
governed shared space, access-control rules per writer, contradiction
detection on write, provenance on every memory, and explicit
supersession — so shared memory can be trusted instead of silently
overwritten, leaked, or left stale. Superseded records survive as
provenance-preserving tombstones with deterministically decaying
confidence, so the team can always ask what it used to believe, when
it changed, and why.
"""

from .access import AccessDenied, AccessPolicy, Agent, SHARED_NAMESPACE
from .consolidation import ConsolidatedView, consolidate
from .contradictions import Conflict, detect_all, detect_for_new, detect_pair
from .memory import GovernedMemory
from .records import AuditEntry, MemoryRecord
from .store import Store
from .tombstones import (
    DEFAULT_HALF_LIFE_SECONDS,
    Tombstone,
    decay_confidence,
    from_record,
)

__version__ = "0.2.0"

__all__ = [
    "AccessDenied",
    "AccessPolicy",
    "Agent",
    "AuditEntry",
    "Conflict",
    "ConsolidatedView",
    "DEFAULT_HALF_LIFE_SECONDS",
    "GovernedMemory",
    "MemoryRecord",
    "SHARED_NAMESPACE",
    "Store",
    "Tombstone",
    "consolidate",
    "decay_confidence",
    "detect_all",
    "detect_for_new",
    "detect_pair",
    "from_record",
]
