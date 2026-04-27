"""Verify Phase 2 nodes are reachable from the qa_direct intent."""
from unittest.mock import patch

from app.agent.graph_v2 import build_learning_graph_v2


def _state(**overrides):
    base = {
        "session_id": "wiring-test",
        "user_input": "请介绍数据库索引的平衡多路搜索树",
        "topic": "数据结构",
        "intent": "qa_direct",
        "branch_trace": [],
    }
    base.update(overrides)
    return base


def _patch_intent_qa_direct(monkeypatch):
    """Force intent_router to return qa_direct."""
    monkeypatch.setattr(
        "app.services.llm.llm_service.route_intent",
        lambda x: '{"intent":"qa_direct","confidence":0.95,"reason":"qa"}',
    )
    monkeypatch.setattr(
        "app.services.llm.llm_service.invoke",
        lambda **kw: "B+树是一种平衡多路搜索树。",
    )


def test_qa_direct_reaches_evidence_gate_and_answer_policy(monkeypatch):
    """Happy path: rag finds evidence, gate passes, answer_policy runs."""
    _patch_intent_qa_direct(monkeypatch)
    fake_rows = [
        {"chunk_id": "c1", "score": 0.9, "text": "B+树是平衡多路搜索树", "source": "textbook"},
        {"chunk_id": "c2", "score": 0.85, "text": "B+树常用于数据库索引", "source": "textbook"},
    ]
    with patch(
        "app.services.rag_coordinator.execute_retrieval_tools",
        return_value=(fake_rows, ["search_local_textbook"]),
    ):
        graph = build_learning_graph_v2()
        result = graph.invoke(
            _state(), config={"configurable": {"thread_id": "wiring-t1"}}
        )

    # If wiring is correct, answer_template_id must be populated by answer_policy_node
    assert result.get("answer_template_id"), (
        "answer_policy node was not visited"
    )


def test_qa_direct_reaches_recovery_when_gate_rejects(monkeypatch):
    """Empty retrieval → gate rejects → recovery fires."""
    _patch_intent_qa_direct(monkeypatch)
    with patch(
        "app.services.rag_coordinator.execute_retrieval_tools",
        return_value=([], []),
    ):
        graph = build_learning_graph_v2()
        result = graph.invoke(
            _state(), config={"configurable": {"thread_id": "wiring-t2"}}
        )

    # recovery_node sets fallback_triggered or recovery_action
    assert result.get("recovery_action") or result.get("fallback_triggered"), (
        "recovery node was not visited despite empty retrieval"
    )
