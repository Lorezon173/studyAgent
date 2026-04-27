from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from app.core.config import settings
from app.services.query_planner import build_query_plan
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
    query_mode: str
    query_reason: str
    candidates: list[dict[str, Any]] = None  # type: ignore[assignment]
    selected_chunk_ids: list[str] = None  # type: ignore[assignment]
    elapsed_ms: int = 0
    reranked: bool = False

    def __post_init__(self) -> None:
        if self.candidates is None:
            self.candidates = []
        if self.selected_chunk_ids is None:
            self.selected_chunk_ids = []


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
    strategy: dict | None = None,
) -> tuple[list[dict[str, Any]], RAGExecutionMeta]:
    start = time.monotonic()
    plan = build_query_plan(query, topic)
    merged_route = dict(tool_route or {})
    if plan.enable_web and not merged_route.get("tool"):
        merged_route["tool"] = "search_web"

    rows, used_tools = execute_retrieval_tools(
        query=plan.rewritten_query,
        topic=topic,
        user_id=user_id,
        tool_route=merged_route,
        top_k=max(1, min(top_k, plan.top_k)),
    )

    reranked = False
    if rows and strategy:
        from app.services.rerank_service import should_rerank, rerank_items
        if should_rerank(strategy=strategy, candidate_count=len(rows)):
            rows = rerank_items(plan.rewritten_query, rows)
            reranked = True

    elapsed = int((time.monotonic() - start) * 1000)
    candidates = [
        {
            "chunk_id": str(r.get("chunk_id", "")),
            "score": float(r.get("score", 0.0)),
            "tool": r.get("tool", ""),
        }
        for r in rows
    ]
    selected_ids = [c["chunk_id"] for c in candidates if c["chunk_id"]]

    if rows:
        return rows, RAGExecutionMeta(
            reason="tool_retrieval_reranked" if reranked else "tool_retrieval",
            used_tools=used_tools,
            hit_count=len(rows),
            fallback_used=False,
            query_mode=plan.mode,
            query_reason=plan.reason,
            candidates=candidates,
            selected_chunk_ids=selected_ids,
            elapsed_ms=elapsed,
            reranked=reranked,
        )
    return [], RAGExecutionMeta(
        reason="tool_retrieval_empty",
        used_tools=used_tools,
        hit_count=0,
        fallback_used=False,
        query_mode=plan.mode,
        query_reason=plan.reason,
        candidates=candidates,
        selected_chunk_ids=selected_ids,
        elapsed_ms=elapsed,
        reranked=reranked,
    )
