"""验证 @node 装饰器把元数据贴到函数对象上。"""
import pytest
from app.agent.node_decorator import node, get_node_meta, NodeMeta


def test_node_decorator_attaches_meta():
    @node(name="hello", retry="LLM_RETRY", trace_label="Hello")
    def my_node(state):
        return state

    meta = get_node_meta(my_node)
    assert isinstance(meta, NodeMeta)
    assert meta.name == "hello"
    assert meta.retry_key == "LLM_RETRY"
    assert meta.trace_label == "Hello"
    assert meta.sensitive is False
    assert meta.tags == ()


def test_node_decorator_defaults():
    @node(name="bare")
    def bare_node(state):
        return state

    meta = get_node_meta(bare_node)
    assert meta.name == "bare"
    assert meta.retry_key is None
    assert meta.trace_label == "bare"  # defaults to name
    assert meta.sensitive is False


def test_node_decorator_sensitive_flag():
    @node(name="auth", sensitive=True, tags=("user_data",))
    def auth_node(state):
        return state

    meta = get_node_meta(auth_node)
    assert meta.sensitive is True
    assert meta.tags == ("user_data",)


def test_node_decorator_does_not_change_runtime_behavior():
    """装饰器透传调用，不修改 state。"""
    @node(name="passthrough")
    def passthrough(state):
        return {"echo": state.get("input")}

    result = passthrough({"input": "hi"})
    assert result == {"echo": "hi"}


def test_undecorated_function_returns_none_meta():
    def plain(state):
        return state
    assert get_node_meta(plain) is None
