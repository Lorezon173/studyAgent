# tests/test_answer_policy_node.py
"""回答策略节点测试"""
from app.agent.nodes import answer_policy_node
from app.agent.state import LearningState


def test_answer_policy_uses_confidence_level():
    """测试回答策略使用置信等级"""
    state: LearningState = {
        "session_id": "test",
        "rag_confidence_level": "high",
        "gate_status": "pass",
    }
    result = answer_policy_node(state)
    assert result["answer_template_id"] == "high"
    assert result["boundary_notice"] == ""


def test_answer_policy_downgrades_on_gate_reject():
    """测试守门拒绝时降级"""
    state: LearningState = {
        "session_id": "test",
        "rag_confidence_level": "high",
        "gate_status": "reject",
    }
    result = answer_policy_node(state)
    assert result["answer_template_id"] == "low"


def test_answer_policy_uses_medium_for_supplement():
    """测试补充状态使用中等模板"""
    state: LearningState = {
        "session_id": "test",
        "rag_confidence_level": "high",
        "gate_status": "supplement",
    }
    result = answer_policy_node(state)
    assert result["answer_template_id"] == "medium"


def test_answer_policy_defaults_to_medium():
    """测试默认使用中等模板"""
    state: LearningState = {
        "session_id": "test",
    }
    result = answer_policy_node(state)
    assert result["answer_template_id"] == "medium"
