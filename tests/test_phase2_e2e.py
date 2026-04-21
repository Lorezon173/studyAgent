# tests/test_phase2_e2e.py
"""Phase 2 端到端测试

验证所有新节点已正确集成到 Graph V2。
"""
import pytest


def test_phase2_retrieval_planner_integrated():
    """测试检索规划节点已集成"""
    from app.agent.graph_v2 import get_learning_graph_v2
    graph = get_learning_graph_v2()

    # 验证节点存在
    node_names = list(graph.nodes.keys())
    assert "retrieval_planner" in node_names


def test_phase2_evidence_gate_integrated():
    """测试证据守门节点已集成"""
    from app.agent.graph_v2 import get_learning_graph_v2
    graph = get_learning_graph_v2()

    node_names = list(graph.nodes.keys())
    assert "evidence_gate" in node_names


def test_phase2_answer_policy_integrated():
    """测试回答策略节点已集成"""
    from app.agent.graph_v2 import get_learning_graph_v2
    graph = get_learning_graph_v2()

    node_names = list(graph.nodes.keys())
    assert "answer_policy" in node_names


def test_phase2_recovery_integrated():
    """测试恢复节点已集成"""
    from app.agent.graph_v2 import get_learning_graph_v2
    graph = get_learning_graph_v2()

    node_names = list(graph.nodes.keys())
    assert "recovery" in node_names


def test_phase2_all_phase1_nodes_still_present():
    """测试 Phase 1 节点仍然存在"""
    from app.agent.graph_v2 import get_learning_graph_v2
    graph = get_learning_graph_v2()

    node_names = list(graph.nodes.keys())

    # Phase 1 核心节点
    expected_nodes = [
        "intent_router",
        "history_check",
        "diagnose",
        "explain",
        "rag_first",
        "rag_answer",
        "llm_answer",
        "summary",
    ]

    for node in expected_nodes:
        assert node in node_names, f"Missing node: {node}"


def test_phase2_retrieval_planner_node_functional():
    """测试检索规划节点功能"""
    from app.agent.nodes import retrieval_planner_node
    from app.agent.state import LearningState

    state: LearningState = {
        "session_id": "test-e2e",
        "user_input": "什么是机器学习",
        "topic": "AI",
    }

    result = retrieval_planner_node(state)

    assert "retrieval_mode" in result
    assert "retrieval_strategy" in result
    assert result["retrieval_strategy"]["top_k"] >= 3


def test_phase2_evidence_gate_node_functional():
    """测试证据守门节点功能"""
    from app.agent.nodes import evidence_gate_node
    from app.agent.state import LearningState

    state: LearningState = {
        "session_id": "test-e2e",
        "user_input": "机器学习",
        "rag_context": "机器学习是人工智能的一个分支",
        "rag_found": True,
    }

    result = evidence_gate_node(state)

    assert "gate_status" in result
    assert result["gate_status"] in ["pass", "supplement", "reject"]


def test_phase2_answer_policy_node_functional():
    """测试回答策略节点功能"""
    from app.agent.nodes import answer_policy_node
    from app.agent.state import LearningState

    state: LearningState = {
        "session_id": "test-e2e",
        "rag_confidence_level": "high",
        "gate_status": "pass",
    }

    result = answer_policy_node(state)

    assert "answer_template_id" in result
    assert "boundary_notice" in result


def test_phase2_recovery_node_functional():
    """测试恢复节点功能"""
    from app.agent.nodes import recovery_node
    from app.agent.state import LearningState

    state: LearningState = {
        "session_id": "test-e2e",
        "node_error": "Test timeout error",
        "stage": "rag_first",
    }

    result = recovery_node(state)

    assert "recovery_action" in result
    assert "reply" in result
    assert result["fallback_triggered"] is True
