"""
检查点存储配置
支持SQLite持久化存储会话状态
"""

from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.sqlite import SqliteSaver

from app.core.config import settings

# 单例检查点存储器
_checkpointer = None


def get_checkpointer():
    """
    获取检查点存储器

    根据配置选择存储后端：
    - SQLite: 持久化存储，支持进程重启后恢复
    - Memory: 内存存储，仅用于开发测试
    """
    global _checkpointer
    if _checkpointer is not None:
        return _checkpointer

    backend = settings.session_store_backend.lower()

    if backend == "sqlite":
        _checkpointer = SqliteSaver.from_conn_string(settings.session_sqlite_path)
    else:
        _checkpointer = MemorySaver()

    return _checkpointer


def reset_checkpointer():
    """重置检查点存储器（用于测试）"""
    global _checkpointer
    _checkpointer = None
