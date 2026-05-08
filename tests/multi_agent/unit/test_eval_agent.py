"""Eval Agent 单元测试。"""
import json
from app.agent.multi_agent.eval_agent import eval_agent_node, _parse_eval_result


def _make_state(**overrides):
    base = {
        "session_id": "test-1",
        "user_id": 1,
        "user_input": "我理解了一些",
        "topic": "二分查找",
        "current_agent": "teaching",
        "task_queue": [],
        "completed_tasks": [],
        "teaching_output": {"reply": "讲解内容", "explanation": "讲解内容"},
        "eval_output": {},
        "retrieval_output": {},
        "final_reply": "",
        "mastery_score": None,
        "branch_trace": [],
    }
    base.update(overrides)
    return base


def test_parse_eval_result_valid_json():
    result = _parse_eval_result('{"mastery_score": 75, "mastery_level": "medium", "eval_feedback": "一般", "error_labels": []}')
    assert result["mastery_score"] == 75
    assert result["mastery_level"] == "medium"


def test_parse_eval_result_invalid_json():
    result = _parse_eval_result("not json")
    assert result["mastery_score"] == 50
    assert result["mastery_level"] == "medium"


def test_eval_agent_returns_score(monkeypatch):
    monkeypatch.setattr(
        "app.services.llm.llm_service.invoke",
        lambda system_prompt, user_prompt, stream_output=False: json.dumps({
            "mastery_score": 80,
            "mastery_level": "high",
            "eval_feedback": "理解较好",
            "error_labels": [],
        }),
    )
    state = _make_state()
    result = eval_agent_node(state)
    assert result["eval_output"]["mastery_score"] == 80
    assert result["current_agent"] == "aggregator"
    assert result["mastery_score"] == 80


def test_eval_agent_handles_llm_failure(monkeypatch):
    monkeypatch.setattr(
        "app.services.llm.llm_service.invoke",
        lambda system_prompt, user_prompt, stream_output=False: "无法解析的输出",
    )
    state = _make_state()
    result = eval_agent_node(state)
    assert result["eval_output"]["mastery_score"] == 50
