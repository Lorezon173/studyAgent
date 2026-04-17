import sys
import types

text_splitter_module = types.ModuleType("langchain.text_splitter")
text_splitter_module.RecursiveCharacterTextSplitter = type("RecursiveCharacterTextSplitter", (), {})
langchain_module = types.ModuleType("langchain")
langchain_module.text_splitter = text_splitter_module
sys.modules.setdefault("langchain", langchain_module)
sys.modules.setdefault("langchain.text_splitter", text_splitter_module)

from app.services.agent_service import AgentService


def test_single_turn_records_decision_trace_and_teach_loop_rag_contract(monkeypatch):
    captured: dict = {}
    decision_contract = {
        "decision_id": "d-1",
        "intent": "teach_loop",
        "intent_confidence": 0.91,
        "reason": "test reason",
        "need_rag": True,
        "rag_scope": "both",
        "tool_plan": ["search_local_textbook"],
        "fallback_policy": "no_evidence_template",
    }

    monkeypatch.setattr("app.services.agent_service.get_session", lambda session_id: None)
    monkeypatch.setattr(
        "app.services.decision_orchestrator.DecisionOrchestrator.decide",
        lambda user_input, topic, user_id, current_stage: decision_contract,
    )
    monkeypatch.setattr(
        "app.services.agent_service.AgentService._detect_topic",
        staticmethod(
            lambda user_input, current_topic: {
                "topic": "二分查找",
                "changed": False,
                "confidence": 0.8,
                "reason": "test",
                "comparison_mode": False,
            }
        ),
    )
    monkeypatch.setattr(
        "app.services.agent_service.AgentService._build_long_term_context",
        staticmethod(lambda topic, user_input, user_id=None: ""),
    )

    def fake_build_rag_context(topic, user_input, user_id=None, tool_route=None, need_rag=True, tool_plan=None):
        captured["need_rag"] = need_rag
        captured["tool_plan"] = tool_plan
        return "", [], {
            "rag_attempted": False,
            "rag_skip_reason": "",
            "rag_used_tools": [],
            "rag_hit_count": 0,
            "rag_fallback_used": False,
        }

    monkeypatch.setattr("app.services.agent_service.AgentService._build_rag_context", staticmethod(fake_build_rag_context))
    monkeypatch.setattr(
        "app.services.agent_service.create_or_update_plan",
        lambda state: {"goal": "g", "steps": []},
    )
    monkeypatch.setattr(
        "app.services.agent_service.StageOrchestrator.run_initial",
        staticmethod(lambda state: {**state, "stage": "explained", "reply": "ok"}),
    )
    monkeypatch.setattr(
        "app.services.agent_service.evaluate_step_result",
        lambda state: {"success": True, "done": False, "need_replan": False, "reason": "ok"},
    )
    monkeypatch.setattr(
        "app.services.agent_service.PersistenceCoordinator.save_state",
        staticmethod(lambda session_id, state: None),
    )

    result = AgentService().run(
        session_id="s-1",
        topic="二分查找",
        user_input="请解释二分查找",
        user_id=7,
    )

    assert result["decision_id"] == "d-1"
    assert result["decision_contract"] == decision_contract
    assert result["intent"] == "teach_loop"
    assert result["intent_confidence"] == 0.91
    assert result["need_rag"] is True
    assert result["rag_scope"] == "both"
    assert result["tool_plan"] == ["search_local_textbook"]
    assert result["fallback_policy"] == "no_evidence_template"
    assert result["decision_contract"]["need_rag"] == result["need_rag"]
    assert result["decision_contract"]["tool_plan"] == result["tool_plan"]
    assert captured["need_rag"] is True
    assert captured["tool_plan"] == ["search_local_textbook"]
    decision_events = [
        event for event in result.get("branch_trace", []) if event.get("phase") == "decision_orchestrator"
    ]
    assert len(decision_events) == 1
    assert decision_events[0].get("decision_id") == "d-1"
    assert decision_events[0].get("intent") == "teach_loop"
    assert decision_events[0].get("need_rag") is True


def test_existing_session_second_turn_keeps_one_decision_event_per_turn(monkeypatch):
    session_store: dict = {}
    first_contract = {
        "decision_id": "d-1",
        "intent": "teach_loop",
        "intent_confidence": 0.89,
        "reason": "first turn",
        "need_rag": True,
        "rag_scope": "both",
        "tool_plan": ["search_local_textbook"],
        "fallback_policy": "no_evidence_template",
    }
    second_contract = {
        "decision_id": "d-2",
        "intent": "teach_loop",
        "intent_confidence": 0.92,
        "reason": "second turn",
        "need_rag": False,
        "rag_scope": "none",
        "tool_plan": [],
        "fallback_policy": "ask_clarify_then_retry",
    }
    decisions = iter([first_contract, second_contract])

    monkeypatch.setattr("app.services.agent_service.get_session", lambda session_id: session_store.get(session_id))
    monkeypatch.setattr(
        "app.services.decision_orchestrator.DecisionOrchestrator.decide",
        lambda user_input, topic, user_id, current_stage: next(decisions),
    )
    monkeypatch.setattr(
        "app.services.agent_service.AgentService._detect_topic",
        staticmethod(
            lambda user_input, current_topic: {
                "topic": "二分查找",
                "changed": False,
                "confidence": 0.8,
                "reason": "test",
                "comparison_mode": False,
            }
        ),
    )
    monkeypatch.setattr(
        "app.services.agent_service.AgentService._build_long_term_context",
        staticmethod(lambda topic, user_input, user_id=None: ""),
    )
    monkeypatch.setattr(
        "app.services.agent_service.AgentService._build_rag_context",
        staticmethod(
            lambda topic, user_input, user_id=None, tool_route=None, need_rag=True, tool_plan=None: (
                "",
                [],
                {
                    "rag_attempted": False,
                    "rag_skip_reason": "",
                    "rag_used_tools": [],
                    "rag_hit_count": 0,
                    "rag_fallback_used": False,
                },
            )
        ),
    )
    monkeypatch.setattr(
        "app.services.agent_service.create_or_update_plan",
        lambda state: {"goal": "g", "steps": []},
    )
    monkeypatch.setattr(
        "app.services.agent_service.StageOrchestrator.run_initial",
        staticmethod(lambda state: {**state, "stage": "explained", "reply": "first"}),
    )
    monkeypatch.setattr(
        "app.services.agent_service.StageOrchestrator.run_restate",
        staticmethod(lambda state: {**state, "stage": "followup_generated", "reply": "second"}),
    )
    monkeypatch.setattr(
        "app.services.agent_service.PersistenceCoordinator.save_state",
        staticmethod(lambda session_id, state: session_store.__setitem__(session_id, state.copy())),
    )

    service = AgentService()
    first = service.run(session_id="s-2", topic="二分查找", user_input="第一轮", user_id=99)
    second = service.run(session_id="s-2", topic="二分查找", user_input="第二轮", user_id=99)

    assert first["decision_id"] == "d-1"
    assert second["decision_id"] == "d-2"
    assert second["decision_contract"] == second_contract
    assert second["need_rag"] is False
    assert second["rag_scope"] == "none"
    assert second["tool_plan"] == []
    assert second["fallback_policy"] == "ask_clarify_then_retry"
    assert second["decision_contract"]["need_rag"] == second["need_rag"]
    assert second["decision_contract"]["tool_plan"] == second["tool_plan"]
    decision_events = [
        event for event in second.get("branch_trace", []) if event.get("phase") == "decision_orchestrator"
    ]
    assert [event.get("decision_id") for event in decision_events] == ["d-1", "d-2"]
