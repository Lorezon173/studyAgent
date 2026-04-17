# app/monitoring/__init__.py
"""Langfuse 监控模块"""

from app.monitoring.desensitize import hash_user_id, sanitize_metadata, truncate_text
from app.monitoring.langfuse_client import get_langfuse, init_langfuse, is_langfuse_enabled, langfuse_context

# These will be implemented in subsequent tasks
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
    "init_langfuse",
    "is_langfuse_enabled",
    "langfuse_context",
    # 追踪装饰器
    "trace_llm",
    "trace_rag",
    "trace_tool",
]
