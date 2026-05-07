"""Shared pytest fixtures for the studyAgent test suite."""
import pytest
from langgraph.checkpoint.memory import MemorySaver

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


@pytest.fixture(autouse=True, scope="session")
def force_graph_v2_session():
    """全局强制使用 Graph V2。"""
    from app.core import config
    original = getattr(config.settings, "use_graph_v2", False)
    config.settings.use_graph_v2 = True
    yield
    config.settings.use_graph_v2 = original


@pytest.fixture
def fresh_checkpointer():
    """每次测试使用新的 MemorySaver checkpointer。"""
    import app.agent.checkpointer as cp_module

    original = cp_module._checkpointer
    cp_module._checkpointer = MemorySaver()

    yield cp_module._checkpointer

    cp_module._checkpointer = original
    import app.agent.graph_v2 as graph_module
    graph_module._learning_graph_v2 = None


@pytest.fixture
def clear_all_state():
    """清除所有状态（session store + checkpointer）。"""
    from app.services.session_store import clear_all_sessions
    clear_all_sessions()
    yield
    clear_all_sessions()
