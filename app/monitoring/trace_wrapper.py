# app/monitoring/trace_wrapper.py
"""追踪装饰器模块（适配 langfuse v4 SDK）。

v4 改用 OpenTelemetry-based API：
- `client.start_as_current_observation(name=..., as_type='span', input=...)`
  返回 context manager
- `span.update(output=..., level=..., status_message=...)`
- 异常时设置 `level="ERROR"` 后再抛
"""

import functools
import logging
import time
from typing import Any, Callable, TypeVar

from app.monitoring.desensitize import sanitize_metadata, truncate_text
from app.monitoring.langfuse_client import get_langfuse_client, is_langfuse_enabled

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


def trace_llm(operation: str) -> Callable[[F], F]:
    """追踪 LLM 调用。

    Args:
        operation: 操作名称，如 "chat", "embed", "route_intent"
    """
    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            if not is_langfuse_enabled():
                return func(*args, **kwargs)
            client = get_langfuse_client()
            start_time = time.perf_counter()

            with client.start_as_current_observation(
                name=f"llm_{operation}",
                as_type="span",
                input={"args_count": len(args), "kwargs_keys": list(kwargs.keys())},
            ) as span:
                try:
                    result = func(*args, **kwargs)
                    elapsed_ms = (time.perf_counter() - start_time) * 1000
                    span.update(
                        output={
                            "content": truncate_text(str(result), max_length=500),
                            "latency_ms": round(elapsed_ms, 2),
                        }
                    )
                    return result
                except Exception as e:
                    elapsed_ms = (time.perf_counter() - start_time) * 1000
                    try:
                        span.update(
                            level="ERROR",
                            status_message=str(e),
                            output={"error": str(e), "latency_ms": round(elapsed_ms, 2)},
                        )
                    except Exception as inner:
                        logger.warning(f"Failed to update span on error: {inner}")
                    raise

        return wrapper  # type: ignore

    return decorator


def trace_rag(operation: str) -> Callable[[F], F]:
    """追踪 RAG 检索。"""
    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            if not is_langfuse_enabled():
                return func(*args, **kwargs)
            client = get_langfuse_client()
            start_time = time.perf_counter()

            query = kwargs.get("query") or (args[0] if args else None)
            input_payload: dict[str, Any] = (
                {"query": truncate_text(str(query), max_length=200)} if query else {}
            )

            with client.start_as_current_observation(
                name=f"rag_{operation}",
                as_type="retriever",
                input=input_payload,
            ) as span:
                try:
                    result = func(*args, **kwargs)
                    elapsed_ms = (time.perf_counter() - start_time) * 1000
                    output_data: dict[str, Any] = {"latency_ms": round(elapsed_ms, 2)}
                    if isinstance(result, list):
                        output_data["chunks_count"] = len(result)
                        if result:
                            scores = [
                                x.get("score", 0) for x in result if isinstance(x, dict)
                            ]
                            if scores:
                                output_data["top_scores"] = scores[:3]
                    span.update(output=output_data)
                    return result
                except Exception as e:
                    elapsed_ms = (time.perf_counter() - start_time) * 1000
                    try:
                        span.update(
                            level="ERROR",
                            status_message=str(e),
                            output={"error": str(e), "latency_ms": round(elapsed_ms, 2)},
                        )
                    except Exception as inner:
                        logger.warning(f"Failed to update span on error: {inner}")
                    raise

        return wrapper  # type: ignore

    return decorator


def trace_tool(tool_name: str) -> Callable[[F], F]:
    """追踪工具执行。"""
    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            if not is_langfuse_enabled():
                return func(*args, **kwargs)
            client = get_langfuse_client()
            start_time = time.perf_counter()

            with client.start_as_current_observation(
                name=f"tool_{tool_name}",
                as_type="tool",
                input=sanitize_metadata(kwargs) if kwargs else {},
            ) as span:
                try:
                    result = func(*args, **kwargs)
                    elapsed_ms = (time.perf_counter() - start_time) * 1000
                    output_data: dict[str, Any] = {
                        "latency_ms": round(elapsed_ms, 2),
                        "tool_name": tool_name,
                    }
                    if isinstance(result, dict):
                        safe_result = sanitize_metadata(result)
                        output_data["result_keys"] = list(safe_result.keys())
                    elif isinstance(result, str):
                        output_data["result_length"] = len(result)
                    span.update(output=output_data)
                    return result
                except Exception as e:
                    elapsed_ms = (time.perf_counter() - start_time) * 1000
                    try:
                        span.update(
                            level="ERROR",
                            status_message=str(e),
                            output={"error": str(e), "latency_ms": round(elapsed_ms, 2)},
                        )
                    except Exception as inner:
                        logger.warning(f"Failed to update span on error: {inner}")
                    raise

        return wrapper  # type: ignore

    return decorator
