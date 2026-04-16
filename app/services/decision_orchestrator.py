from __future__ import annotations

from typing import TypedDict, Any
from uuid import uuid4

from app.services.agent_runtime import route_intent, route_tool


class DecisionContract(TypedDict):
    decision_id: str
    intent: str
    need_rag: bool
    rag_scope: str
    tool_plan: list[str]
    fallback_policy: dict[str, Any]


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

        need_rag = intent_route.intent != "qa_direct"
        tool_plan = [tool_route.tool] if need_rag else []
        rag_scope = "topic" if topic else "global"

        return {
            "decision_id": str(uuid4()),
            "intent": intent_route.intent,
            "need_rag": need_rag,
            "rag_scope": rag_scope,
            "tool_plan": tool_plan,
            "fallback_policy": {
                "on_rag_miss": "fallback_to_model_answer",
                "on_stage_mismatch": "continue_from_current_stage",
                "current_stage": current_stage,
            },
        }
