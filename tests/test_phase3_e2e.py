"""Phase 3 E2E: Phase 2 nodes are reachable, gating works, rag_detail emitted."""
import json
from unittest.mock import patch

from app.agent.graph_v2 import build_learning_graph_v2


def _state(query: str, **overrides):
    base = {
        "session_id": f"e2e-{abs(hash(query)) % 10000}",
        "user_input": query,
        "topic": "数据结构",
        "intent": "qa_direct",
    }
    base.update(overrides)
    return base


def _invoke(state):
    graph = build_learning_graph_v2()
    return graph.invoke(state, config={"configurable": {"thread_id": state["session_id"]}})


def _intent_qa_direct(_user_input: str) -> str:
    return json.dumps({"intent": "qa_direct", "confidence": 0.95, "reason": "qa"})


def _fake_invoke(*_args, **_kwargs) -> str:
    """Stub for llm_service.invoke used by rag_answer / llm_answer / etc."""
    return "测试回答内容"


def test_e2e_qa_direct_happy_path_emits_rag_meta_and_visits_answer_policy():
    """Successful retrieval reaches answer_policy and exposes rag_meta_last in state."""
    fake_rows = [
        {"chunk_id": f"c{i}", "score": 0.9 - i * 0.1, "text": f"数据库索引内容 {i}"}
        for i in range(3)
    ]
    with patch(
        "app.services.tool_executor.execute_retrieval_tools",
        return_value=(fake_rows, ["search_local_textbook"]),
    ), patch(
        "app.services.rag_coordinator.execute_retrieval_tools",
        return_value=(fake_rows, ["search_local_textbook"]),
    ), patch(
        "app.services.llm.llm_service.route_intent",
        side_effect=_intent_qa_direct,
    ), patch(
        "app.services.llm.llm_service.invoke",
        side_effect=_fake_invoke,
    ):
        result = _invoke(_state("请介绍数据库索引的平衡多路搜索树"))

    # answer_policy populates answer_template_id
    assert result.get("answer_template_id"), "answer_policy node not reached"
    # Task 5: rag_meta_last must be in state
    meta = result.get("rag_meta_last")
    assert meta is not None, "rag_meta_last not written"
    assert len(meta.candidates) == 3
    assert meta.selected_chunk_ids == ["c0", "c1", "c2"]
    assert meta.elapsed_ms >= 0


def test_e2e_qa_direct_empty_retrieval_routes_to_recovery():
    """Empty retrieval -> evidence_gate rejects -> recovery node visited."""
    with patch(
        "app.services.tool_executor.execute_retrieval_tools",
        return_value=([], []),
    ), patch(
        "app.services.rag_coordinator.execute_retrieval_tools",
        return_value=([], []),
    ), patch(
        "app.services.llm.llm_service.route_intent",
        side_effect=_intent_qa_direct,
    ), patch(
        "app.services.llm.llm_service.invoke",
        side_effect=_fake_invoke,
    ):
        result = _invoke(_state("请介绍数据库索引"))

    assert result.get("recovery_action") or result.get("fallback_triggered"), (
        "recovery node was not visited despite empty retrieval"
    )


def test_e2e_comparison_query_triggers_rerank():
    """Comparison strategy with >=4 candidates -> rerank invoked, meta.reranked=True."""
    fake_rows = [
        {"chunk_id": f"c{i}", "score": 0.5, "text": f"对比内容 {i}"}
        for i in range(6)
    ]
    # The query contains "对比" so retrieval_planner_node selects the
    # comparison strategy (bm25=0.5, vector=0.5, top_k=5). With 6 candidates,
    # should_rerank returns True and rerank_items is invoked from execute_rag.
    with patch(
        "app.services.tool_executor.execute_retrieval_tools",
        return_value=(fake_rows, ["search_local_textbook"]),
    ), patch(
        "app.services.rag_coordinator.execute_retrieval_tools",
        return_value=(fake_rows, ["search_local_textbook"]),
    ), patch(
        "app.services.rerank_service.rerank_items",
        side_effect=lambda q, items: list(reversed(items)),
    ) as rerank_spy, patch(
        "app.services.llm.llm_service.route_intent",
        side_effect=_intent_qa_direct,
    ), patch(
        "app.services.llm.llm_service.invoke",
        side_effect=_fake_invoke,
    ):
        result = _invoke(_state("对比快速排序和归并排序的时间复杂度差异"))

    meta = result.get("rag_meta_last")
    assert meta is not None
    assert rerank_spy.called and meta.reranked, \
        "rerank not invoked for comparison-mode query with 6 candidates"
