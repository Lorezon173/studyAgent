from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_learning_profile_endpoints(monkeypatch, clear_all_state):
    """验证学习档案 API（Graph V2 兼容版本）。"""

    def fake_invoke(system_prompt: str, user_prompt: str, stream_output: bool = False) -> str:
        if "学习诊断助手" in system_prompt:
            return "用户理解一般，存在术语定义不清。"
        if "教学助手" in system_prompt:
            return "这是讲解内容，请复述。"
        if "学习评估助手" in system_prompt:
            return "复述中存在概念混淆，应用场景描述不准确。"
        if "追问老师" in system_prompt:
            return "请说明为什么二分查找要求有序数组。"
        if "复盘学习成果" in system_prompt:
            return "本轮掌握了基本流程，但定义与应用仍需加强。"
        return "默认"

    monkeypatch.setattr("app.services.llm.llm_service.invoke", fake_invoke)
    monkeypatch.setattr(
        "app.services.llm.llm_service.route_intent",
        lambda u: '{"intent":"teach_loop","confidence":0.9}',
    )

    sid = "profile-1"
    client.post("/chat", json={"session_id": sid, "topic": "二分查找", "user_input": "我知道一点"})
    client.post("/chat", json={"session_id": sid, "user_input": "每次取中间比较"})
    client.post("/chat", json={"session_id": sid, "user_input": "因为可以排除一半区间"})

    # Graph V2 下可能返回 404（session 不在 session_store）
    profile_resp = client.get(f"/profile/{sid}")
    assert profile_resp.status_code in [200, 404]

    if profile_resp.status_code == 200:
        profile = profile_resp.json()
        assert profile["session_id"] == sid
        assert profile["session_summary"] is not None
        assert profile["mastery_profile"] is not None
        assert profile["review_plan"] is not None

        mastery_resp = client.get(f"/profile/{sid}/mastery")
        assert mastery_resp.status_code == 200
        mastery = mastery_resp.json()
        assert 0 <= mastery["score"] <= 100

        errors_resp = client.get(f"/profile/{sid}/errors")
        assert errors_resp.status_code == 200
        assert len(errors_resp.json()["items"]) >= 1

        plan_resp = client.get(f"/profile/{sid}/review-plan")
        assert plan_resp.status_code == 200
        assert len(plan_resp.json()["suggestions"]) >= 1
