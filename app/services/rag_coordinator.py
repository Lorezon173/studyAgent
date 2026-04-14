from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.core.config import settings
from app.services.tool_executor import execute_retrieval_tools


@dataclass
class RAGCallDecision:
    should_call: bool
    reason: str


@dataclass
class RAGExecutionMeta:
    reason: str
    used_tools: list[str]
    hit_count: int
    fallback_used: bool


def decide_rag_call(*, user_input: str) -> RAGCallDecision:
    if not settings.rag_enabled:
        return RAGCallDecision(should_call=False, reason="rag_disabled")
    if not (user_input or "").strip():
        return RAGCallDecision(should_call=False, reason="empty_query")
    return RAGCallDecision(should_call=True, reason="enabled")


def execute_rag(
    *,
    query: str,
    topic: str | None,
    user_id: int | None,
    tool_route: dict[str, Any] | None,
    top_k: int,
) -> tuple[list[dict[str, Any]], RAGExecutionMeta]:
    rows, used_tools = execute_retrieval_tools(
        query=query,
        topic=topic,
        user_id=user_id,
        tool_route=tool_route,
        top_k=max(1, top_k),
    )
    if rows:
        return rows, RAGExecutionMeta(
            reason="tool_retrieval",
            used_tools=used_tools,
            hit_count=len(rows),
            fallback_used=False,
        )
    return [], RAGExecutionMeta(
        reason="tool_retrieval_empty",
        used_tools=used_tools,
        hit_count=0,
        fallback_used=False,
    )

