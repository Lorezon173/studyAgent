# app/agent/retry_policy.py
"""
重试策略定义
为不同类型的节点配置重试策略
"""

from langgraph.types import RetryPolicy


# 自定义异常类型（用于重试判断）
class RateLimitError(Exception):
    """LLM限流错误"""
    pass


class DatabaseError(Exception):
    """数据库错误"""
    pass


# LLM调用重试策略
LLM_RETRY = RetryPolicy(
    max_attempts=3,
    initial_interval=2.0,
    backoff_factor=2.0,
    jitter=True,
    retry_on=[ConnectionError, TimeoutError, RateLimitError],
)

# RAG检索重试策略
RAG_RETRY = RetryPolicy(
    max_attempts=2,
    initial_interval=1.0,
    backoff_factor=2.0,
    jitter=True,
    retry_on=[ConnectionError, TimeoutError],
)

# 数据库查询重试策略
DB_RETRY = RetryPolicy(
    max_attempts=3,
    initial_interval=0.5,
    backoff_factor=1.5,
    jitter=True,
    retry_on=[ConnectionError, DatabaseError],
)

# 无重试策略（用于不需要重试的节点）
NO_RETRY = None


# Single Source of Truth：所有 retry_key → RetryPolicy 的映射唯一定义
# 修改这里时同步 app/agent/node_decorator.py 的 RetryKey Literal（PEP 586 限制无法派生）
RETRY_POLICIES_MAP: dict[str, RetryPolicy] = {
    "LLM_RETRY": LLM_RETRY,
    "RAG_RETRY": RAG_RETRY,
    "DB_RETRY": DB_RETRY,
}
