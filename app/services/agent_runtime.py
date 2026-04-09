from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from app.agent.state import LearningState
from app.services.llm import llm_service


@dataclass
class RouterResult:
    intent: str
    confidence: float
    reason: str


@dataclass
class ToolRouteResult:
    tool: str
    confidence: float
    reason: str
    candidates: list[str]


def route_intent(user_input: str) -> RouterResult:
    llm_result = _route_intent_with_llm(user_input)
    if llm_result is not None:
        return llm_result

    # 回退：规则路由
    return _route_intent_with_rules(user_input)


def _route_intent_with_llm(user_input: str) -> RouterResult | None:
    try:
        raw = llm_service.route_intent(user_input)
        data = json.loads(raw)
        intent = str(data.get("intent", "")).strip()
        confidence = float(data.get("confidence", 0.0))
        reason = str(data.get("reason", "LLM路由决策"))
        if intent not in {"teach_loop", "qa_direct", "review", "replan"}:
            return None
        confidence = max(0.0, min(1.0, confidence))
        return RouterResult(intent=intent, confidence=confidence, reason=reason)
    except Exception:
        return None


def _route_intent_with_rules(user_input: str) -> RouterResult:
    text = user_input.lower()
    if any(k in text for k in ["重规划", "replan", "换个目标", "重新计划", "改目标"]):
        return RouterResult(intent="replan", confidence=0.95, reason="规则回退：检测到显式重规划意图")
    if any(k in text for k in ["总结", "复盘", "回顾", "review"]):
        return RouterResult(intent="review", confidence=0.9, reason="规则回退：检测到复盘意图")
    if any(k in text for k in ["为什么", "怎么", "是什么", "?", "？", "请直接回答", "直接答"]):
        return RouterResult(intent="qa_direct", confidence=0.8, reason="规则回退：检测到直接问答意图")
    return RouterResult(intent="teach_loop", confidence=0.75, reason="规则回退：默认进入教学闭环")


def route_tool(user_input: str, user_id: int | None = None) -> ToolRouteResult:
    text = user_input.lower()

    web_signals = [
        "最新",
        "最近",
        "新闻",
        "联网",
        "官网",
        "release",
        "版本",
        "today",
        "this week",
    ]
    personal_signals = ["我", "我的", "上次", "之前", "错题", "记忆", "薄弱点", "总是错"]

    if any(k in text for k in web_signals):
        return ToolRouteResult(
            tool="search_web",
            confidence=0.9,
            reason="规则路由：检测到时效性/联网信息需求",
            candidates=["search_web", "search_local_textbook"],
        )

    if user_id is not None and any(k in user_input for k in personal_signals):
        return ToolRouteResult(
            tool="search_personal_memory",
            confidence=0.85,
            reason="规则路由：检测到用户私域记忆需求",
            candidates=["search_personal_memory", "search_local_textbook"],
        )

    return ToolRouteResult(
        tool="search_local_textbook",
        confidence=0.75,
        reason="规则路由：默认优先本地教材知识",
        candidates=["search_local_textbook"],
    )


def create_or_update_plan(state: LearningState) -> dict[str, Any]:
    topic = state.get("topic") or "当前主题"
    user_input = state.get("user_input", "")
    steps = [
        {"name": "diagnose_explain", "description": f"诊断并解释 {topic}", "done": False},
        {"name": "check_followup", "description": "检查复述并追问关键漏洞", "done": False},
        {"name": "summarize", "description": "总结并生成复习建议", "done": False},
    ]
    return {
        "goal": f"帮助用户掌握: {topic}",
        "context": user_input,
        "steps": steps,
        "exit_criteria": "完成总结并生成复习建议",
        "fallback_strategy": "当偏离目标或失败时重规划",
    }


def evaluate_step_result(state: LearningState) -> dict[str, Any]:
    stage = state.get("stage")
    if stage == "explained":
        return {"success": True, "done": False, "need_replan": False, "reason": "已完成讲解，进入下一步"}
    if stage == "followup_generated":
        return {"success": True, "done": False, "need_replan": False, "reason": "已追问，等待进一步回答"}
    if stage == "summarized":
        return {"success": True, "done": True, "need_replan": False, "reason": "已完成总结，目标达成"}
    return {"success": False, "done": False, "need_replan": True, "reason": "状态不明确，触发重规划"}


def append_branch_trace(state: LearningState, event: dict[str, Any]) -> None:
    traces = state.get("branch_trace", [])
    traces.append(event)
    state["branch_trace"] = traces
