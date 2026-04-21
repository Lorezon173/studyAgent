# app/services/error_classifier.py
"""错误分类服务

分类异常并返回恢复策略。
"""
from __future__ import annotations
from enum import Enum
from dataclasses import dataclass


class ErrorType(Enum):
    """错误类型枚举"""
    LLM_TIMEOUT = "llm_timeout"
    LLM_RATE_LIMIT = "llm_rate_limit"
    RAG_FAILURE = "rag_failure"
    RAG_NO_RESULTS = "rag_no_results"
    DB_ERROR = "db_error"
    UNKNOWN = "unknown"


@dataclass
class ErrorClassification:
    """错误分类结果"""
    error_type: ErrorType
    retryable: bool
    fallback_action: str


ERROR_STRATEGIES: dict[ErrorType, ErrorClassification] = {
    ErrorType.LLM_TIMEOUT: ErrorClassification(
        error_type=ErrorType.LLM_TIMEOUT,
        retryable=True,
        fallback_action="use_cache",
    ),
    ErrorType.LLM_RATE_LIMIT: ErrorClassification(
        error_type=ErrorType.LLM_RATE_LIMIT,
        retryable=True,
        fallback_action="delay_retry",
    ),
    ErrorType.RAG_FAILURE: ErrorClassification(
        error_type=ErrorType.RAG_FAILURE,
        retryable=False,
        fallback_action="pure_llm",
    ),
    ErrorType.RAG_NO_RESULTS: ErrorClassification(
        error_type=ErrorType.RAG_NO_RESULTS,
        retryable=False,
        fallback_action="suggest_refine",
    ),
    ErrorType.DB_ERROR: ErrorClassification(
        error_type=ErrorType.DB_ERROR,
        retryable=True,
        fallback_action="use_cache",
    ),
    ErrorType.UNKNOWN: ErrorClassification(
        error_type=ErrorType.UNKNOWN,
        retryable=False,
        fallback_action="pure_llm",
    ),
}


def classify_error(error: Exception) -> ErrorClassification:
    """分类错误并返回恢复策略

    Args:
        error: 异常对象

    Returns:
        ErrorClassification: 错误分类结果
    """
    error_name = type(error).__name__
    error_msg = str(error).lower()

    if "timeout" in error_msg or "timed out" in error_msg or error_name == "TimeoutError":
        return ERROR_STRATEGIES[ErrorType.LLM_TIMEOUT]
    if "rate limit" in error_msg or "429" in error_msg:
        return ERROR_STRATEGIES[ErrorType.LLM_RATE_LIMIT]
    if "no result" in error_msg or "empty" in error_msg:
        return ERROR_STRATEGIES[ErrorType.RAG_NO_RESULTS]
    if "connection" in error_msg or "database" in error_msg:
        return ERROR_STRATEGIES[ErrorType.DB_ERROR]

    return ERROR_STRATEGIES[ErrorType.UNKNOWN]
