"""Orchestrator Agent 单元测试。"""
from app.agent.multi_agent.orchestrator import orchestrator_node, aggregator_node


def _make_state(**overrides):
    base = {
        "session_id": "test-1",
        "user_id": 1,
        "user_input": "",
        "topic": "二分查找",
        "current_agent": "orchestrator",
        "task_queue": [],
        "completed_tasks": [],
        "teaching_output": {},
        "eval_output": {},
        "retrieval_output": {},
        "final_reply": "",
        "mastery_score": None,
        "branch_trace": [],
    }
    base.update(overrides)
    return base


def test_orchestrator_routes_teaching_for_learn_intent():
    state = _make_state(user_input="我想学二分查找")
    result = orchestrator_node(state)
    assert result["current_agent"] == "teaching"
    assert any(t["type"] == "teach" for t in result["task_queue"])


def test_orchestrator_routes_eval_for_evaluate_intent():
    state = _make_state(user_input="评估我的理解程度")
    result = orchestrator_node(state)
    assert result["current_agent"] == "eval"


def test_orchestrator_routes_qa_for_direct_question():
    state = _make_state(user_input="二分查找的时间复杂度是什么？")
    result = orchestrator_node(state)
    assert result["current_agent"] in ("retrieval", "teaching")


def test_orchestrator_default_teaching_pipeline(monkeypatch):
    """无规则匹配时走 LLM 路由，默认 teaching 流水线。"""
    monkeypatch.setattr(
        "app.services.llm.llm_service.route_intent",
        lambda user_input: '{"intent":"teach_loop","confidence":0.8,"reason":"学习意图"}',
    )
    state = _make_state(user_input="聊聊哈希表")
    result = orchestrator_node(state)
    assert result["current_agent"] == "teaching"
    types = [t["type"] for t in result["task_queue"]]
    assert "teach" in types
    assert "evaluate" in types


def test_aggregator_combines_outputs():
    state = _make_state(
        teaching_output={"reply": "讲解内容"},
        eval_output={"eval_feedback": "评估反馈"},
    )
    result = aggregator_node(state)
    assert "讲解内容" in result["final_reply"]
    assert "评估反馈" in result["final_reply"]
