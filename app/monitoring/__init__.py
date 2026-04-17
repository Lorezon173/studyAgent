# app/monitoring/__init__.py
"""Langfuse 监控模块"""

from app.monitoring.desensitize import hash_user_id, sanitize_metadata

# These will be implemented in subsequent tasks
try:
    from app.monitoring.langfuse_client import get_langfuse, init_langfuse, langfuse_context
except ImportError:
    get_langfuse = None
    init_langfuse = None
    langfuse_context = None

try:
    from app.monitoring.trace_wrapper import trace_llm, trace_rag, trace_tool
except ImportError:
    trace_llm = None
    trace_rag = None
    trace_tool = None

__all__ = [
    "hash_user_id",
    "sanitize_metadata",
    "get_langfuse",
    "init_langfuse",
    "langfuse_context",
    "trace_llm",
    "trace_rag",
    "trace_tool",
]
