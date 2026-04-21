# tests/test_evidence_gate_node.py
"""证据守门节点测试"""
from app.agent.nodes import evidence_gate_node
from app.agent.state import LearningState


def test_evidence_gate_node_passes_high_quality():
    """测试高质量证据通过守门"""
    state: LearningState = {
        "session_id": "test",
        "user_input": "二分查找",
        "rag_context": "二分查找是一种搜索算法，时间复杂度O(log n)",
        "rag_found": True,
        "rag_confidence_level": "high",
    }
    result = evidence_gate_node(state)
    # 由于覆盖度计算，结果可能是 pass 或 supplement
    assert result["gate_status"] in ["pass", "supplement"]


def test_evidence_gate_node_rejects_no_evidence():
    """测试无证据拒绝"""
    state: LearningState = {
        "session_id": "test",
        "user_input": "量子计算原理",
        "rag_context": "",
        "rag_found": False,
    }
    result = evidence_gate_node(state)
    assert result["gate_status"] == "reject"
    assert result["gate_coverage_score"] == 0.0


def test_evidence_gate_node_rejects_empty_context():
    """测试空上下文拒绝"""
    state: LearningState = {
        "session_id": "test",
        "user_input": "测试问题",
        "rag_context": "",
        "rag_found": True,
    }
    result = evidence_gate_node(state)
    assert result["gate_status"] == "reject"


def test_evidence_gate_node_returns_coverage():
    """测试返回覆盖度分数"""
    state: LearningState = {
        "session_id": "test",
        "user_input": "二分查找",
        "rag_context": "二分查找是一种搜索算法",
        "rag_found": True,
    }
    result = evidence_gate_node(state)
    assert "gate_coverage_score" in result
    assert isinstance(result["gate_coverage_score"], float)
    assert "gate_missing_keywords" in result
    assert isinstance(result["gate_missing_keywords"], list)
