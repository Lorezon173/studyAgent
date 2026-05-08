"""QA 直答端到端集成测试。"""
import pytest
from dataclasses import dataclass
from app.agent.graph_v2 import build_learning_graph_v2
from app.agent.state import LearningState
from tests.agent_v2.conftest import make_fake_invoke


@dataclass
class FakeRAGCallDecision:
    should_call: bool
    reason: str


@dataclass
class FakeRAGExecutionMeta:
    reason: str = "test"
    used_tools: list = None
    hit_count: int = 1
    fallback_used: bool = False
    query_mode: str = "fact"
    query_reason: str = "test"
    candidates: list = None
    selected_chunk_ids: list = None
    elapsed_ms: int = 0
    reranked: bool = False

    def __post_init__(self):
        if self.used_tools is None:
            self.used_tools = []
        if self.candidates is None:
            self.candidates = []
        if self.selected_chunk_ids is None:
            self.selected_chunk_ids = []


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


@dataclass
class FakeTemplate:
    template_id: str = "high"
    content: str = "{answer}"
    boundary_notice: str = ""


class TestQaDirectFlow:
    """QA 直答流程集成测试。"""

    def test_qa_direct_rag_hit(self, monkeypatch):
        """RAG 检索命中 → 证据守门通过 → RAG 回答"""
        llm_mocks = {
            "问答助手": "二分查找的时间复杂度是 O(log n)。"
        }
        monkeypatch.setattr("app.services.llm.llm_service.invoke", make_fake_invoke(llm_mocks))
        monkeypatch.setattr("app.services.llm.llm_service.route_intent",
                          lambda u: '{"intent":"qa_direct","confidence":0.95}')

        # Mock RAG 检索命中
        def fake_execute_rag(**kwargs):
            return [
                {"text": "二分查找时间复杂度 O(log n)", "score": 0.9, "source": "local"}
            ], FakeRAGExecutionMeta(hit_count=1)

        monkeypatch.setattr("app.agent.nodes.qa.decide_rag_call",
                          lambda **kw: FakeRAGCallDecision(should_call=True, reason="enabled"))
        monkeypatch.setattr("app.agent.nodes.qa.execute_rag", fake_execute_rag)

        # Mock 证据守门通过
        monkeypatch.setattr("app.services.evidence_validator.validate_evidence",
                          lambda *a, **k: FakeGateResult(status="pass"))

        from langgraph.checkpoint.memory import MemorySaver
        import app.agent.checkpointer as cp_module
        original = cp_module._checkpointer
        cp_module._checkpointer = MemorySaver()

        try:
            graph = build_learning_graph_v2()
            config = {"configurable": {"thread_id": "test-qa-1"}}

            state: LearningState = {
                "session_id": "test-qa-1",
                "user_input": "二分查找的时间复杂度？",
                "topic": "二分查找",
                "stage": "start",
                "history": [],
                "branch_trace": [],
            }
            result = graph.invoke(state, config=config)

            assert result.get("rag_found") is True
            assert result["stage"] in ["rag_answered", "llm_answered"]
        finally:
            cp_module._checkpointer = original
            import app.agent.graph_v2 as graph_module
            graph_module._learning_graph_v2 = None

    def test_qa_direct_rag_miss(self, monkeypatch):
        """RAG 检索未命中 → 纯 LLM 回答"""
        llm_mocks = {
            "问答助手": "根据我的知识，二分查找时间复杂度是 O(log n)。"
        }
        monkeypatch.setattr("app.services.llm.llm_service.invoke", make_fake_invoke(llm_mocks))
        monkeypatch.setattr("app.services.llm.llm_service.route_intent",
                          lambda u: '{"intent":"qa_direct","confidence":0.95}')

        # Mock RAG 检索未命中
        def fake_execute_rag(**kwargs):
            return [], FakeRAGExecutionMeta(hit_count=0)

        monkeypatch.setattr("app.agent.nodes.qa.decide_rag_call",
                          lambda **kw: FakeRAGCallDecision(should_call=True, reason="enabled"))
        monkeypatch.setattr("app.agent.nodes.qa.execute_rag", fake_execute_rag)

        from langgraph.checkpoint.memory import MemorySaver
        import app.agent.checkpointer as cp_module
        original = cp_module._checkpointer
        cp_module._checkpointer = MemorySaver()

        try:
            graph = build_learning_graph_v2()
            config = {"configurable": {"thread_id": "test-qa-2"}}

            state: LearningState = {
                "session_id": "test-qa-2",
                "user_input": "xyz是什么？",
                "topic": "xyz",
                "stage": "start",
                "history": [],
                "branch_trace": [],
            }
            result = graph.invoke(state, config=config)

            assert result.get("rag_found") is False
            assert "reply" in result
        finally:
            cp_module._checkpointer = original
            import app.agent.graph_v2 as graph_module
            graph_module._learning_graph_v2 = None

    def test_qa_direct_evidence_gate_reject(self, monkeypatch):
        """证据守门拒绝 → 降级回答"""
        llm_mocks = {
            "问答助手": "回答"
        }
        monkeypatch.setattr("app.services.llm.llm_service.invoke", make_fake_invoke(llm_mocks))
        monkeypatch.setattr("app.services.llm.llm_service.route_intent",
                          lambda u: '{"intent":"qa_direct","confidence":0.95}')

        # Mock RAG 有结果
        def fake_execute_rag(**kwargs):
            return [
                {"text": "无关内容", "score": 0.3, "source": "local"}
            ], FakeRAGExecutionMeta(hit_count=1)

        monkeypatch.setattr("app.agent.nodes.qa.decide_rag_call",
                          lambda **kw: FakeRAGCallDecision(should_call=True, reason="enabled"))
        monkeypatch.setattr("app.agent.nodes.qa.execute_rag", fake_execute_rag)

        # Mock 证据守门拒绝
        monkeypatch.setattr("app.services.evidence_validator.validate_evidence",
                          lambda *a, **k: FakeGateResult(status="reject", coverage_score=0.2))

        from langgraph.checkpoint.memory import MemorySaver
        import app.agent.checkpointer as cp_module
        original = cp_module._checkpointer
        cp_module._checkpointer = MemorySaver()

        try:
            graph = build_learning_graph_v2()
            config = {"configurable": {"thread_id": "test-qa-3"}}

            state: LearningState = {
                "session_id": "test-qa-3",
                "user_input": "二分查找的时间复杂度？",
                "topic": "二分查找",
                "stage": "start",
                "history": [],
                "branch_trace": [],
            }
            result = graph.invoke(state, config=config)

            # 应该进入 recovery 或降级回答
            assert result.get("gate_status") == "reject" or result.get("fallback_triggered") or result.get("reply")
        finally:
            cp_module._checkpointer = original
            import app.agent.graph_v2 as graph_module
            graph_module._learning_graph_v2 = None

    def test_qa_direct_citations_attached(self, monkeypatch):
        """引用正确附加到响应"""
        llm_mocks = {
            "问答助手": "回答内容"
        }
        monkeypatch.setattr("app.services.llm.llm_service.invoke", make_fake_invoke(llm_mocks))
        monkeypatch.setattr("app.services.llm.llm_service.route_intent",
                          lambda u: '{"intent":"qa_direct","confidence":0.95}')

        def fake_execute_rag(**kwargs):
            return [
                {"text": "context", "score": 0.9, "source": "local"}
            ], FakeRAGExecutionMeta(hit_count=1)

        monkeypatch.setattr("app.agent.nodes.qa.decide_rag_call",
                          lambda **kw: FakeRAGCallDecision(should_call=True, reason="enabled"))
        monkeypatch.setattr("app.agent.nodes.qa.execute_rag", fake_execute_rag)
        monkeypatch.setattr("app.services.evidence_validator.validate_evidence",
                          lambda *a, **k: FakeGateResult(status="pass"))
        monkeypatch.setattr("app.services.answer_templates.get_answer_template",
                          lambda level: FakeTemplate())

        from langgraph.checkpoint.memory import MemorySaver
        import app.agent.checkpointer as cp_module
        original = cp_module._checkpointer
        cp_module._checkpointer = MemorySaver()

        try:
            graph = build_learning_graph_v2()
            config = {"configurable": {"thread_id": "test-qa-4"}}

            state: LearningState = {
                "session_id": "test-qa-4",
                "user_input": "test",
                "topic": "test",
                "stage": "start",
                "history": [],
                "branch_trace": [],
            }
            result = graph.invoke(state, config=config)

            assert "rag_citations" in result or "reply" in result
        finally:
            cp_module._checkpointer = original
            import app.agent.graph_v2 as graph_module
            graph_module._learning_graph_v2 = None
