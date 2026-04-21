# tests/test_error_classifier.py
"""错误分类服务测试"""
from app.services.error_classifier import classify_error, ErrorType


def test_classify_timeout_error():
    """测试超时错误分类"""
    error = TimeoutError("LLM request timed out")
    result = classify_error(error)
    assert result.error_type == ErrorType.LLM_TIMEOUT
    assert result.retryable is True


def test_classify_generic_error():
    """测试通用错误分类"""
    error = ValueError("Unknown error")
    result = classify_error(error)
    assert result.error_type == ErrorType.UNKNOWN
    assert result.fallback_action == "pure_llm"


def test_classify_rate_limit_error():
    """测试限流错误分类"""
    error = Exception("Rate limit exceeded 429")
    result = classify_error(error)
    assert result.error_type == ErrorType.LLM_RATE_LIMIT
    assert result.retryable is True


def test_classify_db_error():
    """测试数据库错误分类"""
    error = Exception("Database connection failed")
    result = classify_error(error)
    assert result.error_type == ErrorType.DB_ERROR
    assert result.fallback_action == "use_cache"


def test_classify_no_results_error():
    """测试无结果错误分类"""
    error = Exception("No results found, empty response")
    result = classify_error(error)
    assert result.error_type == ErrorType.RAG_NO_RESULTS
    assert result.retryable is False
