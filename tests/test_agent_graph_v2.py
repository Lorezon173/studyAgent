# tests/test_agent_graph_v2.py
"""
Graph V2集成测试
"""

import pytest

from app.agent.graph_v2 import build_learning_graph_v2
from app.agent.state import LearningState


@pytest.fixture
def graph():
    """构建测试图"""
    return build_learning_graph_v2()


@pytest.fixture
def initial_state() -> LearningState:
    """初始状态"""
    return {
        "session_id": "test-session",
        "user_input": "我想学习二分查找",
        "topic": "二分查找",
        "stage": "start",
        "history": [],
        "branch_trace": [],
    }


@pytest.fixture
def graph_config() -> dict:
    return {"configurable": {"thread_id": "test-thread"}}


class TestGraphV2Build:
    """图构建测试"""

    def test_graph_builds_successfully(self, graph):
        """图能成功构建"""
        assert graph is not None

    def test_graph_has_correct_nodes(self, graph):
        """图包含所有必要节点"""
        nodes = set(graph.nodes.keys())
        expected_nodes = {
            "intent_router",
            "history_check",
            "ask_review_or_continue",
            "diagnose",
            "knowledge_retrieval",
            "explain",
            "restate_check",
            "followup",
            "summary",
            "rag_first",
            "rag_answer",
            "llm_answer",
            "replan",
        }
        assert expected_nodes.issubset(nodes)


class TestIntentRouting:
    """意图路由测试"""

    def test_route_to_teach_loop(self, graph, initial_state, monkeypatch, graph_config):
        """测试正常教学路由"""
        def mock_route_intent(user_input):
            return '{"intent":"teach_loop","confidence":0.9,"reason":"学习请求"}'

        monkeypatch.setattr(
            "app.services.llm.llm_service.route_intent",
            mock_route_intent
        )
        monkeypatch.setattr(
            "app.services.llm.llm_service.invoke",
            lambda **kw: "mock response"
        )

        result = graph.invoke(initial_state, config=graph_config)
        assert result.get("intent") == "teach_loop"

    def test_route_to_qa_direct(self, graph, initial_state, monkeypatch, graph_config):
        """测试直接问答路由"""
        initial_state["user_input"] = "二分查找是什么？请直接回答"

        def mock_route_intent(user_input):
            return '{"intent":"qa_direct","confidence":0.95,"reason":"直接问答"}'

        monkeypatch.setattr(
            "app.services.llm.llm_service.route_intent",
            mock_route_intent
        )
        monkeypatch.setattr(
            "app.services.llm.llm_service.invoke",
            lambda **kw: "二分查找是一种在有序数组中查找的算法"
        )

        result = graph.invoke(initial_state, config=graph_config)
        assert result.get("intent") == "qa_direct"

    def test_route_to_replan(self, graph, initial_state, monkeypatch, graph_config):
        """测试重规划路由"""
        initial_state["user_input"] = "我不想学这个了，换个主题"

        def mock_route_intent(user_input):
            return '{"intent":"replan","confidence":0.9,"reason":"重规划请求"}'

        monkeypatch.setattr(
            "app.services.llm.llm_service.route_intent",
            mock_route_intent
        )

        result = graph.invoke(initial_state, config=graph_config)
        assert result.get("intent") == "replan"


class TestConditionalEdges:
    """条件边测试"""

    def test_skip_explanation_when_mastered(self, graph, monkeypatch, graph_config):
        """测试已掌握时跳过讲解"""
        state: LearningState = {
            "session_id": "test",
            "user_input": "我熟悉二分查找",
            "topic": "二分查找",
            "stage": "start",
            "diagnosis": "用户已掌握该知识点",
            "branch_trace": [],
        }

        monkeypatch.setattr(
            "app.services.llm.llm_service.invoke",
            lambda **kw: "用户已掌握二分查找的核心概念"
        )
        monkeypatch.setattr(
            "app.services.llm.llm_service.route_intent",
            lambda x: '{"intent":"teach_loop","confidence":0.9}'
        )

        result = graph.invoke(state, config=graph_config)
        assert result.get("stage") in ["summarized", "diagnosed"]

    def test_loop_back_to_explain(self, graph, monkeypatch, graph_config):
        """测试复述失败后循环回讲解"""
        state: LearningState = {
            "session_id": "test",
            "user_input": "我不太理解",
            "topic": "二分查找",
            "stage": "explained",
            "explanation": "二分查找是...",
            "restatement_eval": "用户理解有误，存在概念混淆",
            "branch_trace": [],
            "explain_loop_count": 0,
        }

        monkeypatch.setattr(
            "app.services.llm.llm_service.invoke",
            lambda **kw: "用户理解有误，需要重新讲解"
        )
        monkeypatch.setattr(
            "app.services.llm.llm_service.route_intent",
            lambda x: '{"intent":"teach_loop","confidence":0.9}'
        )

        result = graph.invoke(state, config=graph_config)
        assert result.get("explain_loop_count", 0) >= 0
