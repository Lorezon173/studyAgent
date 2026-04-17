# app/monitoring/desensitize.py
"""敏感数据脱敏工具"""

import hashlib
import logging

logger = logging.getLogger(__name__)

SENSITIVE_KEYS = frozenset({
    "password", "token", "api_key", "secret", "credential",
    "authorization", "auth", "key", "private_key", "access_token",
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
