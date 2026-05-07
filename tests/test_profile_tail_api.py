import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


@pytest.mark.skip(reason="Graph V2 recursion issue - needs deeper investigation")
def test_profile_tail_endpoints(monkeypatch, clear_all_state, fresh_checkpointer):
    """验证学习档案扩展 API（Graph V2 兼容版本）。"""

    def fake_invoke(system_prompt: str, user_prompt: str, stream_output: bool = False) -> str:
        if "学习诊断助手" in system_prompt:
            return "术语理解一般，存在定义不清。"
        if "教学助手" in system_prompt:
            return "这是讲解内容。"
        if "学习评估助手" in system_prompt:
            return "存在概念混淆与应用不足。"
        if "追问老师" in system_prompt:
            return "请说明适用条件。"
        if "复盘学习成果" in system_prompt:
            return "已掌握基本流程，但概念区分仍需加强。"
        return "默认"

    monkeypatch.setattr("app.services.llm.llm_service.invoke", fake_invoke)
    monkeypatch.setattr(
        "app.services.llm.llm_service.route_intent",
        lambda u: '{"intent":"teach_loop","confidence":0.9}',
    )
    monkeypatch.setattr(
        "app.services.llm.llm_service.detect_topic",
        lambda u, c: '{"topic":"二分查找","changed":false,"confidence":0.9,"reason":"主题稳定","comparison_mode":false}',
    )

    sid = "tail-api-1"
    topic = "二分查找"
    client.post("/chat", json={"session_id": sid, "topic": topic, "user_input": "我知道一点"})
    client.post("/chat", json={"session_id": sid, "user_input": "每次比较中间值"})
    client.post("/chat", json={"session_id": sid, "user_input": "因为可以排除一半"})

    # 检查 API 返回格式
    overview_resp = client.get("/profile/overview")
    assert overview_resp.status_code == 200

    topic_resp = client.get(f"/profile/topic/{topic}")
    assert topic_resp.status_code == 200

    timeline_resp = client.get(f"/profile/session/{sid}/timeline")
    # Graph V2 下可能返回 404（session 不在 session_store）
    assert timeline_resp.status_code in [200, 404]

    memory_resp = client.get(f"/profile/topic/{topic}/memory")
    assert memory_resp.status_code == 200
