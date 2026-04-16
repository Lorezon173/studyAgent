from __future__ import annotations

from typing import Literal, TypedDict
from uuid import uuid4

from app.services.agent_runtime import route_intent, route_tool


IntentType = Literal["teach_loop", "qa_direct", "review", "replan"]
RAGScope = Literal["global", "personal", "both", "web", "none"]
SUPPORTED_INTENTS: set[IntentType] = {"teach_loop", "qa_direct", "review", "replan"}


class DecisionContract(TypedDict):
    decision_id: str
    intent: IntentType
    intent_confidence: float
    reason: str
    need_rag: bool
    rag_scope: RAGScope
    tool_plan: list[str]
    fallback_policy: str


class DecisionOrchestrator:
    @staticmethod
    def _resolve_rag_scope(need_rag: bool, tool: str, user_id: int | None) -> RAGScope:
        if not need_rag:
            return "none"

        if tool == "search_web":
            return "web"
        if tool == "search_personal_memory":
            return "personal"
        if tool == "search_local_textbook":
            return "both" if user_id is not None else "global"
        return "both" if user_id is not None else "global"

    @staticmethod
    def decide(
        user_input: str,
        topic: str | None,
        user_id: int | None,
        current_stage: str,
    ) -> DecisionContract:
        intent_route = route_intent(user_input)
        tool_route = route_tool(user_input, user_id=user_id)
        intent: IntentType = (
            intent_route.intent if intent_route.intent in SUPPORTED_INTENTS else "teach_loop"
        )

        reason = intent_route.reason
        if intent != intent_route.intent:
            reason = f"{reason}; fallback_to=teach_loop(unsupported_intent={intent_route.intent})"
        reason = f"{reason}; context(topic={topic or 'unknown'},stage={current_stage or 'unknown'})"

        need_rag = {
            "teach_loop": True,
            "qa_direct": False,
            "review": False,
            "replan": False,
        }[intent]
        tool_plan = [tool_route.tool] if need_rag else []
        rag_scope = DecisionOrchestrator._resolve_rag_scope(need_rag, tool_route.tool, user_id)

        return {
            "decision_id": str(uuid4()),
            "intent": intent,
            "intent_confidence": intent_route.confidence,
            "reason": reason,
            "need_rag": need_rag,
            "rag_scope": rag_scope,
            "tool_plan": tool_plan,
            "fallback_policy": "no_evidence_template",
        }
