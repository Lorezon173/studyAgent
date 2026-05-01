"""Phase 3a：验证异步骨架新增的 Settings 字段默认值与可覆盖性。"""
import pytest
from app.core.config import Settings


def test_async_graph_enabled_default_false():
    s = Settings()
    assert s.async_graph_enabled is False


def test_redis_url_default_localhost():
    s = Settings()
    assert s.redis_url == "redis://localhost:6379/0"


def test_celery_task_timeout_default_60_seconds():
    s = Settings()
    assert s.celery_task_timeout_s == 60


def test_async_graph_enabled_can_be_overridden_via_env(monkeypatch):
    monkeypatch.setenv("ASYNC_GRAPH_ENABLED", "true")
    s = Settings()
    assert s.async_graph_enabled is True


def test_redis_url_can_be_overridden_via_env(monkeypatch):
    monkeypatch.setenv("REDIS_URL", "redis://other-host:6380/1")
    s = Settings()
    assert s.redis_url == "redis://other-host:6380/1"


def test_celery_task_timeout_can_be_overridden_via_env(monkeypatch):
    monkeypatch.setenv("CELERY_TASK_TIMEOUT_S", "120")
    s = Settings()
    assert s.celery_task_timeout_s == 120
