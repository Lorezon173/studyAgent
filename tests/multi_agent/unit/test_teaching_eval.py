"""Teaching Eval Subagent 单元测试。"""
import json
from app.agent.system_eval.teaching_eval import teaching_eval_node, _parse_score


def test_parse_score_valid():
    result = _parse_score('{"clarity_score": 85, "reason": "清晰"}')
    assert result == 85.0


def test_parse_score_invalid():
    result = _parse_score("not json")
    assert result == 50.0


def test_teaching_eval_returns_scores(monkeypatch):
    def fake_invoke(system_prompt, user_prompt, stream_output=False):
        if "清晰度" in user_prompt:
            return json.dumps({"clarity_score": 80, "reason": "逻辑清晰"})
        if "覆盖" in user_prompt:
            return json.dumps({"coverage_score": 70, "covered_points": ["基础概念"], "missing_points": ["边界条件"]})
        return "默认"

    monkeypatch.setattr("app.services.llm.llm_service.invoke", fake_invoke)

    result = teaching_eval_node({
        "session_id": "sess-1",
        "topic": "二分查找",
        "user_input": "我想学二分查找",
        "teaching_output": {"explanation": "二分查找是一种搜索算法", "reply": "讲解内容"},
        "final_mastery_score": 75.0,
    })

    assert result["session_id"] == "sess-1"
    assert result["clarity_score"] == 80.0
    assert result["coverage_score"] == 70.0
    assert result["effectiveness_score"] > 0
    assert result["teaching_score"] > 0
    assert isinstance(result["improvement_suggestions"], list)


def test_teaching_eval_composite_score(monkeypatch):
    """验证综合评分 = clarity*0.4 + coverage*0.3 + effectiveness*0.3。"""
    def fake_invoke(system_prompt, user_prompt, stream_output=False):
        if "清晰度" in user_prompt:
            return json.dumps({"clarity_score": 90, "reason": "ok"})
        if "覆盖" in user_prompt:
            return json.dumps({"coverage_score": 80, "covered_points": [], "missing_points": []})
        return "默认"

    monkeypatch.setattr("app.services.llm.llm_service.invoke", fake_invoke)

    result = teaching_eval_node({
        "session_id": "sess-2",
        "topic": "图",
        "user_input": "学图",
        "teaching_output": {"explanation": "图的讲解", "reply": "讲解"},
        "final_mastery_score": 80.0,
    })

    expected = 90 * 0.4 + 80 * 0.3 + min(100, 80 * 1.1) * 0.3
    assert abs(result["teaching_score"] - expected) < 0.01
