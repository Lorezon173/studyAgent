"""Phase 6 端到端：图运行后 branch_trace 包含可读的 trace_label。"""

from unittest.mock import patch

from app.agent.graph_v2 import build_learning_graph_v2


def test_qa_direct_run_emits_human_readable_trace_labels():
    fake_rows = [
        {"chunk_id": f"c{i}", "score": 0.9 - i * 0.1, "text": f"什么是数据库索引：数据库索引内容 {i}"}
        for i in range(3)
    ]
    with (
        patch(
            "app.services.rag_coordinator.execute_retrieval_tools",
            return_value=(fake_rows, ["search_local_textbook"]),
        ),
        patch("app.services.llm.llm_service.route_intent", return_value='{"intent":"qa_direct"}'),
        patch("app.services.llm.llm_service.invoke", return_value="answer"),
    ):
        graph = build_learning_graph_v2()
        result = graph.invoke(
            {"session_id": "p6-1", "user_input": "请介绍数据库索引", "topic": "数据结构", "intent": "qa_direct"},
            config={"configurable": {"thread_id": "p6-1"}},
        )
    labels = [e["phase"] for e in result.get("branch_trace", [])]
    assert "RAG First" in labels
    assert "rag_first" not in labels


def test_error_phase_preserves_legacy_string():
    call_count = {"n": 0}

    def flaky(*a, **kw):
        call_count["n"] += 1
        raise TimeoutError("timed out")

    with (
        patch("app.services.rag_coordinator.execute_retrieval_tools", side_effect=flaky),
        patch("app.services.llm.llm_service.route_intent", return_value='{"intent":"qa_direct"}'),
        patch("app.services.llm.llm_service.invoke", return_value="stub"),
    ):
        graph = build_learning_graph_v2()
        result = graph.invoke(
            {"session_id": "p6-2", "user_input": "什么是B+树", "topic": "数据结构", "intent": "qa_direct"},
            config={"configurable": {"thread_id": "p6-2"}},
        )
    labels = [e["phase"] for e in result.get("branch_trace", [])]
    assert "rag_first_error" in labels


def test_invalid_retry_key_at_decoration_time():
    import pytest

    from app.agent.node_decorator import node

    with pytest.raises(ValueError, match="retry"):
        @node(name="phase6_bad_node", retry="NONEXISTENT")
        def _x(state):
            return state
