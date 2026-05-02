# app/monitoring/desensitize.py
"""敏感数据脱敏工具"""

import hashlib
import logging

logger = logging.getLogger(__name__)

SENSITIVE_KEYS = frozenset({
    "password", "token", "api_key", "secret", "credential",
    "authorization", "private_key", "access_token",
})


def hash_user_id(user_id: str | int | None) -> str:
    """对 user_id 进行 SHA256 哈希脱敏

    Args:
        user_id: 原始用户ID（可以是字符串或整数）

    Returns:
        格式: "hash_<前8位哈希值>" 或 "hash_unknown"
    """
    if user_id is None:
        return "hash_unknown"

    try:
        user_str = str(user_id)
        if not user_str:
            return "hash_unknown"
        hash_value = hashlib.sha256(user_str.encode("utf-8")).hexdigest()[:8]
        return f"hash_{hash_value}"
    except Exception as e:
        logger.warning(f"Failed to hash user_id: {e}")
        return "hash_error"


def sanitize_metadata(metadata: dict | None) -> dict:
    """过滤敏感字段

    Args:
        metadata: 原始元数据字典

    Returns:
        过滤后的元数据字典（不包含敏感字段）
    """
    if not metadata or not isinstance(metadata, dict):
        return {}

    return {
        k: v for k, v in metadata.items()
        if k.lower() not in SENSITIVE_KEYS
    }


def truncate_text(text: str | None, max_length: int = 1000) -> str:
    """截断文本以避免过大的 trace 数据

    Args:
        text: 原始文本
        max_length: 最大长度

    Returns:
        截断后的文本
    """
    if not text:
        return ""
    if len(text) <= max_length:
        return text
    return text[:max_length] + "...[truncated]"


def truncate_payload(payload, max_length: int = 1500, _depth: int = 0):
    """递归截断 payload 中的字符串值。

    用于防止 Langfuse Span 上报或 branch_trace 写入时超长字符串
    导致 OOM / 超大 payload 失败。

    规则：
    - dict / list 递归处理（限制深度 ≤ 3）
    - 超过深度的容器整体转 str 后截断
    - str → truncate_text(value, max_length)
    - 其他类型（int / bool / None / 自定义对象）原样返回

    Args:
        payload: 任意结构的待上报数据
        max_length: 字符串最大长度
        _depth: 内部递归深度计数（外部调用勿传）
    """
    if _depth > 3:
        return truncate_text(str(payload), max_length)
    if isinstance(payload, str):
        return truncate_text(payload, max_length)
    if isinstance(payload, dict):
        return {
            k: truncate_payload(v, max_length, _depth + 1)
            for k, v in payload.items()
        }
    if isinstance(payload, list):
        return [
            truncate_payload(v, max_length, _depth + 1)
            for v in payload
        ]
    return payload
