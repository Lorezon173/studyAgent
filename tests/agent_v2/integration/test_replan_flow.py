"""重规划端到端集成测试。"""
import pytest
from app.agent.graph_v2 import build_learning_graph_v2
from app.agent.state import LearningState
from tests.agent_v2.conftest import make_fake_invoke


class TestReplanFlow:
    """重规划流程集成测试。"""

    def test_replan_from_start(self, monkeypatch):
        """首轮即重规划"""
        llm_mocks = {
            "规划助手": "新计划"
        }
        monkeypatch.setattr("app.services.llm.llm_service.invoke", make_fake_invoke(llm_mocks))
        monkeypatch.setattr("app.services.llm.llm_service.route_intent",
                          lambda u: '{"intent":"replan","confidence":0.95}')

        def fake_create_plan(state):
            return {"goal": "学习哈希表", "steps": [{"name": "step1", "description": "了解基本概念"}]}

        monkeypatch.setattr("app.services.agent_runtime.create_or_update_plan", fake_create_plan)

        from langgraph.checkpoint.memory import MemorySaver
        import app.agent.checkpointer as cp_module
        original = cp_module._checkpointer
        cp_module._checkpointer = MemorySaver()

        try:
            graph = build_learning_graph_v2()
            config = {"configurable": {"thread_id": "test-replan-1"}}

            state: LearningState = {
                "session_id": "test-replan-1",
                "user_input": "我想改学哈希表",
                "topic": None,
                "stage": "start",
                "history": [],
                "branch_trace": [],
            }
            result = graph.invoke(state, config=config)

            assert result["stage"] == "planned"
            assert "当前目标" in result.get("reply", "")
        finally:
            cp_module._checkpointer = original
            import app.agent.graph_v2 as graph_module
            graph_module._learning_graph_v2 = None

    def test_replan_mid_session(self, monkeypatch):
        """中途请求重规划"""
        llm_mocks = {
            "规划助手": "新计划"
        }
        monkeypatch.setattr("app.services.llm.llm_service.invoke", make_fake_invoke(llm_mocks))
        monkeypatch.setattr("app.services.llm.llm_service.route_intent",
                          lambda u: '{"intent":"replan","confidence":0.95}')

        def fake_create_plan(state):
            return {"goal": "学习图论", "steps": []}

        monkeypatch.setattr("app.services.agent_runtime.create_or_update_plan", fake_create_plan)

        from langgraph.checkpoint.memory import MemorySaver
        import app.agent.checkpointer as cp_module
        original = cp_module._checkpointer
        cp_module._checkpointer = MemorySaver()

        try:
            graph = build_learning_graph_v2()
            config = {"configurable": {"thread_id": "test-replan-2"}}

            state: LearningState = {
                "session_id": "test-replan-2",
                "user_input": "改学图论",
                "topic": "二分查找",
                "stage": "explained",
                "history": [],
                "branch_trace": [],
                "current_plan": {"goal": "学习二分查找", "steps": []}
            }
            result = graph.invoke(state, config=config)

            assert result["stage"] == "planned"
            assert "图论" in result["current_plan"]["goal"]
        finally:
            cp_module._checkpointer = original
            import app.agent.graph_v2 as graph_module
            graph_module._learning_graph_v2 = None

    def test_replan_updates_current_plan(self, monkeypatch):
        """重规划更新当前计划"""
        monkeypatch.setattr("app.services.llm.llm_service.route_intent",
                          lambda u: '{"intent":"replan","confidence":0.95}')

        def fake_create_plan(state):
            return {"goal": f"学习{state.get('topic', '新主题')}", "steps": [{"name": "s1"}]}

        monkeypatch.setattr("app.services.agent_runtime.create_or_update_plan", fake_create_plan)

        from langgraph.checkpoint.memory import MemorySaver
        import app.agent.checkpointer as cp_module
        original = cp_module._checkpointer
        cp_module._checkpointer = MemorySaver()

        try:
            graph = build_learning_graph_v2()
            config = {"configurable": {"thread_id": "test-replan-3"}}

            state: LearningState = {
                "session_id": "test-replan-3",
                "user_input": "重规划",
                "topic": "栈",
                "stage": "start",
                "history": [],
                "branch_trace": [],
            }
            result = graph.invoke(state, config=config)

            assert result["current_plan"]["goal"] == "学习栈"
            assert result["current_step_index"] == 0
        finally:
            cp_module._checkpointer = original
            import app.agent.graph_v2 as graph_module
            graph_module._learning_graph_v2 = None
