"""节点装饰器：把节点元数据贴到函数对象上，由 NodeRegistry 消费。

@node 不改变函数签名或运行时行为；它只是注入元数据。
LangGraph 的 retry_policy 仍由 graph_v2.py 通过 add_node 配置——
但 add_node 调用现在从 registry 解析 (name, fn, retry)，
而不是手写硬编码节点名。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional, Any, Literal

from app.agent.retry_policy import RETRY_POLICIES_MAP


# Literal 必须是字面量元组（PEP 586），无法从 RETRY_POLICIES_MAP.keys() 派生。
# 一致性由 tests/test_retry_policy_ssot.py 守住。
RetryKey = Literal["LLM_RETRY", "RAG_RETRY", "DB_RETRY"]
_VALID_RETRY_KEYS = frozenset(RETRY_POLICIES_MAP.keys())


@dataclass(frozen=True)
class NodeMeta:
    """节点元数据。"""
    name: str
    retry_key: Optional[RetryKey] = None
    trace_label: str = ""
    sensitive: bool = False  # True 表示 trace 时需要脱敏
    tags: tuple[str, ...] = field(default_factory=tuple)


_REGISTRY_KEY = "__node_meta__"


def node(
    *,
    name: str,
    retry: Optional[RetryKey] = None,
    trace_label: str = "",
    sensitive: bool = False,
    tags: tuple[str, ...] = (),
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """节点装饰器。

    Args:
        name: 节点在图中的名称（必须）
        retry: 重试策略键 — "LLM_RETRY" / "RAG_RETRY" / "DB_RETRY" 或 None
        trace_label: 用于可观测性的人类可读标签
        sensitive: 是否包含敏感数据，trace 时需脱敏
        tags: 自由分类标签
    """
    if retry is not None and retry not in _VALID_RETRY_KEYS:
        raise ValueError(
            f"@node(retry={retry!r}) is not a valid retry key. "
            f"Allowed: {sorted(_VALID_RETRY_KEYS)} or None."
        )

    meta = NodeMeta(
        name=name,
        retry_key=retry,
        trace_label=trace_label or name,
        sensitive=sensitive,
        tags=tags,
    )

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        setattr(fn, _REGISTRY_KEY, meta)
        from app.agent.node_registry import _registry_instance
        _registry_instance.register(meta, fn)
        return fn

    return decorator


def get_node_meta(fn: Callable[..., Any]) -> Optional[NodeMeta]:
    """读取已装饰函数的元数据。"""
    return getattr(fn, _REGISTRY_KEY, None)


__all__ = ["NodeMeta", "node", "get_node_meta"]
