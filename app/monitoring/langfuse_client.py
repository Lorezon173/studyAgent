# app/monitoring/langfuse_client.py
"""Langfuse 客户端单例管理（适配 langfuse v4 SDK）。

设计要点：
- v4 SDK 已移除 `langfuse.decorators` 模块；不再暴露 `langfuse_context`。
- 对外只暴露 `init_langfuse` / `get_langfuse_client` / `is_langfuse_enabled`。
- 包未安装、key 缺失、`langfuse_enabled=False` 等三种情形均回退为 None，
  调用侧通过 `is_langfuse_enabled()` 判定是否上报。
"""

import logging
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)

# 类型注解：可能未安装 langfuse 或版本不兼容
Langfuse: type | None = None
_langfuse_client: Any = None  # 全局单例

try:
    from langfuse import Langfuse as _Langfuse

    Langfuse = _Langfuse
except ImportError:
    logger.debug("langfuse package not installed, monitoring disabled")


def init_langfuse() -> None:
    """初始化 Langfuse 客户端。

    根据配置决定是否启用：
    - `langfuse_enabled=False` → 跳过
    - 缺少 keys → 警告并跳过
    - 包未安装 → 警告并跳过
    """
    global _langfuse_client

    if not settings.langfuse_enabled:
        logger.debug("Langfuse monitoring is disabled")
        _langfuse_client = None
        return

    if not settings.langfuse_public_key or not settings.langfuse_secret_key:
        logger.warning(
            "Langfuse is enabled but keys are missing. "
            "Set LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY."
        )
        _langfuse_client = None
        return

    if Langfuse is None:
        logger.warning("langfuse package not installed, monitoring disabled")
        _langfuse_client = None
        return

    try:
        _langfuse_client = Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=settings.langfuse_host,
        )
        logger.info(f"Langfuse client initialized, host={settings.langfuse_host}")
    except Exception as e:
        logger.error(f"Failed to initialize Langfuse client: {e}")
        _langfuse_client = None


def get_langfuse_client() -> Any:
    """获取 Langfuse 客户端实例（v4）。

    Returns:
        Langfuse 实例，或 None（未启用 / 初始化失败 / 包未安装）
    """
    global _langfuse_client
    if _langfuse_client is None and settings.langfuse_enabled:
        init_langfuse()
    return _langfuse_client


def is_langfuse_enabled() -> bool:
    """检查 Langfuse 是否启用且可用。"""
    return get_langfuse_client() is not None


# 向后兼容别名（保留旧调用方式）
get_langfuse = get_langfuse_client


# 模块加载时初始化
init_langfuse()
