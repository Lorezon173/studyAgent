import sys
import types

text_splitter_module = types.ModuleType("langchain.text_splitter")
text_splitter_module.RecursiveCharacterTextSplitter = type("RecursiveCharacterTextSplitter", (), {})
langchain_module = types.ModuleType("langchain")
langchain_module.text_splitter = text_splitter_module
sys.modules.setdefault("langchain", langchain_module)
sys.modules.setdefault("langchain.text_splitter", text_splitter_module)

from app.services.decision_orchestrator import DecisionOrchestrator
from app.services.orchestration.context_builder import ContextBuilder
from app.services.rag_coordinator import RAGExecutionMeta


def _mock_route_intent(intent: str, confidence: float = 0.9, reason: str = "test"):
    return lambda user_input: type("R", (), {"intent": intent, "confidence": confidence, "reason": reason})()


def _mock_route_tool(tool: str = "search_local_textbook"):
    return lambda user_input, user_id=None: type(
        "T", (), {"tool": tool, "confidence": 0.8, "reason": "test", "candidates": [tool]}
    )()


def test_decision_orchestrator_teach_loop_defaults_need_rag(monkeypatch):
    monkeypatch.setattr("app.services.decision_orchestrator.route_intent", _mock_route_intent("teach_loop"))
    monkeypatch.setattr("app.services.decision_orchestrator.route_tool", _mock_route_tool())

    contract = DecisionOrchestrator.decide(
        user_input="解释二分查找",
        topic="二分查找",
        user_id=1,
        current_stage="start",
    )

    assert contract["intent"] == "teach_loop"
    assert contract["need_rag"] is True
    assert contract["rag_scope"] == "both"
    assert contract["tool_plan"] == ["search_local_textbook", "search_personal_memory"]


def test_decision_orchestrator_both_scope_enforces_dual_retrieval_order(monkeypatch):
    monkeypatch.setattr("app.services.decision_orchestrator.route_intent", _mock_route_intent("teach_loop"))
    monkeypatch.setattr("app.services.decision_orchestrator.route_tool", _mock_route_tool("unexpected_tool"))

    contract = DecisionOrchestrator.decide(
        user_input="解释二分查找",
        topic="二分查找",
        user_id=1,
        current_stage="start",
    )

    assert contract["rag_scope"] == "both"
    assert contract["tool_plan"] == ["search_local_textbook", "search_personal_memory"]


def test_decision_orchestrator_qa_direct_can_skip_rag(monkeypatch):
    monkeypatch.setattr("app.services.decision_orchestrator.route_intent", _mock_route_intent("qa_direct"))
    monkeypatch.setattr("app.services.decision_orchestrator.route_tool", _mock_route_tool())

    contract = DecisionOrchestrator.decide(
        user_input="直接回答一下",
        topic="二分查找",
        user_id=1,
        current_stage="explained",
    )

    assert contract["intent"] == "qa_direct"
    assert contract["need_rag"] is False
    assert contract["rag_scope"] == "none"
    assert contract["tool_plan"] == []


def test_decision_orchestrator_review_and_replan_do_not_need_rag(monkeypatch):
    monkeypatch.setattr("app.services.decision_orchestrator.route_tool", _mock_route_tool())

    for intent in ("review", "replan"):
        monkeypatch.setattr("app.services.decision_orchestrator.route_intent", _mock_route_intent(intent))
        contract = DecisionOrchestrator.decide(
            user_input="继续",
            topic="算法",
            user_id=1,
            current_stage="start",
        )
        assert contract["need_rag"] is False
        assert contract["rag_scope"] == "none"
        assert contract["tool_plan"] == []


def test_decision_orchestrator_rag_scope_global_without_user_id(monkeypatch):
    monkeypatch.setattr("app.services.decision_orchestrator.route_intent", _mock_route_intent("teach_loop"))
    monkeypatch.setattr("app.services.decision_orchestrator.route_tool", _mock_route_tool())

    contract = DecisionOrchestrator.decide(
        user_input="解释这个概念",
        topic="算法",
        user_id=None,
        current_stage="start",
    )

    assert contract["need_rag"] is True
    assert contract["rag_scope"] == "global"


def test_decision_orchestrator_rag_scope_web_for_web_search_tool(monkeypatch):
    monkeypatch.setattr("app.services.decision_orchestrator.route_intent", _mock_route_intent("teach_loop"))
    monkeypatch.setattr("app.services.decision_orchestrator.route_tool", _mock_route_tool("search_web"))

    contract = DecisionOrchestrator.decide(
        user_input="查一下最新资料",
        topic="算法",
        user_id=1,
        current_stage="start",
    )

    assert contract["need_rag"] is True
    assert contract["rag_scope"] == "web"
    assert contract["tool_plan"] == ["search_web"]


def test_decision_orchestrator_rag_scope_personal_for_personal_memory_tool(monkeypatch):
    monkeypatch.setattr("app.services.decision_orchestrator.route_intent", _mock_route_intent("teach_loop"))
    monkeypatch.setattr(
        "app.services.decision_orchestrator.route_tool", _mock_route_tool("search_personal_memory")
    )

    contract = DecisionOrchestrator.decide(
        user_input="结合我之前的错题",
        topic="算法",
        user_id=1,
        current_stage="start",
    )

    assert contract["need_rag"] is True
    assert contract["rag_scope"] == "personal"
    assert contract["tool_plan"] == ["search_personal_memory"]


def test_decision_orchestrator_contract_contains_required_fields(monkeypatch):
    monkeypatch.setattr("app.services.decision_orchestrator.route_intent", _mock_route_intent("teach_loop", confidence=0.75, reason="reasoning"))
    monkeypatch.setattr("app.services.decision_orchestrator.route_tool", _mock_route_tool())

    contract = DecisionOrchestrator.decide(
        user_input="解释这个概念",
        topic="算法",
        user_id=None,
        current_stage="start",
    )

    assert contract["decision_id"]
    assert set(
        ["intent", "intent_confidence", "reason", "need_rag", "rag_scope", "tool_plan", "fallback_policy"]
    ).issubset(contract.keys())
    assert contract["intent_confidence"] == 0.75
    assert "reasoning" in contract["reason"]
    assert "topic=算法" in contract["reason"]
    assert "stage=start" in contract["reason"]
    assert contract["fallback_policy"] == "no_evidence_template"


def test_decision_orchestrator_unsupported_intent_falls_back_to_teach_loop(monkeypatch):
    monkeypatch.setattr("app.services.decision_orchestrator.route_intent", _mock_route_intent("unsupported_intent"))
    monkeypatch.setattr("app.services.decision_orchestrator.route_tool", _mock_route_tool())

    contract = DecisionOrchestrator.decide(
        user_input="继续",
        topic="算法",
        user_id=None,
        current_stage="start",
    )

    assert contract["intent"] == "teach_loop"
    assert contract["need_rag"] is True
    assert contract["rag_scope"] == "global"
    assert "fallback_to=teach_loop(unsupported_intent=unsupported_intent)" in contract["reason"]


def test_decision_orchestrator_reason_contains_topic_and_stage_context(monkeypatch):
    monkeypatch.setattr("app.services.decision_orchestrator.route_intent", _mock_route_intent("teach_loop", reason="reasoning"))
    monkeypatch.setattr("app.services.decision_orchestrator.route_tool", _mock_route_tool())

    contract = DecisionOrchestrator.decide(
        user_input="继续",
        topic="二分查找",
        user_id=1,
        current_stage="explained",
    )

    assert "reasoning" in contract["reason"]
    assert "topic=二分查找" in contract["reason"]
    assert "stage=explained" in contract["reason"]


def test_context_builder_skips_when_need_rag_false(monkeypatch):
    def should_not_call_execute_rag(**kwargs):
        raise AssertionError("execute_rag should not be called when need_rag=False")

    monkeypatch.setattr("app.services.orchestration.context_builder.execute_rag", should_not_call_execute_rag)

    context, citations, meta = ContextBuilder.build_rag_context(
        topic="二分查找",
        user_input="直接给答案",
        user_id=1,
        tool_route={"tool": "search_local_textbook"},
        need_rag=False,
    )

    assert context == ""
    assert citations == []
    assert meta["rag_attempted"] is False
    assert meta["rag_skip_reason"] == "decision_orchestrator_skip"


def test_context_builder_propagates_tool_plan_to_retrieval(monkeypatch):
    captured: dict = {}

    def fake_execute_rag(*, query, topic, user_id, tool_route, top_k):
        captured["query"] = query
        captured["topic"] = topic
        captured["user_id"] = user_id
        captured["tool_route"] = tool_route
        captured["top_k"] = top_k
        return (
            [
                {
                    "chunk_id": "c1",
                    "text": "binary search evidence",
                    "score": 0.88,
                    "tool": "search_personal_memory",
                }
            ],
            RAGExecutionMeta(
                reason="tool_retrieval",
                used_tools=["search_personal_memory"],
                hit_count=1,
                fallback_used=False,
            ),
        )

    monkeypatch.setattr("app.services.orchestration.context_builder.execute_rag", fake_execute_rag)

    _, _, meta = ContextBuilder.build_rag_context(
        topic="二分查找",
        user_input="结合我的历史错题解释",
        user_id=7,
        tool_route={"tool": "search_local_textbook"},
        need_rag=True,
        tool_plan=["search_personal_memory"],
    )

    assert captured["tool_route"]["tool_plan"] == ["search_personal_memory"]
    assert meta["rag_attempted"] is True
    assert meta["rag_used_tools"] == ["search_personal_memory"]
