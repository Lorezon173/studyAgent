"""Multi-Agent 协作流程集成测试。"""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _fake_invoke(system_prompt, user_prompt, stream_output=False):
    if "教学助手" in system_prompt:
        return "二分查找每次取中间值比较，缩小搜索范围。"
    if "评估专家" in system_prompt:
        return '{"mastery_score": 80, "mastery_level": "high", "eval_feedback": "理解较好", "error_labels": []}'
    return "默认"


def test_multi_agent_teach_and_eval_flow(monkeypatch):
    """测试教学+评估协作流程。"""
    monkeypatch.setattr("app.services.llm.llm_service.invoke", _fake_invoke)

    resp = client.post("/chat/multi", json={
        "session_id": "multi-int-1",
        "topic": "二分查找",
        "user_input": "我想学二分查找",
    })

    assert resp.status_code == 200
    body = resp.json()
    assert body["session_id"] == "multi-int-1"
    assert body["final_reply"]
    assert body["mastery_score"] == 80
    assert body["teaching_output"] is not None
    assert body["eval_output"] is not None


def test_multi_agent_eval_only_flow(monkeypatch):
    """测试仅评估流程。"""
    monkeypatch.setattr("app.services.llm.llm_service.invoke", _fake_invoke)

    resp = client.post("/chat/multi", json={
        "session_id": "multi-int-2",
        "topic": "二分查找",
        "user_input": "评估我的理解程度",
    })

    assert resp.status_code == 200
    body = resp.json()
    assert body["eval_output"] is not None


def test_multi_agent_missing_topic():
    """测试缺少 topic 时不崩溃。"""
    resp = client.post("/chat/multi", json={
        "session_id": "multi-int-3",
        "user_input": "随便聊聊",
    })

    assert resp.status_code == 200
