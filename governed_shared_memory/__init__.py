"""Governed shared memory for multi-agent LLM systems.

A stdlib-only, offline library: per-agent private namespaces plus one
governed shared space, access-control rules per writer, contradiction
detection on write, provenance on every memory, and explicit
supersession — so shared memory can be trusted instead of silently
overwritten, leaked, or left stale.
"""

from .access import AccessDenied, AccessPolicy, Agent, SHARED_NAMESPACE
from .consolidation import ConsolidatedView, consolidate
from .contradictions import Conflict, detect_all, detect_for_new, detect_pair
from .memory import GovernedMemory
from .records import AuditEntry, MemoryRecord
from .store import Store

__version__ = "0.1.0"

__all__ = [
    "AccessDenied",
    "AccessPolicy",
    "Agent",
    "AuditEntry",
    "Conflict",
    "ConsolidatedView",
    "GovernedMemory",
    "MemoryRecord",
    "SHARED_NAMESPACE",
    "Store",
    "consolidate",
    "detect_all",
    "detect_for_new",
    "detect_pair",
]
