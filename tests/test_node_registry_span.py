"""Phase 7 Task 2: NodeRegistry add_to_graph 的 span 包装测试。"""
from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import MagicMock

import pytest

from app.agent.node_decorator import NodeMeta
from app.agent.node_registry import NodeRegistry


class _FakeGraph:
    def __init__(self):
        self.nodes: dict[str, dict] = {}

    def add_node(self, name, fn, retry_policy=None):
        self.nodes[name] = {"fn": fn, "retry_policy": retry_policy}


class _FakeSpan:
    def __init__(self):
        self.update_calls: list[dict] = []

    def update(self, **kwargs):
        self.update_calls.append(kwargs)


@contextmanager
def _fake_span_cm(span: _FakeSpan):
    yield span


@pytest.fixture
def enabled_langfuse(monkeypatch):
    span = _FakeSpan()
    client = MagicMock()
    client.start_as_current_observation = MagicMock(
        side_effect=lambda **kwargs: _fake_span_cm(span)
    )

    monkeypatch.setattr(
        "app.monitoring.langfuse_client.is_langfuse_enabled",
        lambda: True,
    )
    monkeypatch.setattr(
        "app.monitoring.langfuse_client.get_langfuse_client",
        lambda: client,
    )
    return client, span


def test_add_to_graph_wrapper_passthrough_when_langfuse_disabled(monkeypatch):
    monkeypatch.setattr(
        "app.monitoring.langfuse_client.is_langfuse_enabled",
        lambda: False,
    )
    monkeypatch.setattr(
        "app.monitoring.langfuse_client.get_langfuse_client",
        lambda: (_ for _ in ()).throw(AssertionError("must not create span")),
    )

    reg = NodeRegistry()
    meta = NodeMeta(name="plain_node", retry_key=None, trace_label="Plain Node")
    expected = {"ok": True}

    def plain(state):
        return expected

    reg.register(meta, plain)
    graph = _FakeGraph()
    reg.add_to_graph(graph, retries={})

    wrapped = graph.nodes["plain_node"]["fn"]
    assert wrapped({"x": 1}) is expected


def test_add_to_graph_wrapper_creates_span_with_trace_label(enabled_langfuse):
    client, span = enabled_langfuse

    reg = NodeRegistry()
    meta = NodeMeta(name="span_node", retry_key=None, trace_label="Readable Span")
    expected = {"reply": "ok"}

    def plain(state):
        return expected

    reg.register(meta, plain)
    graph = _FakeGraph()
    reg.add_to_graph(graph, retries={})

    wrapped = graph.nodes["span_node"]["fn"]
    result = wrapped({"topic": "binary search"})

    assert result is expected
    client.start_as_current_observation.assert_called_once()
    call_kwargs = client.start_as_current_observation.call_args.kwargs
    assert call_kwargs["name"] == "Readable Span"
    assert call_kwargs["as_type"] == "span"
    assert "input" in span.update_calls[0]
    assert "output" in span.update_calls[1]


def test_sensitive_node_sanitizes_and_truncates_payload(enabled_langfuse):
    _, span = enabled_langfuse

    reg = NodeRegistry()
    meta = NodeMeta(name="secure_node", retry_key=None, trace_label="Secure", sensitive=True)
    long_text = "x" * 2000

    def secure(state):
        return {"ok": True, "password": "hidden", "answer": long_text}

    reg.register(meta, secure)
    graph = _FakeGraph()
    reg.add_to_graph(graph, retries={})

    wrapped = graph.nodes["secure_node"]["fn"]
    wrapped({"api_key": "secret", "prompt": long_text, "safe": 1})

    input_payload = span.update_calls[0]["input"]
    output_payload = span.update_calls[1]["output"]
    assert "api_key" not in input_payload
    assert input_payload["safe"] == 1
    assert input_payload["prompt"].endswith("...[truncated]")
    assert "password" not in output_payload
    assert output_payload["ok"] is True
    assert output_payload["answer"].endswith("...[truncated]")


def test_span_records_error_and_reraises(enabled_langfuse):
    _, span = enabled_langfuse

    reg = NodeRegistry()
    meta = NodeMeta(name="boom_node", retry_key=None, trace_label="Boom")

    def boom(state):
        raise RuntimeError("explode")

    reg.register(meta, boom)
    graph = _FakeGraph()
    reg.add_to_graph(graph, retries={})

    wrapped = graph.nodes["boom_node"]["fn"]
    with pytest.raises(RuntimeError, match="explode"):
        wrapped({"x": 1})

    assert any(
        call.get("level") == "ERROR" and "explode" in str(call.get("status_message", ""))
        for call in span.update_calls
    )
