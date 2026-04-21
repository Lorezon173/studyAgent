# tests/test_recovery_node.py
"""恢复节点测试"""
from app.agent.nodes import recovery_node
from app.agent.state import LearningState


def test_recovery_node_handles_timeout():
    """测试恢复节点处理超时"""
    state: LearningState = {
        "session_id": "test",
        "node_error": "LLM request timed out",
        "stage": "rag_first",
    }
    result = recovery_node(state)
    assert result["fallback_triggered"] is True
    assert result["recovery_action"] == "use_cache"


def test_recovery_node_generates_fallback_reply():
    """测试恢复节点生成降级响应"""
    state: LearningState = {
        "session_id": "test",
        "node_error": "RAG service failed",
        "stage": "rag_first",
    }
    result = recovery_node(state)
    assert "reply" in result
    assert len(result["reply"]) > 0


def test_recovery_node_handles_unknown_error():
    """测试恢复节点处理未知错误"""
    state: LearningState = {
        "session_id": "test",
        "node_error": "Something went wrong",
        "stage": "explain",
    }
    result = recovery_node(state)
    assert result["fallback_triggered"] is True
    assert "error_code" in result


def test_recovery_node_handles_empty_error():
    """测试恢复节点处理空错误"""
    state: LearningState = {
        "session_id": "test",
        "node_error": "",
        "stage": "unknown",
    }
    result = recovery_node(state)
    assert result["fallback_triggered"] is True
    assert "reply" in result
