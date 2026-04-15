from app.services.decision_orchestrator import DecisionOrchestrator


def test_decision_orchestrator_teach_loop_defaults_need_rag(monkeypatch):
    monkeypatch.setattr(
        "app.services.decision_orchestrator.route_intent",
        lambda user_input: type("R", (), {"intent": "teach_loop", "confidence": 0.9, "reason": "test"})(),
    )
    monkeypatch.setattr(
        "app.services.decision_orchestrator.route_tool",
        lambda user_input, user_id=None: type(
            "T", (), {"tool": "search_local_textbook", "confidence": 0.8, "reason": "test", "candidates": ["search_local_textbook"]}
        )(),
    )

    contract = DecisionOrchestrator.decide(
        user_input="解释二分查找",
        topic="二分查找",
        user_id=1,
        current_stage="start",
    )

    assert contract["intent"] == "teach_loop"
    assert contract["need_rag"] is True
    assert contract["tool_plan"] == ["search_local_textbook"]


def test_decision_orchestrator_qa_direct_can_skip_rag(monkeypatch):
    monkeypatch.setattr(
        "app.services.decision_orchestrator.route_intent",
        lambda user_input: type("R", (), {"intent": "qa_direct", "confidence": 0.9, "reason": "test"})(),
    )
    monkeypatch.setattr(
        "app.services.decision_orchestrator.route_tool",
        lambda user_input, user_id=None: type(
            "T", (), {"tool": "search_local_textbook", "confidence": 0.8, "reason": "test", "candidates": ["search_local_textbook"]}
        )(),
    )

    contract = DecisionOrchestrator.decide(
        user_input="直接回答一下",
        topic="二分查找",
        user_id=1,
        current_stage="explained",
    )

    assert contract["intent"] == "qa_direct"
    assert contract["need_rag"] is False
    assert contract["tool_plan"] == []


def test_decision_orchestrator_contract_contains_required_fields():
    contract = DecisionOrchestrator.decide(
        user_input="解释这个概念",
        topic="算法",
        user_id=None,
        current_stage="start",
    )
    assert contract["decision_id"]
    assert set(["intent", "need_rag", "rag_scope", "tool_plan", "fallback_policy"]).issubset(contract.keys())
