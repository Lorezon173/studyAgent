# app/monitoring/langfuse_client.py
"""Langfuse 客户端单例管理"""

import logging
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)

# 类型注解：可能未安装 langfuse
Langfuse: type | None = None
langfuse_context: Any = None
langfuse: Any = None

# 尝试导入 Langfuse
try:
    from langfuse import Langfuse as _Langfuse
    from langfuse.decorators import langfuse_context as _langfuse_context

    Langfuse = _Langfuse
    langfuse_context = _langfuse_context
except ImportError:
    logger.debug("langfuse package not installed, monitoring disabled")


def init_langfuse() -> None:
    """初始化 Langfuse 客户端

    根据配置决定是否启用 Langfuse：
    - 如果 langfuse_enabled=False，不初始化
    - 如果缺少必要的 key，记录警告并跳过
    """
    global langfuse

    if not settings.langfuse_enabled:
        logger.debug("Langfuse monitoring is disabled")
        langfuse = None
        return

    if not settings.langfuse_public_key or not settings.langfuse_secret_key:
        logger.warning(
            "Langfuse is enabled but keys are missing. "
            "Set LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY."
        )
        langfuse = None
        return

    if Langfuse is None:
        logger.warning("langfuse package not installed, monitoring disabled")
        langfuse = None
        return

    try:
        langfuse = Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=settings.langfuse_host,
        )
        logger.info(f"Langfuse client initialized, host={settings.langfuse_host}")
    except Exception as e:
        logger.error(f"Failed to initialize Langfuse client: {e}")
        langfuse = None


def get_langfuse() -> Any:
    """获取 Langfuse 客户端实例

    Returns:
        Langfuse 客户端实例，或 None（如果未启用/初始化失败）
    """
    global langfuse
    if langfuse is None and settings.langfuse_enabled:
        init_langfuse()
    return langfuse


def is_langfuse_enabled() -> bool:
    """检查 Langfuse 是否启用且可用

    Returns:
        True 如果 Langfuse 可用
    """
    return get_langfuse() is not None


# 模块加载时初始化
init_langfuse()
