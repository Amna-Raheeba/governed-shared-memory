"""Access control: per-agent namespaces and the governed shared space.

The model is deliberately small:

- Every agent owns a **private namespace** named after itself
  (``planner``, ``researcher``, ...). Only the owner and admins can
  read or write it. This is what stops *unauthorized leakage* — the
  first failure mode in Caura et al.: one agent cannot silently read
  another agent's private notes.
- The **shared namespace** (``"shared"``) is the governed space:
  any registered agent may read it, but writing requires the
  ``writer`` role, and superseding someone else's record requires
  the ``admin`` role (or being the original writer).
- Roles are ``reader`` < ``writer`` < ``admin``. An unknown agent
  gets nothing.

Every denied attempt is written to the audit log as a ``deny`` entry
— a leak that was *attempted* is itself evidence worth keeping.
"""
from __future__ import annotations

from dataclasses import dataclass

SHARED_NAMESPACE = "shared"

ROLE_RANK = {"reader": 1, "writer": 2, "admin": 3}


@dataclass(frozen=True)
class Agent:
    """A registered agent identity."""

    agent_id: str
    role: str = "writer"  # "reader" | "writer" | "admin"

    def __post_init__(self) -> None:
        if self.role not in ROLE_RANK:
            raise ValueError(f"unknown role: {self.role!r}")


class AccessDenied(PermissionError):
    """Raised (and audit-logged) when a governed action is refused."""


class AccessPolicy:
    """Who may read, write, and supersede where."""

    def __init__(self, agents: list[Agent] | None = None) -> None:
        self.agents: dict[str, Agent] = {a.agent_id: a for a in (agents or [])}

    def register(self, agent: Agent) -> None:
        self.agents[agent.agent_id] = agent

    def _agent(self, agent_id: str) -> Agent:
        agent = self.agents.get(agent_id)
        if agent is None:
            raise AccessDenied(f"unknown agent: {agent_id!r}")
        return agent

    def can_read(self, agent_id: str, namespace: str) -> bool:
        """Private namespaces: owner + admins only. Shared: any agent."""
        agent = self._agent(agent_id)
        if namespace == SHARED_NAMESPACE:
            return True
        if namespace == agent_id:
            return True
        return agent.role == "admin"

    def can_write(self, agent_id: str, namespace: str) -> bool:
        """Write own private namespace, or shared with writer+ role."""
        agent = self._agent(agent_id)
        if namespace == agent_id:
            return ROLE_RANK[agent.role] >= ROLE_RANK["writer"]
        if namespace == SHARED_NAMESPACE:
            return ROLE_RANK[agent.role] >= ROLE_RANK["writer"]
        return agent.role == "admin"

    def can_supersede(self, agent_id: str, namespace: str,
                      record_writer: str) -> bool:
        """Supersede your own record, or any record as admin."""
        agent = self._agent(agent_id)
        if agent.role == "admin":
            return True
        return agent_id == record_writer and self.can_write(agent_id, namespace)

    def check_read(self, agent_id: str, namespace: str) -> None:
        if not self.can_read(agent_id, namespace):
            raise AccessDenied(
                f"agent {agent_id!r} may not read namespace {namespace!r}"
            )

    def check_write(self, agent_id: str, namespace: str) -> None:
        if not self.can_write(agent_id, namespace):
            raise AccessDenied(
                f"agent {agent_id!r} may not write namespace {namespace!r}"
            )

    def check_supersede(self, agent_id: str, namespace: str,
                        record_writer: str) -> None:
        if not self.can_supersede(agent_id, namespace, record_writer):
            raise AccessDenied(
                f"agent {agent_id!r} may not supersede a record by "
                f"{record_writer!r} in namespace {namespace!r}"
            )
