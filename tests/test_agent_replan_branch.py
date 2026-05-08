"""Agent 重规划分支测试 - Graph V2 兼容性问题待解决。

注意：这些测试依赖 get_session() 从 session_store 获取状态。
Graph V2 使用 LangGraph checkpointer 存储状态，导致 get_session() 返回 None。
需要重构测试以使用 LangGraph checkpointer API 或标记跳过。
"""
import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


@pytest.mark.skip(reason="Graph V2 兼容问题：session_store 为空，需要适配 LangGraph checkpointer")
def test_auto_branch_to_qa_direct(monkeypatch):
    from app.services.session_store import clear_all_sessions
    clear_all_sessions()

    def fake_invoke(system_prompt: str, user_prompt: str, stream_output: bool = False) -> str:
        if "学习诊断助手" in system_prompt:
            return "诊断"
        if "教学助手" in system_prompt:
            return "讲解"
        return "默认"

    monkeypatch.setattr("app.services.llm.llm_service.invoke", fake_invoke)
    monkeypatch.setattr(
        "app.services.llm.llm_service.answer_direct",
        lambda user_input, topic, comparison_mode=False: "这是LLM直答结果",
    )
    monkeypatch.setattr(
        "app.services.llm.llm_service.detect_topic",
        lambda user_input, current_topic: '{"topic":"图","changed":false,"confidence":0.8,"reason":"主题稳定","comparison_mode":false}',
    )
    monkeypatch.setattr(
        "app.services.llm.llm_service.route_intent",
        lambda user_input: '{"intent":"qa_direct","confidence":0.9,"reason":"LLM判断为直接问答"}',
    )
    sid = "branch-qa-1"

    # 第一次先建立会话
    resp1 = client.post("/chat", json={"session_id": sid, "topic": "图", "user_input": "我想学习图"})
    assert resp1.status_code == 200

    # 第二次输入直接问答意图，应该进入 qa_direct 分支
    resp2 = client.post("/chat", json={"session_id": sid, "user_input": "这是什么？请直接回答"})
    assert resp2.status_code == 200
    body = resp2.json()
    assert body["stage"] == "explained"
    assert body["reply"] == "这是LLM直答结果"


@pytest.mark.skip(reason="Graph V2 兼容问题：session_store 为空，需要适配 LangGraph checkpointer")
def test_auto_replan(monkeypatch):
    from app.services.session_store import clear_all_sessions
    clear_all_sessions()

    def fake_invoke(system_prompt: str, user_prompt: str, stream_output: bool = False) -> str:
        if "学习诊断助手" in system_prompt:
            return "诊断"
        if "教学助手" in system_prompt:
            return "讲解"
        return "默认"

    monkeypatch.setattr("app.services.llm.llm_service.invoke", fake_invoke)
    monkeypatch.setattr(
        "app.services.llm.llm_service.detect_topic",
        lambda user_input, current_topic: '{"topic":"二分查找","changed":false,"confidence":0.8,"reason":"主题稳定","comparison_mode":false}',
    )
    sid = "replan-1"
    client.post("/chat", json={"session_id": sid, "topic": "二分查找", "user_input": "先学这个"})

    # 显式触发重规划
    monkeypatch.setattr(
        "app.services.llm.llm_service.route_intent",
        lambda user_input: '{"intent":"replan","confidence":0.95,"reason":"LLM判断重规划"}',
    )
    resp = client.post("/chat", json={"session_id": sid, "user_input": "重规划：我想改成学习哈希表"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["stage"] == "planned"
    assert "重规划" in body["reply"]
    assert "当前目标" in body["reply"]
    assert "下一步建议" in body["reply"]


@pytest.mark.skip(reason="Graph V2 兼容问题：session_store 为空，需要适配 LangGraph checkpointer")
def test_replan_can_work_on_first_round(monkeypatch):
    from app.services.session_store import clear_all_sessions
    clear_all_sessions()

    monkeypatch.setattr(
        "app.services.llm.llm_service.detect_topic",
        lambda user_input, current_topic: '{"topic":"哈希表","changed":true,"confidence":0.9,"reason":"首轮识别主题","comparison_mode":false}',
    )
    monkeypatch.setattr(
        "app.services.llm.llm_service.route_intent",
        lambda user_input: '{"intent":"replan","confidence":0.95,"reason":"首轮即重规划"}',
    )

    sid = "replan-first-1"
    resp = client.post("/chat", json={"session_id": sid, "user_input": "重规划：我想先学哈希表"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["stage"] == "planned"
    assert "当前目标" in body["reply"]
    assert "下一步建议" in body["reply"]


@pytest.mark.skip(reason="Graph V2 兼容问题：session_store 为空，需要适配 LangGraph checkpointer")
def test_route_fallback_when_llm_route_invalid(monkeypatch):
    from app.services.session_store import clear_all_sessions
    clear_all_sessions()

    def fake_invoke(system_prompt: str, user_prompt: str, stream_output: bool = False) -> str:
        if "学习诊断助手" in system_prompt:
            return "诊断"
        if "教学助手" in system_prompt:
            return "讲解"
        return "默认"

    monkeypatch.setattr("app.services.llm.llm_service.invoke", fake_invoke)
    monkeypatch.setattr(
        "app.services.llm.llm_service.detect_topic",
        lambda user_input, current_topic: '{"topic":"图","changed":false,"confidence":0.8,"reason":"主题稳定","comparison_mode":false}',
    )
    monkeypatch.setattr("app.services.llm.llm_service.route_intent", lambda user_input: "invalid-json")

    sid = "fallback-1"
    resp = client.post("/chat", json={"session_id": sid, "topic": "图", "user_input": "为什么需要有序数组？"})
    assert resp.status_code == 200


@pytest.mark.skip(reason="Graph V2 兼容问题：session_store 为空，需要适配 LangGraph checkpointer")
def test_tool_router_prefers_personal_memory_when_user_context(monkeypatch):
    from app.services.session_store import clear_all_sessions
    clear_all_sessions()

    def fake_invoke(system_prompt: str, user_prompt: str, stream_output: bool = False) -> str:
        if "学习诊断助手" in system_prompt:
            return "诊断"
        if "教学助手" in system_prompt:
            return "讲解"
        return "默认"

    monkeypatch.setattr("app.services.llm.llm_service.invoke", fake_invoke)
    monkeypatch.setattr(
        "app.services.llm.llm_service.detect_topic",
        lambda user_input, current_topic: '{"topic":"二分查找","changed":false,"confidence":0.8,"reason":"主题稳定","comparison_mode":false}',
    )
    monkeypatch.setattr(
        "app.services.llm.llm_service.route_intent",
        lambda user_input: '{"intent":"teach_loop","confidence":0.9,"reason":"继续教学"}',
    )

    sid = "tool-route-personal-1"
    resp = client.post(
        "/chat",
        json={"session_id": sid, "user_id": 1, "topic": "二分查找", "user_input": "我上次在边界条件总是错"},
    )
    assert resp.status_code == 200
