"""Phase 3a：占位任务 run_chat_graph 在 eager 模式下的行为。"""
import threading
import time
import pytest
import fakeredis

from app.worker.celery_app import celery_app
from app.worker import tasks as worker_tasks
from app.services.redis_pubsub import RedisPubSub


@pytest.fixture(autouse=True)
def eager_mode():
    """让 .delay() 同步执行，避免拉起 worker 进程。"""
    prev = (celery_app.conf.task_always_eager, celery_app.conf.task_eager_propagates)
    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = True
    yield
    celery_app.conf.task_always_eager = prev[0]
    celery_app.conf.task_eager_propagates = prev[1]


@pytest.fixture
def fake_pubsub(monkeypatch):
    """注入 fakeredis 替代 get_default_pubsub。"""
    client = fakeredis.FakeRedis(decode_responses=False)
    instance = RedisPubSub(client)
    monkeypatch.setattr(
        worker_tasks,
        "get_default_pubsub",
        lambda: instance,
    )
    return instance


def test_run_chat_graph_returns_echo_structure(fake_pubsub):
    payload = {"session_id": "s1", "user_input": "hi"}
    result = worker_tasks.run_chat_graph.delay(payload).get(timeout=5)
    assert result == {"status": "ok", "echo": payload}


def test_run_chat_graph_emits_accepted_and_done(fake_pubsub):
    payload = {"session_id": "s2", "user_input": "x"}
    received: list[tuple[str, str]] = []

    def consumer():
        for event, data in fake_pubsub.subscribe("chat:s2", timeout_s=2.0):
            received.append((event, data))

    t = threading.Thread(target=consumer, daemon=True)
    t.start()
    time.sleep(0.1)
    worker_tasks.run_chat_graph.delay(payload).get(timeout=5)
    t.join(timeout=3.0)
    events = [e for e, _ in received]
    assert events == ["accepted", "done"]


def test_task_is_registered_with_expected_name():
    assert "app.worker.tasks.run_chat_graph" in celery_app.tasks
