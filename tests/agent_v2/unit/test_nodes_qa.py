"""QA 节点单元测试。"""
import pytest
from dataclasses import dataclass
from app.agent.nodes.qa import (
    rag_first_node,
    rag_answer_node,
    llm_answer_node,
    knowledge_retrieval_node,
)
from app.agent.state import LearningState


@dataclass
class FakeRAGCallDecision:
    should_call: bool
    reason: str


@dataclass
class FakeRAGExecutionMeta:
    reason: str = "test"
    used_tools: list = None
    hit_count: int = 0
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


class TestRagFirstNode:
    def test_rag_first_disabled(self, monkeypatch):
        monkeypatch.setattr("app.agent.nodes.qa.decide_rag_call",
                          lambda **kw: FakeRAGCallDecision(should_call=False, reason="rag_disabled"))

        state: LearningState = {
            "user_input": "test",
            "topic": "test",
        }
        result = rag_first_node(state)

        assert result["rag_found"] is False

    def test_rag_first_retrieves(self, monkeypatch):
        monkeypatch.setattr("app.agent.nodes.qa.decide_rag_call",
                          lambda **kw: FakeRAGCallDecision(should_call=True, reason="enabled"))

        def fake_execute_rag(**kwargs):
            rows = [
                {"text": "二分查找是一种算法", "score": 0.9, "source": "local"},
            ]
            meta = FakeRAGExecutionMeta(hit_count=1)
            return rows, meta

        monkeypatch.setattr("app.agent.nodes.qa.execute_rag", fake_execute_rag)

        state: LearningState = {
            "user_input": "什么是二分查找？",
            "topic": "二分查找",
        }
        result = rag_first_node(state)

        assert result["rag_found"] is True

    def test_rag_first_no_results(self, monkeypatch):
        monkeypatch.setattr("app.agent.nodes.qa.decide_rag_call",
                          lambda **kw: FakeRAGCallDecision(should_call=True, reason="enabled"))

        def fake_execute_rag(**kwargs):
            return [], FakeRAGExecutionMeta(hit_count=0)

        monkeypatch.setattr("app.agent.nodes.qa.execute_rag", fake_execute_rag)

        state: LearningState = {
            "user_input": "什么是xyz？",
            "topic": "xyz",
        }
        result = rag_first_node(state)

        assert result["rag_found"] is False


class TestRagAnswerNode:
    def test_rag_answer_uses_context(self, monkeypatch):
        captured = {}

        def fake_invoke(system_prompt, user_prompt, stream_output=False):
            captured["user_prompt"] = user_prompt
            return "根据检索结果，二分查找是..."

        monkeypatch.setattr("app.services.llm.llm_service.invoke", fake_invoke)

        state: LearningState = {
            "user_input": "什么是二分查找？",
            "rag_context": "二分查找是一种在有序数组中查找的算法",
            "rag_citations": [{"chunk_id": "c1"}]
        }
        result = rag_answer_node(state)

        assert "reply" in result
        assert "有序数组" in captured["user_prompt"]

    def test_rag_answer_includes_citations(self, monkeypatch):
        def fake_invoke(system_prompt, user_prompt, stream_output=False):
            return "回答内容"

        monkeypatch.setattr("app.services.llm.llm_service.invoke", fake_invoke)

        state: LearningState = {
            "user_input": "test",
            "rag_context": "context",
            "rag_citations": [{"source": "教材", "title": "教材"}]
        }
        result = rag_answer_node(state)

        assert result["stage"] == "rag_answered"


class TestLlmAnswerNode:
    def test_llm_answer_without_rag(self, monkeypatch):
        def fake_invoke(system_prompt, user_prompt, stream_output=False):
            return "纯 LLM 回答内容"

        monkeypatch.setattr("app.services.llm.llm_service.invoke", fake_invoke)

        state: LearningState = {
            "user_input": "什么是二分查找？",
            "topic": "二分查找",
            "rag_found": False
        }
        result = llm_answer_node(state)

        assert "reply" in result
        assert result["stage"] == "llm_answered"


class TestKnowledgeRetrievalNode:
    def test_knowledge_retrieval_disabled(self, monkeypatch):
        monkeypatch.setattr("app.agent.nodes.qa.decide_rag_call",
                          lambda **kw: FakeRAGCallDecision(should_call=False, reason="rag_disabled"))

        state: LearningState = {
            "user_input": "test",
            "topic": "test",
        }
        result = knowledge_retrieval_node(state)

        assert result["retrieved_context"] == ""

    def test_knowledge_retrieval_enriches_context(self, monkeypatch):
        monkeypatch.setattr("app.agent.nodes.qa.decide_rag_call",
                          lambda **kw: FakeRAGCallDecision(should_call=True, reason="enabled"))

        def fake_execute_rag(**kwargs):
            rows = [
                {"content": "补充知识：时间复杂度 O(log n)", "score": 0.9, "source": "local"},
            ]
            meta = FakeRAGExecutionMeta(hit_count=1)
            return rows, meta

        monkeypatch.setattr("app.agent.nodes.qa.execute_rag", fake_execute_rag)

        state: LearningState = {
            "user_input": "二分查找",
            "topic": "二分查找",
            "diagnosis": "需要补充时间复杂度知识"
        }
        result = knowledge_retrieval_node(state)

        assert "retrieved_context" in result
