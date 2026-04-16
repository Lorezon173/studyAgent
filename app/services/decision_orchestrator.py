from __future__ import annotations

from typing import Literal, TypedDict
from uuid import uuid4

from app.services.agent_runtime import route_intent, route_tool


IntentType = Literal["teach_loop", "qa_direct", "review", "replan"]
RAGScope = Literal["none", "global", "both"]


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
    def decide(
        user_input: str,
        topic: str | None,
        user_id: int | None,
        current_stage: str,
    ) -> DecisionContract:
        intent_route = route_intent(user_input)
        tool_route = route_tool(user_input, user_id=user_id)

        need_rag = {
            "teach_loop": True,
            "qa_direct": False,
            "review": False,
            "replan": False,
        }.get(intent_route.intent, True)
        tool_plan = [tool_route.tool] if need_rag else []
        if not need_rag:
            rag_scope: RAGScope = "none"
        elif user_id is not None:
            rag_scope = "both"
        else:
            rag_scope = "global"

        return {
            "decision_id": str(uuid4()),
            "intent": intent_route.intent,
            "intent_confidence": intent_route.confidence,
            "reason": intent_route.reason,
            "need_rag": need_rag,
            "rag_scope": rag_scope,
            "tool_plan": tool_plan,
            "fallback_policy": "no_evidence_template",
        }
