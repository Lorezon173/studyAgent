from app.agent.state import LearningState
from app.services.agent_runtime import (
    append_branch_trace,
    create_or_update_plan,
    evaluate_step_result,
    route_intent,
    route_tool,
)
from app.services.orchestration.context_builder import ContextBuilder
from app.services.orchestration.context_builder import (
    get_topic_long_term_memory,
    retrieve_personal_memory,
    settings,
)
from app.services.rag_service import rag_service  # 保留导入以兼容历史 monkeypatch 测试路径
from app.services.orchestration.persistence_coordinator import PersistenceCoordinator
from app.services.orchestration.stage_orchestrator import StageOrchestrator
from app.services.session_store import get_session

__all__ = ["AgentService", "agent_service", "rag_service"]


class AgentService:
    """
    多轮会话编排服务

    阶段A（start）: 诊断 + 讲解
    阶段B（explained）: 复述检测 + 追问
    阶段C（followup_generated）: 总结
    """

    @staticmethod
    def _parse_json_text(raw: str) -> dict:
        return ContextBuilder.parse_json_text(raw)

    @staticmethod
    def _detect_topic(user_input: str, current_topic: str | None) -> dict:
        return ContextBuilder.detect_topic(user_input, current_topic)

    @staticmethod
    def _apply_replan(state: LearningState) -> LearningState:
        state["current_plan"] = create_or_update_plan(state)
        state["current_step_index"] = 0
        state["need_replan"] = False
        state["replan_reason"] = ""
        plan = state["current_plan"]
        next_step = ""
        steps = plan.get("steps", [])
        if isinstance(steps, list) and steps:
            first = steps[0]
            if isinstance(first, dict):
                next_step = str(first.get("description") or first.get("name") or "")
        state["next_stage"] = "start"
        state["reply"] = (
            "已根据你的新输入完成重规划。\n"
            f"当前目标：{plan.get('goal', '未设置')}\n"
            f"下一步建议：{next_step or '继续描述你的学习目标或直接提问'}"
        )
        state["stage"] = "planned"
        append_branch_trace(
            state,
            {
                "phase": "planner",
                "action": "replan",
                "goal": state["current_plan"]["goal"],
                "next_stage": "start",
                "next_step": next_step,
            },
        )
        return state

    @staticmethod
    def _snapshot_topic_segment(state: LearningState) -> dict:
        return ContextBuilder.snapshot_topic_segment(state)

    @staticmethod
    def _build_topic_context(state: LearningState, max_segments: int = 3) -> str:
        return ContextBuilder.build_topic_context(state, max_segments=max_segments)

    @staticmethod
    def _build_long_term_context(topic: str | None, user_input: str, user_id: int | None) -> str:
        if not topic:
            return ""
        memory = get_topic_long_term_memory(topic, user_id=user_id)
        lines: list[str] = []
        if memory.get("last_stuck_point"):
            lines.append(f"上次卡点：{memory['last_stuck_point']}")

        common_errors = memory.get("common_errors", [])[:3]
        if common_errors:
            lines.append("常见错误：" + "；".join(f"{x['label']}({x['count']})" for x in common_errors))

        trend = memory.get("mastery_trend", [])
        if trend:
            last = trend[-1]
            lines.append(f"最近掌握度：{last.get('level', 'unknown')} ({last.get('score', 0)})")

        personal_hits = retrieve_personal_memory(topic=topic, query=user_input, limit=2, user_id=user_id)
        if personal_hits:
            snippets = " | ".join(x["content"][:80] for x in personal_hits if x.get("content"))
            if snippets:
                lines.append(f"个人RAG记忆：{snippets}")
        return "\n".join(lines)

    @staticmethod
    def _build_rag_context(
        topic: str | None,
        user_input: str,
        user_id: int | None = None,
        tool_route: dict | None = None,
    ) -> tuple[str, list[dict], dict]:
        context, citations, rag_meta = ContextBuilder.build_rag_context(
            topic=topic,
            user_input=user_input,
            user_id=user_id,
            tool_route=tool_route,
        )
        if context or not settings.rag_enabled:
            return context, citations, rag_meta

        # 兼容旧链路：当工具执行未返回结果时，回退到原 rag_service 调用方式。
        rows = rag_service.retrieve(
            query=user_input,
            topic=topic,
            top_k=settings.rag_retrieve_top_k,
        )
        if user_id is not None:
            personal_rows = rag_service.retrieve_scoped(
                query=user_input,
                scope="personal",
                user_id=str(user_id),
                topic=topic,
                top_k=settings.rag_retrieve_top_k,
            )
            rows = rows + personal_rows
            rows.sort(key=lambda x: float(x.get("score", 0.0)), reverse=True)
            deduped: list[dict] = []
            seen: set[str] = set()
            for row in rows:
                cid = str(row.get("chunk_id", ""))
                if cid and cid in seen:
                    continue
                if cid:
                    seen.add(cid)
                deduped.append(row)
                if len(deduped) >= max(1, int(settings.rag_retrieve_top_k)):
                    break
            rows = deduped
        if not rows:
            return "", [], {
                "rag_attempted": True,
                "rag_skip_reason": "legacy_fallback_empty",
                "rag_used_tools": [],
                "rag_hit_count": 0,
                "rag_fallback_used": True,
            }

        lines: list[str] = []
        legacy_citations: list[dict] = []
        for idx, row in enumerate(rows, start=1):
            snippet = str(row.get("text", "")).strip()
            lines.append(f"[证据{idx}] {snippet[:180]}")
            legacy_citations.append(
                {
                    "chunk_id": row.get("chunk_id"),
                    "source_type": row.get("source_type"),
                    "title": row.get("title"),
                    "source_uri": row.get("source_uri"),
                    "chapter": row.get("chapter"),
                    "page_no": row.get("page_no"),
                    "image_id": row.get("image_id"),
                    "scope": row.get("scope", "global"),
                    "user_id": row.get("user_id"),
                    "snippet": snippet[:180],
                    "score": row.get("score", 0.0),
                    "lexical_score": row.get("lexical_score"),
                    "bm25_score": row.get("bm25_score"),
                    "vector_score": row.get("vector_score"),
                    "rrf_score": row.get("rrf_score"),
                    "rrf_bm25": row.get("rrf_bm25"),
                    "rrf_dense": row.get("rrf_dense"),
                    "hybrid_score": row.get("hybrid_score"),
                    "rerank_score": row.get("rerank_score"),
                }
            )
        return "[知识检索]\n" + "\n".join(lines), legacy_citations, {
            "rag_attempted": True,
            "rag_skip_reason": "",
            "rag_used_tools": [],
            "rag_hit_count": len(legacy_citations),
            "rag_fallback_used": True,
        }

    def run(
        self,
        session_id: str,
        topic: str | None,
        user_input: str,
        user_id: int | None = None,
        stream_output: bool = False,
    ) -> LearningState:
        route = route_intent(user_input)
        existing = get_session(session_id)
        current_topic = topic if existing is None else existing.get("topic")
        topic_eval = self._detect_topic(user_input, current_topic)
        resolved_topic = topic_eval["topic"] or current_topic or topic

        if existing is None:
            tool_route = route_tool(user_input, user_id=user_id)
            state: LearningState = {
                "session_id": session_id,
                "user_id": user_id,
                "topic": resolved_topic,
                "user_input": user_input,
                "stream_output": stream_output,
                "stage": "start",
                "history": [f"用户: {user_input}"],
                "intent": route.intent,
                "intent_confidence": route.confidence,
                "tool_route": {
                    "tool": tool_route.tool,
                    "confidence": tool_route.confidence,
                    "reason": tool_route.reason,
                    "candidates": tool_route.candidates,
                },
                "current_plan": create_or_update_plan(
                    {"session_id": session_id, "topic": resolved_topic, "user_input": user_input}
                ),
                "current_step_index": 0,
                "need_replan": False,
                "replan_reason": "",
                "branch_trace": [],
                "topic_confidence": topic_eval["confidence"],
                "topic_changed": bool(topic_eval["topic"]),
                "topic_reason": topic_eval["reason"],
                "comparison_mode": topic_eval["comparison_mode"],
                "topic_segments": [],
                "topic_context": "",
            }
            append_branch_trace(
                state,
                {
                    "phase": "topic",
                    "topic": resolved_topic,
                    "changed": topic_eval["changed"],
                    "confidence": topic_eval["confidence"],
                    "reason": topic_eval["reason"],
                    "comparison_mode": topic_eval["comparison_mode"],
                },
            )
            append_branch_trace(
                state,
                {
                    "phase": "router",
                    "intent": route.intent,
                    "confidence": route.confidence,
                    "reason": route.reason,
                },
            )
            append_branch_trace(
                state,
                {
                    "phase": "tool_router",
                    "tool": tool_route.tool,
                    "confidence": tool_route.confidence,
                    "reason": tool_route.reason,
                    "candidates": tool_route.candidates,
                },
            )
            long_context = self._build_long_term_context(
                state.get("topic"),
                user_input,
                user_id=state.get("user_id"),
            )
            rag_context, citations, rag_meta = self._build_rag_context(
                state.get("topic"),
                user_input,
                state.get("user_id"),
                state.get("tool_route"),
            )
            context_parts = []
            if long_context:
                context_parts.append(f"[长期记忆]\n{long_context}")
            if rag_context:
                context_parts.append(rag_context)
            state["topic_context"] = "\n\n".join(context_parts)
            state["citations"] = citations
            state["rag_attempted"] = rag_meta.get("rag_attempted", False)
            state["rag_skip_reason"] = rag_meta.get("rag_skip_reason", "")
            state["rag_used_tools"] = rag_meta.get("rag_used_tools", [])
            state["rag_hit_count"] = rag_meta.get("rag_hit_count", 0)
            state["rag_fallback_used"] = rag_meta.get("rag_fallback_used", False)
            append_branch_trace(state, {"phase": "rag", **rag_meta})
            if route.intent == "replan":
                state = self._apply_replan(state)
                PersistenceCoordinator.save_state(session_id, state)
                return state
            result = StageOrchestrator.run_initial(state)
            step_eval = evaluate_step_result(result)
            result["need_replan"] = step_eval["need_replan"]
            result["replan_reason"] = step_eval["reason"] if step_eval["need_replan"] else ""
            result["current_step_index"] = 1 if step_eval["success"] else 0
            append_branch_trace(result, {"phase": "critic", **step_eval})
            result["history"] = result.get("history", []) + [f"助手: {result.get('reply', '')}"]
            PersistenceCoordinator.save_state(session_id, result)
            return result

        # 已有会话：覆盖本轮输入
        state = existing.copy()
        state["stream_output"] = stream_output
        existing_user_id = state.get("user_id")
        if existing_user_id is None and user_id is not None:
            state["user_id"] = user_id
        elif user_id is not None and existing_user_id is not None and int(existing_user_id) != int(user_id):
            raise ValueError("当前会话已绑定其他用户，请创建新会话后重试。")
        elif "user_id" not in state:
            state["user_id"] = None
        tool_route = route_tool(user_input, user_id=state.get("user_id"))
        state["user_input"] = user_input
        state["history"] = state.get("history", []) + [f"用户: {user_input}"]
        old_topic = state.get("topic")
        new_topic = topic_eval["topic"] or old_topic
        state["topic_confidence"] = topic_eval["confidence"]
        state["topic_changed"] = bool(old_topic and new_topic != old_topic) or (old_topic is None and new_topic is not None)
        state["topic_reason"] = topic_eval["reason"]
        state["comparison_mode"] = topic_eval["comparison_mode"]
        if not isinstance(state.get("topic_segments"), list):
            state["topic_segments"] = []
        if state["topic_changed"]:
            # 先快照旧主题上下文，再切换到新主题，避免片段被新主题污染
            state["topic_segments"].append(self._snapshot_topic_segment(state))
        state["topic"] = new_topic
        if state["topic_changed"]:
            # 主题切换后同步更新计划，保证后续多轮对话围绕新主题展开
            if isinstance(state.get("current_plan"), dict):
                state["current_plan"]["goal"] = f"帮助用户掌握: {state.get('topic') or '当前主题'}"
                state["current_plan"]["context"] = user_input
            else:
                state["current_plan"] = create_or_update_plan(state)
        short_context = self._build_topic_context(state)
        long_context = self._build_long_term_context(
            state.get("topic"),
            user_input,
            user_id=state.get("user_id"),
        )
        state["tool_route"] = {
            "tool": tool_route.tool,
            "confidence": tool_route.confidence,
            "reason": tool_route.reason,
            "candidates": tool_route.candidates,
        }
        rag_context, citations, rag_meta = self._build_rag_context(
            state.get("topic"),
            user_input,
            state.get("user_id"),
            state.get("tool_route"),
        )
        context_parts = []
        if short_context:
            context_parts.append(short_context)
        if long_context:
            context_parts.append(f"[长期记忆]\n{long_context}")
        if rag_context:
            context_parts.append(rag_context)
        state["topic_context"] = "\n\n".join(context_parts)
        state["citations"] = citations
        state["rag_attempted"] = rag_meta.get("rag_attempted", False)
        state["rag_skip_reason"] = rag_meta.get("rag_skip_reason", "")
        state["rag_used_tools"] = rag_meta.get("rag_used_tools", [])
        state["rag_hit_count"] = rag_meta.get("rag_hit_count", 0)
        state["rag_fallback_used"] = rag_meta.get("rag_fallback_used", False)
        append_branch_trace(state, {"phase": "rag", **rag_meta})
        append_branch_trace(
            state,
            {
                "phase": "topic",
                "topic": state.get("topic"),
                "changed": state["topic_changed"],
                "confidence": topic_eval["confidence"],
                "reason": topic_eval["reason"],
                "comparison_mode": topic_eval["comparison_mode"],
            },
        )
        state["intent"] = route.intent
        state["intent_confidence"] = route.confidence
        append_branch_trace(
            state,
            {
                "phase": "router",
                "intent": route.intent,
                "confidence": route.confidence,
                "reason": route.reason,
            },
        )
        append_branch_trace(
            state,
            {
                "phase": "tool_router",
                "tool": tool_route.tool,
                "confidence": tool_route.confidence,
                "reason": tool_route.reason,
                "candidates": tool_route.candidates,
            },
        )

        if route.intent == "replan":
            state = self._apply_replan(state)
            PersistenceCoordinator.save_state(session_id, state)
            return state

        if route.intent == "qa_direct":
            # QA直答：切入 qa_subgraph，返回后保持原阶段，便于下一轮回到主线
            result = StageOrchestrator.run_qa_direct(state)
            append_branch_trace(
                result,
                {
                    "phase": "executor",
                    "mode": "qa_direct",
                    "stage_kept": result.get("stage"),
                },
            )
            PersistenceCoordinator.save_state(session_id, result)
            return result

        if state.get("topic_changed"):
            # 教学主线中主题切换：重置教学上下文并从新主题重新讲解
            for key in ["diagnosis", "explanation", "restatement_eval", "followup_question", "summary"]:
                state.pop(key, None)
            state["stage"] = "start"
            state["current_step_index"] = 0
            state["stream_output"] = stream_output
            append_branch_trace(
                state,
                {
                    "phase": "topic",
                    "action": "reset_for_new_topic",
                    "next_stage": "start",
                },
            )
            result = StageOrchestrator.run_initial(state)
            step_eval = evaluate_step_result(result)
            result["need_replan"] = step_eval["need_replan"]
            result["replan_reason"] = step_eval["reason"] if step_eval["need_replan"] else ""
            result["current_step_index"] = 1 if step_eval["success"] else 0
            append_branch_trace(result, {"phase": "critic", **step_eval})
            result["history"] = result.get("history", []) + [f"助手: {result.get('reply', '')}"]
            PersistenceCoordinator.save_state(session_id, result)
            return result

        current_stage = state.get("stage")
        if stream_output and current_stage == "explained":
            state["stream_output"] = False
        if current_stage == "explained":
            result = StageOrchestrator.run_restate(state)
        elif current_stage == "followup_generated":
            if stream_output:
                state["stream_output"] = False
            result = StageOrchestrator.run_summary(state)
        else:
            # 异常状态回退到初始阶段，保证可继续使用
            fallback_state: LearningState = {
                "session_id": session_id,
                "user_id": state.get("user_id"),
                "topic": state.get("topic") or topic,
                "user_input": user_input,
                "stream_output": stream_output,
                "stage": "start",
                "history": state.get("history", []),
                "intent": route.intent,
                "intent_confidence": route.confidence,
                "current_plan": state.get("current_plan") or create_or_update_plan(state),
                "current_step_index": 0,
                "need_replan": False,
                "replan_reason": "",
                "branch_trace": state.get("branch_trace", []),
                "topic_confidence": state.get("topic_confidence", 0.0),
                "topic_changed": state.get("topic_changed", False),
                "topic_reason": state.get("topic_reason", ""),
                "comparison_mode": state.get("comparison_mode", False),
                "topic_segments": state.get("topic_segments", []),
                "topic_context": state.get("topic_context", ""),
            }
            result = StageOrchestrator.run_initial(fallback_state)

        step_eval = evaluate_step_result(result)
        result["need_replan"] = step_eval["need_replan"]
        result["replan_reason"] = step_eval["reason"] if step_eval["need_replan"] else ""
        if step_eval["success"]:
            result["current_step_index"] = int(result.get("current_step_index", 0)) + 1
        append_branch_trace(result, {"phase": "critic", **step_eval})

        result["history"] = result.get("history", []) + [f"助手: {result.get('reply', '')}"]
        PersistenceCoordinator.save_state(session_id, result)
        return result


agent_service = AgentService()
