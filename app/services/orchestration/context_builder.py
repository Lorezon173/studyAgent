import json
import re
from datetime import datetime

from app.agent.state import LearningState
from app.core.config import settings
from app.services.learning_profile_store import get_topic_long_term_memory
from app.services.evidence_policy import evaluate_evidence
from app.services.llm import llm_service
from app.services.personal_rag_store import retrieve_personal_memory
from app.services.rag_coordinator import decide_rag_call, execute_rag


class ContextBuilder:
    @staticmethod
    def parse_json_text(raw: str) -> dict:
        text = raw.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
            text = re.sub(r"\s*```$", "", text)
        data = json.loads(text)
        return data if isinstance(data, dict) else {}

    @staticmethod
    def detect_topic(user_input: str, current_topic: str | None) -> dict:
        try:
            raw = llm_service.detect_topic(user_input, current_topic)
            data = ContextBuilder.parse_json_text(raw)
            topic = data.get("topic")
            if not isinstance(topic, str):
                topic = None
            changed = bool(data.get("changed", False))
            confidence = float(data.get("confidence", 0.0))
            confidence = max(0.0, min(1.0, confidence))
            reason = str(data.get("reason", "LLM主题识别"))
            comparison_mode = bool(data.get("comparison_mode", False))
            return {
                "topic": topic.strip() if topic else None,
                "changed": changed,
                "confidence": confidence,
                "reason": reason,
                "comparison_mode": comparison_mode,
            }
        except Exception:
            return {
                "topic": current_topic,
                "changed": False,
                "confidence": 0.0,
                "reason": "主题识别失败，保持当前主题",
                "comparison_mode": False,
            }

    @staticmethod
    def snapshot_topic_segment(state: LearningState) -> dict:
        return {
            "topic": state.get("topic"),
            "stage": state.get("stage", "unknown"),
            "diagnosis": state.get("diagnosis", ""),
            "explanation": state.get("explanation", ""),
            "restatement_eval": state.get("restatement_eval", ""),
            "followup_question": state.get("followup_question", ""),
            "summary": state.get("summary", ""),
            "timestamp": datetime.now().isoformat(),
        }

    @staticmethod
    def build_topic_context(state: LearningState, max_segments: int = 3) -> str:
        topic = state.get("topic")
        segments = state.get("topic_segments", [])
        if not isinstance(segments, list):
            return ""

        related = [seg for seg in segments if isinstance(seg, dict) and seg.get("topic") == topic]
        related = related[-max_segments:]
        parts: list[str] = []
        for idx, seg in enumerate(related, start=1):
            seg_stage = seg.get("stage", "unknown")
            seg_summary = seg.get("summary") or seg.get("restatement_eval") or seg.get("diagnosis") or ""
            seg_summary = str(seg_summary).strip()
            if seg_summary:
                parts.append(f"[片段{idx}] stage={seg_stage}; 摘要={seg_summary[:180]}")
        return "\n".join(parts)

    @staticmethod
    def build_long_term_context(
        topic: str | None,
        user_input: str,
        user_id: int | None = None,
    ) -> str:
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
    def build_rag_context(
        topic: str | None,
        user_input: str,
        user_id: int | None = None,
        tool_route: dict | None = None,
    ) -> tuple[str, list[dict], dict]:
        decision = decide_rag_call(user_input=user_input)
        if not decision.should_call:
            return "", [], {
                "rag_attempted": False,
                "rag_skip_reason": decision.reason,
                "rag_used_tools": [],
                "rag_hit_count": 0,
                "rag_fallback_used": False,
                "rag_query_mode": "",
                "rag_query_reason": "",
                "rag_confidence_level": "low",
                "rag_low_evidence": True,
                "rag_avg_score": 0.0,
            }

        rows, meta = execute_rag(
            query=user_input,
            topic=topic,
            user_id=user_id,
            tool_route=tool_route,
            top_k=max(1, int(settings.rag_retrieve_top_k)),
        )
        if not rows:
            return "", [], {
                "rag_attempted": True,
                "rag_skip_reason": meta.reason,
                "rag_used_tools": meta.used_tools,
                "rag_hit_count": 0,
                "rag_fallback_used": meta.fallback_used,
                "rag_query_mode": meta.query_mode,
                "rag_query_reason": meta.query_reason,
                "rag_confidence_level": "low",
                "rag_low_evidence": True,
                "rag_avg_score": 0.0,
            }

        assessment = evaluate_evidence(rows)
        lines: list[str] = []
        citations: list[dict] = []
        source_tag = f"[知识检索|tools={','.join(meta.used_tools)}]" if meta.used_tools else "[知识检索]"
        for idx, row in enumerate(rows, start=1):
            snippet = str(row.get("text", "")).strip()
            lines.append(f"[证据{idx}] {snippet[:180]}")
            citations.append(
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
                    "tool": row.get("tool"),
                }
            )
        return source_tag + "\n" + "\n".join(lines), citations, {
            "rag_attempted": True,
            "rag_skip_reason": "",
            "rag_used_tools": meta.used_tools,
            "rag_hit_count": len(rows),
            "rag_fallback_used": meta.fallback_used,
            "rag_query_mode": meta.query_mode,
            "rag_query_reason": meta.query_reason,
            "rag_confidence_level": assessment.level,
            "rag_low_evidence": assessment.low_evidence,
            "rag_avg_score": assessment.avg_score,
        }

