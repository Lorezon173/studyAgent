"""验证 Phase 5 改造后所有既有调用路径仍工作。"""
from unittest.mock import patch
from app.agent.graph_v2 import build_learning_graph_v2


def test_qa_direct_happy_path_after_phase5():
    """Phase 5 不应改变 qa_direct 成功路径行为。"""
    fake_rows = [
        {"chunk_id": f"c{i}", "score": 0.9 - i * 0.1,
         "text": f"什么是数据库索引：数据库索引内容 {i}"}
        for i in range(3)
    ]
    with patch("app.services.rag_coordinator.execute_retrieval_tools",
               return_value=(fake_rows, ["search_local_textbook"])), \
         patch("app.services.llm.llm_service.route_intent",
               return_value='{"intent":"qa_direct"}'), \
         patch("app.services.llm.llm_service.invoke", return_value="answer"):
        graph = build_learning_graph_v2()
        result = graph.invoke(
            {"session_id": "p5-1", "user_input": "请介绍数据库索引",
             "topic": "数据结构", "intent": "qa_direct"},
            config={"configurable": {"thread_id": "p5-1"}},
        )
    assert "rag_found" in result
    assert "rag_context" in result
    assert "answer_template_id" in result
    assert result.get("rag_found") is True


def test_qa_direct_retry_then_recover_after_phase5():
    """Phase 4 引入的单次重试语义不应被 Phase 5 改造破坏。"""
    call_count = {"n": 0}

    def flaky(*a, **kw):
        call_count["n"] += 1
        raise TimeoutError("timed out")

    with patch("app.services.rag_coordinator.execute_retrieval_tools",
               side_effect=flaky), \
         patch("app.services.llm.llm_service.route_intent",
               return_value='{"intent":"qa_direct"}'), \
         patch("app.services.llm.llm_service.invoke", return_value="stub"):
        graph = build_learning_graph_v2()
        result = graph.invoke(
            {"session_id": "p5-2", "user_input": "什么是B+树",
             "topic": "数据结构", "intent": "qa_direct"},
            config={"configurable": {"thread_id": "p5-2"}},
        )
    assert call_count["n"] == 2
    assert result.get("error_code") == "llm_timeout"
    assert result.get("fallback_triggered") is True


def test_legacy_imports_still_work():
    """既有测试通过 `from app.agent.nodes import xxx_node` 必须仍可用。"""
    from app.agent.nodes import (
        intent_router_node,
        rag_first_node,
        knowledge_retrieval_node,
        evidence_gate_node,
        recovery_node,
    )
    assert callable(intent_router_node)
    assert callable(rag_first_node)
    assert callable(knowledge_retrieval_node)
    assert callable(evidence_gate_node)
    assert callable(recovery_node)


def test_decorator_metadata_accessible_at_runtime():
    """通过 NodeRegistry 可读取每个节点的 retry_key 与 trace_label。"""
    from app.agent.node_registry import get_registry
    import app.agent.nodes  # 触发注册

    reg = get_registry()
    rag_first_meta, _ = reg.get("rag_first")
    assert rag_first_meta.retry_key == "RAG_RETRY"
    assert rag_first_meta.trace_label == "RAG First"

    intent_meta, _ = reg.get("intent_router")
    assert intent_meta.retry_key == "LLM_RETRY"

    gate_meta, _ = reg.get("evidence_gate")
    assert gate_meta.retry_key is None
