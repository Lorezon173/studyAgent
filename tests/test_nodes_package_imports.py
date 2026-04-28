"""保证 nodes.py → nodes/ 包拆分后所有公共导入仍可工作。"""


def test_all_nodes_importable_from_app_agent_nodes():
    from app.agent.nodes import (
        intent_router_node,
        history_check_node,
        ask_review_or_continue_node,
        diagnose_node,
        knowledge_retrieval_node,
        explain_node,
        restate_check_node,
        followup_node,
        summarize_node,
        rag_first_node,
        rag_answer_node,
        llm_answer_node,
        replan_node,
        retrieval_planner_node,
        evidence_gate_node,
        answer_policy_node,
        recovery_node,
    )
    nodes = [
        intent_router_node, history_check_node, ask_review_or_continue_node,
        diagnose_node, knowledge_retrieval_node, explain_node, restate_check_node,
        followup_node, summarize_node, rag_first_node, rag_answer_node,
        llm_answer_node, replan_node, retrieval_planner_node, evidence_gate_node,
        answer_policy_node, recovery_node,
    ]
    assert len(nodes) == 17
    for n in nodes:
        assert callable(n), f"{n} is not callable"


def test_subpackages_are_importable():
    from app.agent.nodes import teach, qa, orchestration
    from app.agent.nodes import _shared
    assert hasattr(teach, "diagnose_node")
    assert hasattr(qa, "knowledge_retrieval_node")
    assert hasattr(orchestration, "evidence_gate_node")
    assert hasattr(_shared, "_append_trace")


def test_existing_test_mock_paths_still_resolve():
    """验证测试中常用的 mock 路径仍解析到同一对象。"""
    from app.agent import nodes
    assert hasattr(nodes, "knowledge_retrieval_node")
    assert hasattr(nodes, "rag_first_node")
    # llm_service is mocked via "app.agent.nodes.llm_service.invoke" in tests
    assert hasattr(nodes, "llm_service")
