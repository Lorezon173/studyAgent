"""Celery 应用实例。worker 进程入口；3a 阶段仅完成实例化与任务发现。"""
from __future__ import annotations

from celery import Celery

from app.core.config import settings


celery_app = Celery(
    "study_agent",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.worker.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_time_limit=settings.celery_task_timeout_s,
    task_soft_time_limit=max(settings.celery_task_timeout_s - 5, 1),
)
