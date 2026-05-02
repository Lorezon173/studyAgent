"""Phase 3b Task 3：/chat/stream 在 flag on 时走 async 分支，从 pubsub 桥接到 SSE。"""
import pytest
import fakeredis
from fastapi.testclient import TestClient
from fastapi import FastAPI

from app.api.chat import router
from app.core.config import settings
from app.services import redis_pubsub as pubsub_mod
from app.services.redis_pubsub import RedisPubSub


@pytest.fixture
def app():
    a = FastAPI()
    a.include_router(router)
    return a


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def shared_fakeredis(monkeypatch):
    """让 chat.py 订阅端 和 worker 发布端共用同一个 fakeredis 实例。"""
    client = fakeredis.FakeRedis(decode_responses=False)
    instance = RedisPubSub(client)
    monkeypatch.setattr(pubsub_mod, "get_default_pubsub", lambda: instance)
    from app.worker import tasks as worker_tasks
    monkeypatch.setattr(worker_tasks, "get_default_pubsub", lambda: instance)
    return instance


@pytest.fixture
def flag_on(monkeypatch):
    monkeypatch.setattr(settings, "async_graph_enabled", True)


@pytest.fixture
def eager_celery(monkeypatch):
    from app.worker.celery_app import celery_app
    monkeypatch.setattr(celery_app.conf, "task_always_eager", True)
    monkeypatch.setattr(celery_app.conf, "task_eager_propagates", True)


@pytest.fixture
def stub_agent(monkeypatch):
    """worker 内部把 agent_service 替换为 stub。"""
    def fake_run(**kwargs):
        sink = kwargs.get("progress_sink")
        sink("token", "he")
        sink("token", "llo")
        sink("stage", "explained")
        return {"session_id": kwargs["session_id"], "stage": "explained", "reply": "hello"}

    from app.worker import tasks as worker_tasks
    monkeypatch.setattr(
        worker_tasks, "agent_service",
        type("Stub", (), {"run": staticmethod(fake_run)})(),
    )


def _parse_sse(raw: str) -> list[tuple[str, str]]:
    events: list[tuple[str, str]] = []
    current_event = None
    for line in raw.split("\n"):
        if line.startswith("event: "):
            current_event = line[len("event: "):].strip()
        elif line.startswith("data: ") and current_event is not None:
            events.append((current_event, line[len("data: "):]))
            current_event = None
    return events


def test_chat_stream_async_emits_accepted_token_done(
    client, flag_on, eager_celery, shared_fakeredis, stub_agent
):
    response = client.post(
        "/chat/stream",
        json={"session_id": "s-async-1", "topic": "math", "user_input": "hi"},
    )
    assert response.status_code == 200
    events = _parse_sse(response.text)
    names = [e for e, _ in events]
    assert names[0] == "accepted"
    assert "token" in names
    assert names[-1] == "done"


def test_chat_stream_async_forwards_error_event(
    client, flag_on, eager_celery, shared_fakeredis, monkeypatch
):
    """worker 异常时 SSE 应收到 error 事件。eager+propagate 模式下任务会 raise，
    但 chat.py 的 dispatch 调用站点会捕获异常并直接 yield error。"""
    def boom(**kwargs):
        raise RuntimeError("kaboom")

    from app.worker import tasks as worker_tasks
    monkeypatch.setattr(
        worker_tasks, "agent_service",
        type("Stub", (), {"run": staticmethod(boom)})(),
    )

    response = client.post(
        "/chat/stream",
        json={"session_id": "s-async-err", "topic": None, "user_input": "x"},
    )
    assert response.status_code == 200
    events = _parse_sse(response.text)
    names = [e for e, _ in events]
    assert "error" in names
