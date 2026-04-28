"""Shared pytest fixtures for the studyAgent test suite."""
import pytest

from app.agent.node_registry import get_registry


@pytest.fixture(autouse=True)
def _restore_node_registry_after_test():
    """Snapshot the global NodeRegistry before each test, restore after.

    Tests sometimes decorate ad-hoc nodes (e.g., `@node(name="hello")`)
    which auto-register into the global singleton. Without restoration,
    those registrations leak across tests and a future test using an
    existing name with different metadata would raise ValueError during
    unrelated collection.
    """
    reg = get_registry()
    snapshot = dict(reg._nodes)  # shallow copy of internal mapping
    try:
        yield
    finally:
        reg._nodes.clear()
        reg._nodes.update(snapshot)
