"""Phase 3a：task_dispatcher 按 ASYNC_GRAPH_ENABLED flag 分流。"""
import pytest

from app.core.config import settings
from app.worker.celery_app import celery_app
from app.services.task_dispatcher import dispatch, DispatchResult


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
    """避免占位任务真正去连 Redis。"""
    import fakeredis
    from app.services.redis_pubsub import RedisPubSub
    from app.worker import tasks as worker_tasks

    client = fakeredis.FakeRedis(decode_responses=False)
    monkeypatch.setattr(
        worker_tasks, "get_default_pubsub",
        lambda: RedisPubSub(client),
    )


def test_dispatch_returns_sync_result_when_flag_off(monkeypatch, fake_pubsub):
    monkeypatch.setattr(settings, "async_graph_enabled", False)
    result = dispatch({"session_id": "s1", "user_input": "x"})
    assert isinstance(result, DispatchResult)
    assert result.mode == "sync"
    assert result.task_id is None


def test_dispatch_returns_async_result_when_flag_on(monkeypatch, fake_pubsub):
    monkeypatch.setattr(settings, "async_graph_enabled", True)
    result = dispatch({"session_id": "s2", "user_input": "y"})
    assert result.mode == "async"
    assert result.task_id is not None
    assert isinstance(result.task_id, str)
    assert len(result.task_id) > 0


def test_dispatch_passes_payload_to_task(monkeypatch, fake_pubsub):
    """flag on 时 payload 必须原样传递，由 worker 任务消费。"""
    monkeypatch.setattr(settings, "async_graph_enabled", True)
    captured: list[dict] = []

    from app.worker import tasks as worker_tasks
    real_task = worker_tasks.run_chat_graph

    def spy_delay(payload):
        captured.append(payload)
        return real_task.apply(args=(payload,))

    monkeypatch.setattr(real_task, "delay", spy_delay)

    payload = {"session_id": "s3", "user_input": "z"}
    dispatch(payload)
    assert captured == [payload]
