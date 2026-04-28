"""节点名 → 实现的注册表。Task 3 扩充。"""
from __future__ import annotations

from typing import Callable, Dict, TYPE_CHECKING

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


_registry_instance = NodeRegistry()


def get_registry() -> NodeRegistry:
    return _registry_instance


__all__ = ["NodeRegistry", "get_registry"]
