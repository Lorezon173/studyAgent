# tests/test_retrieval_planner_node.py
"""检索规划节点测试"""
from app.agent.nodes import retrieval_planner_node
from app.agent.state import LearningState


def test_retrieval_planner_node_sets_strategy():
    """测试检索规划节点设置策略"""
    state: LearningState = {
        "session_id": "test",
        "user_input": "二分查找是什么？",
        "topic": "算法",
    }
    result = retrieval_planner_node(state)
    assert "retrieval_strategy" in result
    assert result["retrieval_mode"] == "fact"
    assert result["retrieval_strategy"]["bm25_weight"] == 0.4


def test_retrieval_planner_node_detects_freshness():
    """测试检索规划节点检测时效性查询"""
    state: LearningState = {
        "session_id": "test",
        "user_input": "LangGraph 最新版本是什么",
        "topic": "框架",
    }
    result = retrieval_planner_node(state)
    assert result["retrieval_mode"] == "freshness"
    assert result["retrieval_strategy"]["web_enabled"] is True


def test_retrieval_planner_node_detects_comparison():
    """测试检索规划节点检测对比查询"""
    state: LearningState = {
        "session_id": "test",
        "user_input": "Python和JavaScript的区别是什么",
        "topic": "编程语言",
    }
    result = retrieval_planner_node(state)
    assert result["retrieval_mode"] == "comparison"
    assert result["retrieval_strategy"]["bm25_weight"] == 0.5
