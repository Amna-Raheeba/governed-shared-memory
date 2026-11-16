"""Access control: private namespaces stay private."""
import pytest

from governed_shared_memory.access import (
    AccessDenied, AccessPolicy, Agent,
)


def _policy():
    return AccessPolicy([
        Agent("planner", "writer"),
        Agent("researcher", "reader"),
        Agent("admin", "admin"),
    ])


def test_unknown_role_rejected():
    with pytest.raises(ValueError):
        Agent("x", "superuser")


def test_unknown_agent_denied_everything():
    policy = _policy()
    with pytest.raises(AccessDenied):
        policy.check_read("ghost", "shared")


def test_shared_is_readable_by_any_agent():
    policy = _policy()
    assert policy.can_read("researcher", "shared")
    assert policy.can_read("planner", "shared")


def test_private_namespace_owner_only():
    policy = _policy()
    assert policy.can_read("planner", "planner")
    assert not policy.can_read("researcher", "planner")


def test_admin_can_read_any_namespace():
    policy = _policy()
    assert policy.can_read("admin", "planner")
    assert policy.can_read("admin", "researcher")


def test_reader_cannot_write_shared():
    policy = _policy()
    assert not policy.can_write("researcher", "shared")
    with pytest.raises(AccessDenied):
        policy.check_write("researcher", "shared")


def test_writer_can_write_shared_and_own_namespace():
    policy = _policy()
    assert policy.can_write("planner", "shared")
    assert policy.can_write("planner", "planner")


def test_writer_cannot_write_others_private_namespace():
    policy = _policy()
    assert not policy.can_write("planner", "researcher")


def test_supersede_own_record_allowed():
    policy = _policy()
    assert policy.can_supersede("planner", "shared", "planner")


def test_supersede_others_record_needs_admin():
    policy = _policy()
    assert not policy.can_supersede("planner", "shared", "researcher")
    assert policy.can_supersede("admin", "shared", "researcher")


def test_register_adds_agent():
    policy = AccessPolicy()
    policy.register(Agent("critic", "writer"))
    assert policy.can_write("critic", "shared")
