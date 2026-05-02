"""Phase 7 Task 0: Langfuse v4 SDK 适配回归测试。

校验：
- 包结构不再依赖已被 v4 移除的 `langfuse.decorators`
- `langfuse_enabled=False` 时 trace_* 装饰器透传
- 启用时调用 `client.start_as_current_observation` 并按预期 update span
"""
from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import MagicMock

import pytest


# ----- 模块结构回归 -----

def test_monitoring_package_does_not_export_langfuse_context():
    """v4 已无 langfuse.decorators；模块不再 re-export `langfuse_context`。"""
    import app.monitoring as m
    assert not hasattr(m, "langfuse_context"), (
        "monitoring package must not re-export removed v2 langfuse_context"
    )


def test_langfuse_client_module_does_not_import_decorators():
    """langfuse_client 不应再触发 v4 不存在的 `langfuse.decorators` 导入。"""
    import app.monitoring.langfuse_client as lc
    assert not hasattr(lc, "langfuse_context"), (
        "langfuse_client must not expose the removed v2 langfuse_context"
    )
    assert hasattr(lc, "get_langfuse_client")
    assert hasattr(lc, "is_langfuse_enabled")


def test_get_langfuse_client_returns_none_when_disabled(monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "langfuse_enabled", False)

    from app.monitoring.langfuse_client import get_langfuse_client, init_langfuse
    init_langfuse()  # 重新走一次初始化以应用 patch
    assert get_langfuse_client() is None


# ----- trace_wrapper 行为回归 -----

class _FakeSpan:
    def __init__(self):
        self.update_calls: list[dict] = []
    def update(self, **kwargs):
        self.update_calls.append(kwargs)


@contextmanager
def _fake_span_cm(span):
    """模拟 v4 start_as_current_observation 的 context manager 协议。"""
    yield span


@pytest.fixture
def mock_langfuse_client(monkeypatch):
    """启用 Langfuse 并替换 client 为 mock。"""
    span = _FakeSpan()
    client = MagicMock()
    client.start_as_current_observation = MagicMock(
        side_effect=lambda **kwargs: _fake_span_cm(span)
    )

    monkeypatch.setattr(
        "app.monitoring.trace_wrapper.is_langfuse_enabled",
        lambda: True,
    )
    monkeypatch.setattr(
        "app.monitoring.trace_wrapper.get_langfuse_client",
        lambda: client,
    )
    return client, span


def test_trace_llm_passthrough_when_disabled(monkeypatch):
    monkeypatch.setattr(
        "app.monitoring.trace_wrapper.is_langfuse_enabled", lambda: False
    )
    from app.monitoring.trace_wrapper import trace_llm

    @trace_llm("chat")
    def call(x):
        return x * 2

    assert call(3) == 6  # 直接透传


def test_trace_llm_creates_span_with_correct_name(mock_langfuse_client):
    client, span = mock_langfuse_client
    from app.monitoring.trace_wrapper import trace_llm

    @trace_llm("chat")
    def call(prompt):
        return "answer"

    result = call("hello")

    assert result == "answer"
    client.start_as_current_observation.assert_called_once()
    call_kwargs = client.start_as_current_observation.call_args.kwargs
    assert call_kwargs["name"] == "llm_chat"
    assert call_kwargs["as_type"] == "span"
    # span.update 应被调用一次记录 output
    assert len(span.update_calls) == 1
    assert "output" in span.update_calls[0]
    assert "content" in span.update_calls[0]["output"]


def test_trace_llm_records_error_on_exception(mock_langfuse_client):
    client, span = mock_langfuse_client
    from app.monitoring.trace_wrapper import trace_llm

    @trace_llm("chat")
    def boom():
        raise RuntimeError("kaboom")

    with pytest.raises(RuntimeError, match="kaboom"):
        boom()

    # span.update 应记录 ERROR level
    assert any(
        c.get("level") == "ERROR" and "kaboom" in str(c.get("status_message", ""))
        for c in span.update_calls
    )


def test_trace_rag_uses_retriever_as_type(mock_langfuse_client):
    client, _ = mock_langfuse_client
    from app.monitoring.trace_wrapper import trace_rag

    @trace_rag("retrieve")
    def retrieve(query):
        return [{"score": 0.9}, {"score": 0.5}]

    retrieve("foo")
    kwargs = client.start_as_current_observation.call_args.kwargs
    assert kwargs["name"] == "rag_retrieve"
    assert kwargs["as_type"] == "retriever"


def test_trace_tool_uses_tool_as_type(mock_langfuse_client):
    client, _ = mock_langfuse_client
    from app.monitoring.trace_wrapper import trace_tool

    @trace_tool("web_search")
    def search(query=None):
        return {"results": []}

    search(query="x")
    kwargs = client.start_as_current_observation.call_args.kwargs
    assert kwargs["name"] == "tool_web_search"
    assert kwargs["as_type"] == "tool"
