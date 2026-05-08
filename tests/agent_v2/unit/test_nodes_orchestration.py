"""编排节点单元测试。"""
import pytest
from dataclasses import dataclass
from app.agent.nodes.orchestration import (
    intent_router_node,
    replan_node,
    retrieval_planner_node,
    evidence_gate_node,
    answer_policy_node,
    recovery_node,
)
from app.agent.state import LearningState


# ========== intent_router_node ==========

class TestIntentRouterNode:
    def test_intent_router_teach_loop(self, monkeypatch):
        def fake_route_intent(user_input):
            return '{"intent": "teach_loop", "confidence": 0.95, "reason": "教学意图"}'
        monkeypatch.setattr("app.services.llm.llm_service.route_intent", fake_route_intent)

        state: LearningState = {"user_input": "我想学二分查找"}
        result = intent_router_node(state)

        assert result["intent"] == "teach_loop"
        assert result["intent_confidence"] == 0.95

    def test_intent_router_qa_direct(self, monkeypatch):
        def fake_route_intent(user_input):
            return '{"intent": "qa_direct", "confidence": 0.9, "reason": "问答意图"}'
        monkeypatch.setattr("app.services.llm.llm_service.route_intent", fake_route_intent)

        state: LearningState = {"user_input": "什么是二分查找？"}
        result = intent_router_node(state)

        assert result["intent"] == "qa_direct"

    def test_intent_router_fallback_on_error(self, monkeypatch):
        def fake_route_intent(user_input):
            raise Exception("LLM error")
        monkeypatch.setattr("app.services.llm.llm_service.route_intent", fake_route_intent)

        state: LearningState = {"user_input": "重规划：我想学哈希表"}
        result = intent_router_node(state)

        # 应使用规则回退
        assert result["intent"] in {"teach_loop", "qa_direct", "replan", "review"}
        assert result["intent_confidence"] == 0.7


# ========== replan_node ==========

class TestReplanNode:
    def test_replan_creates_plan(self, monkeypatch):
        def fake_create_plan(state):
            return {"goal": "学习哈希表", "steps": [{"name": "step1", "description": "了解基本概念"}]}
        monkeypatch.setattr("app.services.agent_runtime.create_or_update_plan", fake_create_plan)

        state: LearningState = {"user_input": "我想学哈希表", "topic": "哈希表"}
        result = replan_node(state)

        assert result["stage"] == "planned"
        assert result["current_plan"]["goal"] == "学习哈希表"
        assert "当前目标" in result["reply"]

    def test_replan_resets_step_index(self, monkeypatch):
        def fake_create_plan(state):
            return {"goal": "test", "steps": []}
        monkeypatch.setattr("app.services.agent_runtime.create_or_update_plan", fake_create_plan)

        state: LearningState = {"user_input": "test", "current_step_index": 5}
        result = replan_node(state)

        assert result["current_step_index"] == 0
        assert result["need_replan"] is False


# ========== retrieval_planner_node ==========

class TestRetrievalPlannerNode:
    def test_retrieval_planner_fact_mode(self, monkeypatch):
        @dataclass
        class FakeQueryPlan:
            mode: str = "fact"
            rewritten_query: str = ""
            top_k: int = 5
            enable_web: bool = False
            reason: str = "事实查询"

        monkeypatch.setattr("app.services.query_planner.build_query_plan",
                          lambda u, t: FakeQueryPlan())
        monkeypatch.setattr("app.services.retrieval_strategy.get_retrieval_strategy",
                          lambda m: {"bm25_weight": 0.4, "vector_weight": 0.6})

        state: LearningState = {"user_input": "二分查找的基本原理", "topic": "二分查找"}
        result = retrieval_planner_node(state)

        assert result["retrieval_mode"] == "fact"
        assert "retrieval_strategy" in result

    def test_retrieval_planner_comparison_mode(self, monkeypatch):
        @dataclass
        class FakeQueryPlan:
            mode: str = "comparison"
            rewritten_query: str = ""
            top_k: int = 5
            enable_web: bool = False
            reason: str = "对比查询"

        monkeypatch.setattr("app.services.query_planner.build_query_plan",
                          lambda u, t: FakeQueryPlan())
        monkeypatch.setattr("app.services.retrieval_strategy.get_retrieval_strategy",
                          lambda m: {"bm25_weight": 0.5, "vector_weight": 0.5})

        state: LearningState = {"user_input": "二分查找和线性查找的区别", "topic": "二分查找"}
        result = retrieval_planner_node(state)

        assert result["retrieval_mode"] == "comparison"


# ========== evidence_gate_node ==========

class TestEvidenceGateNode:
    def test_evidence_gate_no_evidence(self):
        state: LearningState = {"rag_found": False}
        result = evidence_gate_node(state)

        assert result["gate_status"] == "reject"
        assert result["gate_coverage_score"] == 0.0

    def test_evidence_gate_pass(self, monkeypatch):
        @dataclass
        class FakeGateResult:
            status: str = "pass"
            coverage_score: float = 0.85
            conflict_score: float = 0.1
            missing_keywords: list = None
            conflict_pairs: list = None

            def __post_init__(self):
                if self.missing_keywords is None:
                    self.missing_keywords = []
                if self.conflict_pairs is None:
                    self.conflict_pairs = []

        monkeypatch.setattr("app.services.evidence_validator.validate_evidence",
                          lambda *args, **kwargs: FakeGateResult())

        state: LearningState = {
            "rag_found": True,
            "rag_context": "二分查找是 O(log n) 的算法",
            "user_input": "二分查找的复杂度"
        }
        result = evidence_gate_node(state)

        assert result["gate_status"] == "pass"

    def test_evidence_gate_reject_low_coverage(self, monkeypatch):
        @dataclass
        class FakeGateResult:
            status: str = "reject"
            coverage_score: float = 0.3
            conflict_score: float = 0.1
            missing_keywords: list = None
            conflict_pairs: list = None

            def __post_init__(self):
                if self.missing_keywords is None:
                    self.missing_keywords = ["时间复杂度"]
                if self.conflict_pairs is None:
                    self.conflict_pairs = []

        monkeypatch.setattr("app.services.evidence_validator.validate_evidence",
                          lambda *args, **kwargs: FakeGateResult())

        state: LearningState = {
            "rag_found": True,
            "rag_context": "二分查找是一种算法",
            "user_input": "二分查找的时间复杂度"
        }
        result = evidence_gate_node(state)

        assert result["gate_status"] == "reject"


# ========== answer_policy_node ==========

class TestAnswerPolicyNode:
    def test_answer_policy_high_confidence(self, monkeypatch):
        @dataclass
        class FakeTemplate:
            template_id: str = "high"
            content: str = "{answer}"
            boundary_notice: str = ""

        monkeypatch.setattr("app.services.answer_templates.get_answer_template",
                          lambda level: FakeTemplate())

        state: LearningState = {"rag_confidence_level": "high"}
        result = answer_policy_node(state)

        assert result["answer_template_id"] == "high"

    def test_answer_policy_low_confidence_with_notice(self, monkeypatch):
        @dataclass
        class FakeTemplate:
            template_id: str = "low"
            content: str = "{answer}"
            boundary_notice: str = "证据不足，请核实"

        monkeypatch.setattr("app.services.answer_templates.get_answer_template",
                          lambda level: FakeTemplate())

        state: LearningState = {"rag_confidence_level": "low"}
        result = answer_policy_node(state)

        assert result["answer_template_id"] == "low"
        assert result["boundary_notice"] == "证据不足，请核实"


# ========== recovery_node ==========

class TestRecoveryNode:
    def test_recovery_sets_error_code(self):
        state: LearningState = {"node_error": "LLM timeout", "error_code": "llm_timeout"}
        result = recovery_node(state)

        assert result["fallback_triggered"] is True

    def test_recovery_generates_fallback_reply(self):
        state: LearningState = {"node_error": "RAG failure", "error_code": "rag_failure"}
        result = recovery_node(state)

        assert "reply" in result
        assert result["recovery_action"] in ["use_cache", "pure_llm", "suggest_refine", "delay_retry"]
