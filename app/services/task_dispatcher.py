"""Task dispatcher：根据 ASYNC_GRAPH_ENABLED flag 决定走同步还是异步路径。

调用方（如 app/api/chat.py）只关心 DispatchResult.mode，不感知 celery。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from app.core.config import settings


@dataclass(frozen=True)
class DispatchResult:
    mode: Literal["sync", "async"]
    task_id: str | None


def dispatch(payload: dict[str, Any]) -> DispatchResult:
    if not settings.async_graph_enabled:
        return DispatchResult(mode="sync", task_id=None)

    from app.worker.tasks import run_chat_graph
    async_result = run_chat_graph.delay(payload)
    return DispatchResult(mode="async", task_id=async_result.id)
