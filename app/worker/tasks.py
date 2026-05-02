"""Celery 任务集合。

3a 阶段：仅占位 run_chat_graph，验证 web→broker→worker→pubsub 通路。
3b 阶段：将占位替换为对 agent_service.run 的真实调用 + 进度回调。
"""
from __future__ import annotations

from typing import Any

from app.services.redis_pubsub import get_default_pubsub
from app.worker.celery_app import celery_app


@celery_app.task(name="app.worker.tasks.run_chat_graph")
def run_chat_graph(payload: dict[str, Any]) -> dict[str, Any]:
    """Phase 3a 占位实现。

    通过 pubsub 在 chat:{session_id} 频道发出 accepted / done，回 echo 给调用方。
    后续 3b 阶段会引入 progress / token / stage 事件。
    """
    channel = f"chat:{payload.get('session_id', 'unknown')}"
    pubsub = get_default_pubsub()
    pubsub.publish(channel, "accepted", payload.get("session_id", ""))
    result = {"status": "ok", "echo": payload}
    pubsub.publish(channel, "done", "[DONE]")
    return result
