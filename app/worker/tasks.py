"""Celery 任务集合。

3b 阶段：run_chat_graph 调用 agent_service.run + progress_sink，经 pubsub 桥接事件。
"""
from __future__ import annotations

from typing import Any

from app.services.redis_pubsub import get_default_pubsub
from app.services.agent_service import agent_service
from app.worker.celery_app import celery_app


@celery_app.task(name="app.worker.tasks.run_chat_graph")
def run_chat_graph(payload: dict[str, Any]) -> dict[str, Any]:
    """运行一次 chat graph，经 pubsub 在 chat:{session_id} 频道推送进度。

    Events: accepted → token* → stage → done | error
    """
    session_id = str(payload.get("session_id", ""))
    channel = f"chat:{session_id}"
    pubsub = get_default_pubsub()
    pubsub.publish(channel, "accepted", session_id)

    def sink(event: str, data: str) -> None:
        pubsub.publish(channel, event, data)

    try:
        result = agent_service.run(
            session_id=session_id,
            topic=payload.get("topic"),
            user_input=str(payload.get("user_input", "")),
            user_id=payload.get("user_id"),
            progress_sink=sink,
        )
    except Exception as exc:
        pubsub.publish(channel, "error", f"{type(exc).__name__}: {exc}")
        raise

    pubsub.publish(channel, "done", "[DONE]")
    return {
        "status": "ok",
        "reply": str(result.get("reply", "")),
        "stage": str(result.get("stage", "")),
    }
