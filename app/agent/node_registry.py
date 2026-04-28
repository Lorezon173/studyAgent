"""节点名 → 实现的注册表。Task 3 扩充。"""
from __future__ import annotations

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
            if meta.retry_key is None:
                graph.add_node(name, fn)
            else:
                policy = retries.get(meta.retry_key)
                if policy is None:
                    raise ValueError(
                        f"Node '{name}' references retry_key='{meta.retry_key}' "
                        f"but it is not in the retries map: {list(retries.keys())}"
                    )
                graph.add_node(name, fn, retry=policy)


_registry_instance = NodeRegistry()


def get_registry() -> NodeRegistry:
    return _registry_instance


__all__ = ["NodeRegistry", "get_registry"]
