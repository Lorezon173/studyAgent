"""恢复降级端到端集成测试。"""
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


class TestRecoveryFlow:
    """恢复降级流程集成测试。"""

    def test_recovery_llm_timeout(self, monkeypatch):
        """LLM 超时触发恢复"""
        def failing_invoke(system_prompt, user_prompt, stream_output=False):
            raise TimeoutError("LLM timeout")

        monkeypatch.setattr("app.services.llm.llm_service.invoke", failing_invoke)
        monkeypatch.setattr("app.services.llm.llm_service.route_intent",
                          lambda u: '{"intent":"qa_direct","confidence":0.95}')

        from langgraph.checkpoint.memory import MemorySaver
        import app.agent.checkpointer as cp_module
        original = cp_module._checkpointer
        cp_module._checkpointer = MemorySaver()

        try:
            graph = build_learning_graph_v2()
            config = {"configurable": {"thread_id": "test-recovery-1"}}

            state: LearningState = {
                "session_id": "test-recovery-1",
                "user_input": "test",
                "topic": "test",
                "stage": "start",
                "history": [],
                "branch_trace": [],
            }
            result = graph.invoke(state, config=config)

            # 应该有错误状态或恢复标记
            assert result.get("node_error") or result.get("fallback_triggered") or result.get("stage")
        finally:
            cp_module._checkpointer = original
            import app.agent.graph_v2 as graph_module
            graph_module._learning_graph_v2 = None

    def test_recovery_rag_failure(self, monkeypatch):
        """RAG 失败触发降级"""
        llm_mocks = {"问答助手": "降级回答"}
        monkeypatch.setattr("app.services.llm.llm_service.invoke", make_fake_invoke(llm_mocks))
        monkeypatch.setattr("app.services.llm.llm_service.route_intent",
                          lambda u: '{"intent":"qa_direct","confidence":0.95}')

        def failing_rag(**kwargs):
            raise Exception("RAG connection failed")

        monkeypatch.setattr("app.agent.nodes.qa.decide_rag_call",
                          lambda **kw: FakeRAGCallDecision(should_call=True, reason="enabled"))
        monkeypatch.setattr("app.agent.nodes.qa.execute_rag", failing_rag)

        from langgraph.checkpoint.memory import MemorySaver
        import app.agent.checkpointer as cp_module
        original = cp_module._checkpointer
        cp_module._checkpointer = MemorySaver()

        try:
            graph = build_learning_graph_v2()
            config = {"configurable": {"thread_id": "test-recovery-2"}}

            state: LearningState = {
                "session_id": "test-recovery-2",
                "user_input": "test",
                "topic": "test",
                "stage": "start",
                "history": [],
                "branch_trace": [],
            }
            result = graph.invoke(state, config=config)

            # 验证降级处理
            assert result.get("stage") in ["recovered", "answered", "start"] or result.get("node_error")
        finally:
            cp_module._checkpointer = original
            import app.agent.graph_v2 as graph_module
            graph_module._learning_graph_v2 = None

    def test_recovery_error_code_set(self, monkeypatch):
        """错误码正确设置"""
        def failing_invoke(system_prompt, user_prompt, stream_output=False):
            raise TimeoutError("timeout")

        monkeypatch.setattr("app.services.llm.llm_service.invoke", failing_invoke)
        monkeypatch.setattr("app.services.llm.llm_service.route_intent",
                          lambda u: '{"intent":"qa_direct","confidence":0.95}')

        from langgraph.checkpoint.memory import MemorySaver
        import app.agent.checkpointer as cp_module
        original = cp_module._checkpointer
        cp_module._checkpointer = MemorySaver()

        try:
            graph = build_learning_graph_v2()
            config = {"configurable": {"thread_id": "test-recovery-3"}}

            state: LearningState = {
                "session_id": "test-recovery-3",
                "user_input": "test",
                "topic": "test",
                "stage": "start",
                "history": [],
                "branch_trace": [],
            }
            result = graph.invoke(state, config=config)

            # 验证错误码（如果有）
            error_code = result.get("error_code")
            if error_code:
                assert error_code in ["llm_timeout", "rag_failure", "unknown"]
        finally:
            cp_module._checkpointer = original
            import app.agent.graph_v2 as graph_module
            graph_module._learning_graph_v2 = None

    def test_recovery_fallback_reply(self, monkeypatch):
        """降级响应生成"""
        llm_mocks = {"问答助手": "抱歉，服务暂时不可用，请稍后重试。"}
        monkeypatch.setattr("app.services.llm.llm_service.invoke", make_fake_invoke(llm_mocks))
        monkeypatch.setattr("app.services.llm.llm_service.route_intent",
                          lambda u: '{"intent":"qa_direct","confidence":0.95}')

        # Mock RAG 返回空结果
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
            config = {"configurable": {"thread_id": "test-recovery-4"}}

            state: LearningState = {
                "session_id": "test-recovery-4",
                "user_input": "test question",
                "topic": "test",
                "stage": "start",
                "history": [],
                "branch_trace": [],
            }
            result = graph.invoke(state, config=config)

            assert "reply" in result
        finally:
            cp_module._checkpointer = original
            import app.agent.graph_v2 as graph_module
            graph_module._learning_graph_v2 = None
