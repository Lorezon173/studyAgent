"""节点名 → 实现的注册表。Task 3 扩充。"""
from __future__ import annotations

import functools
from typing import Any, Callable, Dict, TYPE_CHECKING

if TYPE_CHECKING:
    from app.agent.node_decorator import NodeMeta


class NodeRegistry:
    """节点注册表单例。"""

    def __init__(self) -> None:
        self._nodes: Dict[str, tuple["NodeMeta", Callable]] = {}

    def register(self, meta: "NodeMeta", fn: Callable) -> None:
        if meta.name in self._nodes:
            existing_meta, _ = self._nodes[meta.name]
            if existing_meta is not meta:
                raise ValueError(
                    f"Node '{meta.name}' already registered with different metadata"
                )
        self._nodes[meta.name] = (meta, fn)

    def get(self, name: str) -> tuple["NodeMeta", Callable]:
        if name not in self._nodes:
            raise KeyError(f"Node '{name}' not registered")
        return self._nodes[name]

    def all(self) -> Dict[str, tuple["NodeMeta", Callable]]:
        return dict(self._nodes)

    def clear(self) -> None:
        """仅供测试使用。"""
        self._nodes.clear()

    def add_to_graph(self, graph, *, retries: Dict[str, Any]) -> None:
        """把所有已注册节点添加到 LangGraph StateGraph。

        Args:
            graph: langgraph.graph.StateGraph 实例
            retries: retry_key → RetryPolicy 映射
                     例如 {"LLM_RETRY": LLM_RETRY, "RAG_RETRY": RAG_RETRY, ...}
        """
        for name, (meta, fn) in self._nodes.items():
            fn_to_register = self._wrap_with_span(meta, fn)
            if meta.retry_key is None:
                graph.add_node(name, fn_to_register)
            else:
                policy = retries.get(meta.retry_key)
                if policy is None:
                    raise ValueError(
                        f"Node '{name}' references retry_key='{meta.retry_key}' "
                        f"but it is not in the retries map: {list(retries.keys())}"
                    )
                graph.add_node(name, fn_to_register, retry_policy=policy)

    @staticmethod
    def _wrap_with_span(meta: "NodeMeta", fn: Callable) -> Callable:
        """为节点函数创建 Langfuse span 包装。

        设计约束：
        - @node 仍是纯元数据装饰器（不改函数行为）
        - 仅在 add_to_graph 路径（LangGraph 运行时）生效
        - langfuse_enabled=False 时零侵入透传
        """

        @functools.wraps(fn)
        def wrapped(state, *args, **kwargs):
            from app.monitoring.desensitize import sanitize_metadata, truncate_payload
            from app.monitoring.langfuse_client import (
                get_langfuse_client,
                is_langfuse_enabled,
            )

            if not is_langfuse_enabled():
                return fn(state, *args, **kwargs)

            client = get_langfuse_client()
            if client is None:
                return fn(state, *args, **kwargs)

            span_name = meta.trace_label or meta.name
            with client.start_as_current_observation(
                name=span_name,
                as_type="span",
            ) as span:
                span_input = sanitize_metadata(state) if meta.sensitive else state
                span.update(input=truncate_payload(span_input))
                try:
                    result = fn(state, *args, **kwargs)
                except Exception as e:
                    span.update(level="ERROR", status_message=str(e))
                    raise
                span_output = sanitize_metadata(result) if meta.sensitive else result
                span.update(output=truncate_payload(span_output))
                return result

        return wrapped


_registry_instance = NodeRegistry()


def get_registry() -> NodeRegistry:
    return _registry_instance


__all__ = ["NodeRegistry", "get_registry"]
