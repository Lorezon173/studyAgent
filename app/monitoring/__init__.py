# app/monitoring/__init__.py
"""Langfuse 监控模块（v4 SDK）。"""

from app.monitoring.desensitize import (
    hash_user_id,
    sanitize_metadata,
    truncate_text,
)
from app.monitoring.langfuse_client import (
    get_langfuse,  # 兼容别名 → get_langfuse_client
    get_langfuse_client,
    init_langfuse,
    is_langfuse_enabled,
)

# 追踪装饰器（v4 实现）
try:
    from app.monitoring.trace_wrapper import trace_llm, trace_rag, trace_tool
except ImportError:
    trace_llm = None
    trace_rag = None
    trace_tool = None

__all__ = [
    # 脱敏工具
    "hash_user_id",
    "sanitize_metadata",
    "truncate_text",
    # Langfuse 客户端
    "get_langfuse",
    "get_langfuse_client",
    "init_langfuse",
    "is_langfuse_enabled",
    # 追踪装饰器
    "trace_llm",
    "trace_rag",
    "trace_tool",
]
