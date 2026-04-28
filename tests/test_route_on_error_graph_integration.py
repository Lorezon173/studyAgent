"""验证 route_on_error 真正驱动图执行：retry 与 recovery 都通过图触发。"""
import uuid
from unittest.mock import patch
from app.agent.graph_v2 import build_learning_graph_v2


def _state(intent="qa_direct"):
    return {
        "session_id": f"ro-{intent}-{uuid.uuid4().hex[:8]}",
        "user_input": "什么是B+树",
        "topic": "数据结构",
        "intent": intent,
    }


def _invoke(state):
    graph = build_learning_graph_v2()
    return graph.invoke(state, config={"configurable": {"thread_id": state["session_id"]}})


def test_qa_direct_timeout_retries_once_then_recovers():
    """rag_first 第一次 timeout → retry_rag → 再次 timeout → recovery。"""
    call_count = {"n": 0}

    def flaky(*a, **kw):
        call_count["n"] += 1
        raise TimeoutError("timed out")

    with patch("app.services.rag_coordinator.execute_retrieval_tools", side_effect=flaky), \
         patch("app.services.llm.llm_service.route_intent", return_value='{"intent": "qa_direct", "confidence": 0.9, "reason": "test"}'), \
         patch("app.services.llm.llm_service.invoke", return_value="stub"):
        result = _invoke(_state("qa_direct"))
    assert call_count["n"] == 2, f"expected exactly 2 retrieval attempts, got {call_count['n']}"
    assert result.get("error_code") == "llm_timeout"
    assert result.get("recovery_action") or result.get("fallback_triggered")


def test_qa_direct_db_error_routing_uses_classifier():
    """db_error: behavior depends on classifier's retryable flag."""
    call_count = {"n": 0}

    def boom(*a, **kw):
        call_count["n"] += 1
        raise RuntimeError("connection refused")

    with patch("app.services.rag_coordinator.execute_retrieval_tools", side_effect=boom), \
         patch("app.services.llm.llm_service.route_intent", return_value='{"intent": "qa_direct", "confidence": 0.9, "reason": "test"}'), \
         patch("app.services.llm.llm_service.invoke", return_value="stub"):
        result = _invoke(_state("qa_direct"))

    from app.services.error_classifier import classify_from_code
    expected_calls = 2 if classify_from_code("db_error").retryable else 1
    assert call_count["n"] == expected_calls
    assert result.get("recovery_action") or result.get("fallback_triggered")
