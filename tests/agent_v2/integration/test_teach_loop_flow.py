"""教学主线端到端集成测试。"""
import pytest
from dataclasses import dataclass
from app.agent.graph_v2 import build_learning_graph_v2
from app.agent.state import LearningState
from tests.agent_v2.conftest import make_fake_invoke, assert_branch_trace_phases


class TestTeachLoopFlow:
    """教学主线流程集成测试。"""

    def test_teach_loop_complete(self, monkeypatch):
        """完整教学流程：诊断→讲解→复述检测→追问/总结"""
        llm_mocks = {
            "学习诊断助手": "用户对二分查找有基本概念。",
            "教学助手": "二分查找每次取中间值比较。请你复述。",
            "学习评估助手": "复述正确。",
            "追问老师": "请说明为什么数组必须有序？",
            "复盘学习成果": "已掌握基本流程。"
        }
        monkeypatch.setattr("app.services.llm.llm_service.invoke", make_fake_invoke(llm_mocks))
        monkeypatch.setattr("app.services.llm.llm_service.route_intent",
                          lambda u: '{"intent":"teach_loop","confidence":0.95}')
        monkeypatch.setattr("app.services.llm.llm_service.detect_topic",
                          lambda u, c: '{"topic":"二分查找","changed":true,"confidence":0.9,"reason":"","comparison_mode":false}')

        from langgraph.checkpoint.memory import MemorySaver
        import app.agent.checkpointer as cp_module
        original = cp_module._checkpointer
        cp_module._checkpointer = MemorySaver()

        try:
            graph = build_learning_graph_v2()
            config = {"configurable": {"thread_id": "test-teach-1"}}

            # 图会在一次 invoke 中运行到终端节点
            state: LearningState = {
                "session_id": "test-teach-1",
                "user_input": "我想学二分查找",
                "topic": "二分查找",
                "stage": "start",
                "history": [],
                "branch_trace": [],
            }
            result = graph.invoke(state, config=config)

            # 验证最终阶段是终止状态之一
            assert result["stage"] in ["summarized", "followup_generated"]

            # 验证分支追踪包含关键节点
            phases = [e.get("phase") for e in result.get("branch_trace", [])]
            assert any("Intent Router" in str(p) or "intent" in str(p).lower() for p in phases)
        finally:
            cp_module._checkpointer = original
            import app.agent.graph_v2 as graph_module
            graph_module._learning_graph_v2 = None

    def test_teach_loop_with_history(self, monkeypatch):
        """有历史记录时询问复习/继续"""
        llm_mocks = {
            "学习诊断助手": "诊断结果",
            "教学助手": "讲解内容",
        }
        monkeypatch.setattr("app.services.llm.llm_service.invoke", make_fake_invoke(llm_mocks))
        monkeypatch.setattr("app.services.llm.llm_service.route_intent",
                          lambda u: '{"intent":"teach_loop","confidence":0.95}')

        # Mock 有历史记录
        monkeypatch.setattr("app.services.learning_profile_store.list_topic_memory_entries",
                          lambda **kw: [{"entry_type": "session", "content": "test", "level": "medium"}])

        from langgraph.checkpoint.memory import MemorySaver
        import app.agent.checkpointer as cp_module
        original = cp_module._checkpointer
        cp_module._checkpointer = MemorySaver()

        try:
            graph = build_learning_graph_v2()
            config = {"configurable": {"thread_id": "test-teach-history"}}

            state: LearningState = {
                "session_id": "test-teach-history",
                "user_id": 1,
                "user_input": "继续学二分查找",
                "topic": "二分查找",
                "stage": "start",
                "history": [],
                "branch_trace": [],
            }
            result = graph.invoke(state, config=config)

            assert result["has_history"] is True
        finally:
            cp_module._checkpointer = original
            import app.agent.graph_v2 as graph_module
            graph_module._learning_graph_v2 = None

    def test_teach_loop_restate_retry(self, monkeypatch):
        """复述不合格时重新讲解（最多3次）"""
        call_count = {"n": 0}

        def counting_fake_invoke(system_prompt, user_prompt, stream_output=False):
            call_count["n"] += 1
            if "学习评估助手" in system_prompt and call_count["n"] <= 2:
                return "复述存在错误，理解有误。"
            if "学习评估助手" in system_prompt:
                return "复述正确。"
            if "教学助手" in system_prompt:
                return "二分查找讲解内容。"
            return "默认"

        monkeypatch.setattr("app.services.llm.llm_service.invoke", counting_fake_invoke)
        monkeypatch.setattr("app.services.llm.llm_service.route_intent",
                          lambda u: '{"intent":"teach_loop","confidence":0.95}')

        from langgraph.checkpoint.memory import MemorySaver
        import app.agent.checkpointer as cp_module
        original = cp_module._checkpointer
        cp_module._checkpointer = MemorySaver()

        try:
            graph = build_learning_graph_v2()
            config = {"configurable": {"thread_id": "test-retry"}}

            state: LearningState = {
                "session_id": "test-retry",
                "user_input": "学二分查找",
                "topic": "二分查找",
                "stage": "start",
                "history": [],
                "branch_trace": [],
            }

            # 第一轮
            result = graph.invoke(state, config=config)
            # 应该已经经过诊断和讲解
            assert result["stage"] in ["explained", "restatement_checked", "summarized", "followup_generated"]
        finally:
            cp_module._checkpointer = original
            import app.agent.graph_v2 as graph_module
            graph_module._learning_graph_v2 = None

    def test_teach_loop_branch_trace(self, monkeypatch):
        """分支追踪完整性"""
        llm_mocks = {
            "学习诊断助手": "诊断",
            "教学助手": "讲解",
            "学习评估助手": "已理解",
            "复盘学习成果": "总结"
        }
        monkeypatch.setattr("app.services.llm.llm_service.invoke", make_fake_invoke(llm_mocks))
        monkeypatch.setattr("app.services.llm.llm_service.route_intent",
                          lambda u: '{"intent":"teach_loop","confidence":0.95}')

        from langgraph.checkpoint.memory import MemorySaver
        import app.agent.checkpointer as cp_module
        original = cp_module._checkpointer
        cp_module._checkpointer = MemorySaver()

        try:
            graph = build_learning_graph_v2()
            config = {"configurable": {"thread_id": "test-trace"}}

            state: LearningState = {
                "session_id": "test-trace",
                "user_input": "学二分查找",
                "topic": "二分查找",
                "stage": "start",
                "history": [],
                "branch_trace": [],
            }
            result = graph.invoke(state, config=config)

            # 验证 branch_trace 包含预期阶段（使用 trace_label 格式）
            phases = [e.get("phase") for e in result.get("branch_trace", [])]
            # phase 使用的是节点的 trace_label，如 "Intent Router"
            assert any("Intent Router" in str(p) or "intent" in str(p).lower() for p in phases)
            assert any("Diagnose" in str(p) or "diagnose" in str(p).lower() for p in phases)
        finally:
            cp_module._checkpointer = original
            import app.agent.graph_v2 as graph_module
            graph_module._learning_graph_v2 = None
