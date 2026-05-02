"""Phase 3b Task 3：flag off 时 /chat/stream 保持 Phase 7 前的同步 Queue+Thread 行为。"""
import pytest
from fastapi.testclient import TestClient
from fastapi import FastAPI

from app.api.chat import router
from app.core.config import settings
from app.services import agent_service as agent_mod


@pytest.fixture
def app():
    a = FastAPI()
    a.include_router(router)
    return a


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def flag_off(monkeypatch):
    monkeypatch.setattr(settings, "async_graph_enabled", False)


@pytest.fixture
def stub_sync_agent(monkeypatch):
    """同��路径下 agent_service.run 返回固定 state，不触发真实 LLM。"""
    def fake_run(session_id, topic, user_input, user_id=None, stream_output=False, progress_sink=None):
        return {"session_id": session_id, "stage": "explained", "reply": "sync-reply", "history": []}

    monkeypatch.setattr(agent_mod.agent_service, "run", fake_run)


def test_chat_stream_sync_emits_stage_and_done_only(client, flag_off, stub_sync_agent):
    response = client.post(
        "/chat/stream",
        json={"session_id": "s-sync-1", "topic": "math", "user_input": "hi"},
    )
    assert response.status_code == 200
    # 同步路径不 emit accepted（那是 async 引入的）
    assert "event: accepted" not in response.text
    assert "event: stage" in response.text
    assert "event: done" in response.text


def test_chat_post_non_stream_unaffected_by_flag(client, flag_off, stub_sync_agent):
    """POST /chat（非 stream）在 flag off 时完全同步，不经 celery/pubsub。"""
    response = client.post(
        "/chat",
        json={"session_id": "s-sync-2", "topic": "math", "user_input": "hi"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["reply"] == "sync-reply"
    assert data["stage"] == "explained"
