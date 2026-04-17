# app/monitoring/trace_wrapper.py
"""追踪装饰器模块"""

import functools
import logging
import time
from typing import Any, Callable, TypeVar

from app.core.config import settings
from app.monitoring.desensitize import sanitize_metadata, truncate_text
from app.monitoring.langfuse_client import get_langfuse, langfuse_context

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


def _should_trace() -> bool:
    """检查是否应该执行追踪"""
    return settings.langfuse_enabled and get_langfuse() is not None


def _safe_span_end(span: Any, output: Any) -> None:
    """安全地结束 span"""
    try:
        if span is not None:
            span.end(output=output)
    except Exception as e:
        logger.warning(f"Failed to end span: {e}")


def trace_llm(operation: str) -> Callable[[F], F]:
    """追踪 LLM 调用的装饰器

    Args:
        operation: 操作名称，如 "chat", "embed", "route_intent"

    Returns:
        装饰器函数

    Example:
        @trace_llm("chat")
        def call_llm(prompt: str) -> str:
            ...
    """
    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            if not _should_trace():
                return func(*args, **kwargs)

            start_time = time.perf_counter()
            span = None

            try:
                # 尝试创建 span
                if langfuse_context is not None:
                    span = langfuse_context.span(
                        name=f"llm_{operation}",
                        input={"args_count": len(args), "kwargs_keys": list(kwargs.keys())},
                    )

                # 执行原函数
                result = func(*args, **kwargs)

                # 记录输出
                elapsed_ms = (time.perf_counter() - start_time) * 1000
                output_data = {
                    "content": truncate_text(str(result), max_length=500),
                    "latency_ms": round(elapsed_ms, 2),
                }

                _safe_span_end(span, output_data)
                return result

            except Exception as e:
                # 记录异常
                elapsed_ms = (time.perf_counter() - start_time) * 1000
                if span is not None:
                    try:
                        span.end(
                            output={"error": str(e), "latency_ms": round(elapsed_ms, 2)},
                            level="ERROR",
                        )
                    except Exception:
                        pass
                raise

        return wrapper  # type: ignore

    return decorator


def trace_rag(operation: str) -> Callable[[F], F]:
    """追踪 RAG 检索的装饰器

    Args:
        operation: 操作名称，如 "retrieve", "ingest"

    Returns:
        装饰器函数

    Example:
        @trace_rag("retrieve")
        def retrieve_knowledge(query: str) -> list:
            ...
    """
    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            if not _should_trace():
                return func(*args, **kwargs)

            start_time = time.perf_counter()
            span = None

            try:
                # 提取查询信息
                query = kwargs.get("query") or (args[0] if args else None)

                if langfuse_context is not None:
                    span = langfuse_context.span(
                        name=f"rag_{operation}",
                        input={"query": truncate_text(str(query), max_length=200)} if query else {},
                    )

                # 执行原函数
                result = func(*args, **kwargs)

                # 记录输出
                elapsed_ms = (time.perf_counter() - start_time) * 1000
                output_data: dict[str, Any] = {"latency_ms": round(elapsed_ms, 2)}

                if isinstance(result, list):
                    output_data["chunks_count"] = len(result)
                    if result:
                        scores = [x.get("score", 0) for x in result if isinstance(x, dict)]
                        if scores:
                            output_data["top_scores"] = scores[:3]

                _safe_span_end(span, output_data)
                return result

            except Exception as e:
                elapsed_ms = (time.perf_counter() - start_time) * 1000
                if span is not None:
                    try:
                        span.end(
                            output={"error": str(e), "latency_ms": round(elapsed_ms, 2)},
                            level="ERROR",
                        )
                    except Exception:
                        pass
                raise

        return wrapper  # type: ignore

    return decorator


def trace_tool(tool_name: str) -> Callable[[F], F]:
    """追踪工具执行的装饰器

    Args:
        tool_name: 工具名称，如 "web_search", "calculator"

    Returns:
        装饰器函数

    Example:
        @trace_tool("web_search")
        def execute_search(query: str) -> dict:
            ...
    """
    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            if not _should_trace():
                return func(*args, **kwargs)

            start_time = time.perf_counter()
            span = None

            try:
                if langfuse_context is not None:
                    span = langfuse_context.span(
                        name=f"tool_{tool_name}",
                        input=sanitize_metadata(kwargs) if kwargs else {},
                    )

                # 执行原函数
                result = func(*args, **kwargs)

                # 记录输出
                elapsed_ms = (time.perf_counter() - start_time) * 1000
                output_data: dict[str, Any] = {
                    "latency_ms": round(elapsed_ms, 2),
                    "tool_name": tool_name,
                }

                if isinstance(result, dict):
                    # 安全地记录字典结果
                    safe_result = sanitize_metadata(result)
                    output_data["result_keys"] = list(safe_result.keys())
                elif isinstance(result, str):
                    output_data["result_length"] = len(result)

                _safe_span_end(span, output_data)
                return result

            except Exception as e:
                elapsed_ms = (time.perf_counter() - start_time) * 1000
                if span is not None:
                    try:
                        span.end(
                            output={"error": str(e), "latency_ms": round(elapsed_ms, 2)},
                            level="ERROR",
                        )
                    except Exception:
                        pass
                raise

        return wrapper  # type: ignore

    return decorator
