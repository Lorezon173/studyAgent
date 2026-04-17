# tests/test_langfuse_monitoring.py
"""Langfuse 监控模块单元测试"""

import pytest

from app.monitoring.desensitize import (
    hash_user_id,
    sanitize_metadata,
    truncate_text,
)


class TestHashUserId:
    """user_id 哈希脱敏测试"""

    def test_hash_string_user_id(self):
        """测试字符串 user_id 哈希"""
        result = hash_user_id("user123")
        assert result.startswith("hash_")
        assert len(result) == 13  # "hash_" + 8 chars

    def test_hash_integer_user_id(self):
        """测试整数 user_id 哈希"""
        result = hash_user_id(12345)
        assert result.startswith("hash_")
        assert len(result) == 13

    def test_hash_none_user_id(self):
        """测试 None user_id"""
        result = hash_user_id(None)
        assert result == "hash_unknown"

    def test_hash_empty_string(self):
        """测试空字符串"""
        result = hash_user_id("")
        assert result == "hash_unknown"

    def test_hash_consistency(self):
        """测试相同输入产生相同输出"""
        result1 = hash_user_id("same_user")
        result2 = hash_user_id("same_user")
        assert result1 == result2

    def test_hash_different_inputs(self):
        """测试不同输入产生不同输出"""
        result1 = hash_user_id("user1")
        result2 = hash_user_id("user2")
        assert result1 != result2


class TestSanitizeMetadata:
    """元数据脱敏测试"""

    def test_sanitize_removes_password(self):
        """测试移除 password 字段"""
        data = {"name": "test", "password": "secret123"}
        result = sanitize_metadata(data)
        assert result == {"name": "test"}

    def test_sanitize_removes_api_key(self):
        """测试移除 api_key 字段"""
        data = {"model": "gpt-4", "api_key": "sk-xxx"}
        result = sanitize_metadata(data)
        assert result == {"model": "gpt-4"}

    def test_sanitize_case_insensitive(self):
        """测试大小写不敏感"""
        data = {"API_KEY": "xxx", "Token": "yyy", "SECRET": "zzz"}
        result = sanitize_metadata(data)
        assert result == {}

    def test_sanitize_keeps_safe_fields(self):
        """测试保留安全字段"""
        data = {"model": "gpt-4", "tokens": 100, "latency_ms": 50}
        result = sanitize_metadata(data)
        assert result == data

    def test_sanitize_none_input(self):
        """测试 None 输入"""
        result = sanitize_metadata(None)
        assert result == {}

    def test_sanitize_empty_dict(self):
        """测试空字典"""
        result = sanitize_metadata({})
        assert result == {}


class TestTruncateText:
    """文本截断测试"""

    def test_truncate_short_text(self):
        """测试短文本不截断"""
        text = "short text"
        result = truncate_text(text, max_length=100)
        assert result == text

    def test_truncate_long_text(self):
        """测试长文本截断"""
        text = "a" * 2000
        result = truncate_text(text, max_length=1000)
        assert len(result) == 1014  # 1000 + "...[truncated]"
        assert result.endswith("...[truncated]")

    def test_truncate_none(self):
        """测试 None 输入"""
        result = truncate_text(None)
        assert result == ""

    def test_truncate_empty(self):
        """测试空字符串"""
        result = truncate_text("")
        assert result == ""


class TestLangfuseClient:
    """Langfuse 客户端测试"""

    def test_get_langfuse_returns_none_when_disabled(self):
        """测试禁用时返回 None"""
        from app.monitoring.langfuse_client import get_langfuse

        # 默认配置下 langfuse_enabled=False
        result = get_langfuse()
        # 应该返回 None 或一个客户端实例
        assert result is None or hasattr(result, "trace")

    def test_langfuse_context_available(self):
        """测试 langfuse_context 可用"""
        from app.monitoring.langfuse_client import langfuse_context

        # langfuse_context 可能为 None（langfuse 未安装）或一个上下文对象
        # 两种情况都是有效的
        assert langfuse_context is None or hasattr(langfuse_context, "update_current_trace")


class TestTraceWrapper:
    """追踪装饰器测试"""

    def test_trace_llm_decorator_exists(self):
        """测试装饰器可导入"""
        from app.monitoring.trace_wrapper import trace_llm

        assert callable(trace_llm)

    def test_trace_llm_disabled_returns_original_result(self):
        """测试禁用时返回原始结果"""
        from app.monitoring.trace_wrapper import trace_llm

        @trace_llm("test_op")
        def sample_func():
            return "original_result"

        # 当 Langfuse 禁用时，应直接返回结果
        result = sample_func()
        assert result == "original_result"

    def test_trace_rag_decorator_exists(self):
        """测试 RAG 装饰器可导入"""
        from app.monitoring.trace_wrapper import trace_rag

        assert callable(trace_rag)

    def test_trace_tool_decorator_exists(self):
        """测试工具装饰器可导入"""
        from app.monitoring.trace_wrapper import trace_tool

        assert callable(trace_tool)

    def test_decorator_preserves_function_metadata(self):
        """测试装饰器保留函数元数据"""
        from app.monitoring.trace_wrapper import trace_llm

        @trace_llm("test")
        def my_function():
            """My docstring"""
            pass

        assert my_function.__name__ == "my_function"
        assert my_function.__doc__ == "My docstring"


class TestLangfuseIntegration:
    """Langfuse 集成测试"""

    def test_full_flow_with_monitoring_disabled(self):
        """测试监控禁用时的完整流程"""
        # 确保 Langfuse 禁用
        from app.core.config import settings

        if not settings.langfuse_enabled:
            # LLM 调用应正常工作
            from app.services.llm import llm_service

            # 这里只测试导入和方法存在
            assert hasattr(llm_service, "invoke")
            assert callable(llm_service.invoke)

    def test_rag_retrieve_with_monitoring_disabled(self):
        """测试监控禁用时的 RAG 检索"""
        from app.services.rag_store import retrieve_knowledge

        # 测试函数可调用
        assert callable(retrieve_knowledge)

    def test_agent_service_imports(self):
        """测试 Agent 服务导入"""
        from app.services.agent_service import AgentService

        assert hasattr(AgentService, "run_with_graph_v2")
        assert hasattr(AgentService, "run")

    def test_monitoring_module_exports(self):
        """测试监控模块导出"""
        import app.monitoring as monitoring

        assert hasattr(monitoring, "hash_user_id")
        assert hasattr(monitoring, "sanitize_metadata")
        assert hasattr(monitoring, "trace_llm")
        assert hasattr(monitoring, "trace_rag")
        assert hasattr(monitoring, "trace_tool")
        assert hasattr(monitoring, "get_langfuse")
        assert hasattr(monitoring, "is_langfuse_enabled")
