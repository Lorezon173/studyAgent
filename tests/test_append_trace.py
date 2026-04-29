"""验证 _append_trace 消费 NodeMeta 的 trace_label 与 sensitive 字段。"""

from app.agent.node_decorator import node
from app.agent.nodes import register_all_nodes
from app.agent.nodes._shared import _append_trace


def test_unknown_phase_preserves_legacy_behavior():
    state = {}
    _append_trace(state, "rag_first_error", {"error_type": "timeout"})
    assert len(state["branch_trace"]) == 1
    entry = state["branch_trace"][0]
    assert entry["phase"] == "rag_first_error"
    assert entry["error_type"] == "timeout"
    assert "timestamp" in entry


def test_known_phase_uses_trace_label():
    register_all_nodes()
    state = {}
    _append_trace(state, "rag_first", {"rag_found": True})
    entry = state["branch_trace"][0]
    assert entry["phase"] == "RAG First"
    assert entry["rag_found"] is True


def test_known_phase_without_label_falls_back_to_name():
    @node(name="phase_no_label", trace_label="")
    def n(state):
        return state

    state = {}
    _append_trace(state, "phase_no_label", {"foo": 1})
    entry = state["branch_trace"][0]
    assert entry["phase"] == "phase_no_label"
    assert entry["foo"] == 1


def test_sensitive_phase_redacts_known_secret_keys():
    @node(name="auth_x", sensitive=True, trace_label="Auth X")
    def auth_node(state):
        return state

    state = {}
    _append_trace(
        state,
        "auth_x",
        {"user_id": 42, "api_key": "sk-leak", "password": "p@ss", "ok": True},
    )
    entry = state["branch_trace"][0]
    assert entry["phase"] == "Auth X"
    assert entry["user_id"] == 42
    assert entry["ok"] is True
    assert "api_key" not in entry
    assert "password" not in entry


def test_sensitive_error_phase_redacts_known_secret_keys():
    @node(name="auth_err", sensitive=True, trace_label="Auth Err")
    def auth_error_node(state):
        return state

    state = {}
    _append_trace(
        state,
        "auth_err_error",
        {"api_key": "sk-leak", "password": "p@ss", "ok": True},
    )
    entry = state["branch_trace"][0]
    assert entry["phase"] == "auth_err_error"
    assert entry["ok"] is True
    assert "api_key" not in entry
    assert "password" not in entry


def test_non_sensitive_phase_passes_payload_through():
    register_all_nodes()
    state = {}
    _append_trace(
        state,
        "rag_first",
        {"rag_found": True, "api_key": "sk-NOT-actually-secret"},
    )
    entry = state["branch_trace"][0]
    assert entry["api_key"] == "sk-NOT-actually-secret"


def test_multiple_calls_accumulate_in_branch_trace():
    register_all_nodes()
    state = {}
    _append_trace(state, "rag_first", {"step": 1})
    _append_trace(state, "evidence_gate", {"step": 2})
    assert [e["phase"] for e in state["branch_trace"]] == ["RAG First", "Evidence Gate"]
