"""Phase 3a：验证 Celery 应用实例与配置。"""
from celery import Celery

from app.worker.celery_app import celery_app
from app.core.config import settings


def test_celery_app_is_celery_instance():
    assert isinstance(celery_app, Celery)


def test_celery_app_main_name():
    assert celery_app.main == "learning_agent"


def test_broker_url_matches_settings():
    assert celery_app.conf.broker_url == settings.redis_url


def test_result_backend_matches_settings():
    assert celery_app.conf.result_backend == settings.redis_url


def test_task_module_included():
    """worker 启动时会 import app.worker.tasks，验证 include 配置正确。"""
    includes = celery_app.conf.include or []
    assert "app.worker.tasks" in includes
