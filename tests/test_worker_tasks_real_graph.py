"""Phase 3b Task 2：run_chat_graph 调用真实 agent_service.run 并通过 pubsub 桥接进度。"""
import threading
import time
import pytest
import fakeredis

from app.worker.celery_app import celery_app
from app.worker import tasks as worker_tasks
from app.services.redis_pubsub import RedisPubSub


@pytest.fixture(autouse=True)
def eager_mode():
    prev = (celery_app.conf.task_always_eager, celery_app.conf.task_eager_propagates)
    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = True
    yield
    celery_app.conf.task_always_eager = prev[0]
    celery_app.conf.task_eager_propagates = prev[1]


@pytest.fixture
def fake_pubsub(monkeypatch):
    client = fakeredis.FakeRedis(decode_responses=False)
    instance = RedisPubSub(client)
    monkeypatch.setattr(worker_tasks, "get_default_pubsub", lambda: instance)
    return instance


@pytest.fixture
def mock_agent_service(monkeypatch):
    """让 agent_service.run 直接通过 progress_sink 推 2 token + 1 stage 后返回。"""
    def fake_run(**kwargs):
        sink = kwargs.get("progress_sink")
        assert sink is not None, "worker 必须传 progress_sink"
        sink("token", "hello ")
        sink("token", "world")
        sink("stage", "explained")
        return {"session_id": kwargs["session_id"], "stage": "explained", "reply": "hello world"}

    monkeypatch.setattr(
        worker_tasks, "agent_service",
        type("Stub", (), {"run": staticmethod(fake_run)})(),
    )


def test_run_chat_graph_emits_full_event_sequence(fake_pubsub, mock_agent_service):
    session_id = "s-3b-1"
    received: list[tuple[str, str]] = []

    def consumer():
        for ev, data in fake_pubsub.subscribe(f"chat:{session_id}", timeout_s=3.0):
            received.append((ev, data))

    t = threading.Thread(target=consumer, daemon=True)
    t.start()
    time.sleep(0.1)

    payload = {"session_id": session_id, "topic": "math", "user_input": "hi"}
    result = worker_tasks.run_chat_graph.delay(payload).get(timeout=5)
    t.join(timeout=3.0)

    events = [e for e, _ in received]
    assert events[0] == "accepted"
    assert "token" in events
    assert events[-1] == "done"
    assert result == {"status": "ok", "reply": "hello world", "stage": "explained"}


def test_run_chat_graph_emits_error_on_exception(fake_pubsub, monkeypatch):
    def boom(**kwargs):
        raise RuntimeError("graph failed")

    monkeypatch.setattr(
        worker_tasks, "agent_service",
        type("Stub", (), {"run": staticmethod(boom)})(),
    )

    session_id = "s-3b-err"
    received: list[tuple[str, str]] = []

    def consumer():
        for ev, data in fake_pubsub.subscribe(f"chat:{session_id}", timeout_s=3.0):
            received.append((ev, data))

    t = threading.Thread(target=consumer, daemon=True)
    t.start()
    time.sleep(0.1)

    payload = {"session_id": session_id, "topic": None, "user_input": "x"}
    with pytest.raises(Exception):
        worker_tasks.run_chat_graph.delay(payload).get(timeout=5)
    t.join(timeout=3.0)

    events = [e for e, _ in received]
    assert events[0] == "accepted"
    assert events[-1] == "error"
