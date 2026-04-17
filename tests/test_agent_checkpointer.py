# tests/test_agent_checkpointer.py
"""
检查点功能测试
"""

import os
import tempfile

import pytest

from app.agent.checkpointer import get_checkpointer, reset_checkpointer
from app.core.config import settings


class TestCheckpointer:
    """检查点测试"""

    def test_get_checkpointer_returns_memory_saver_by_default(self, monkeypatch):
        """默认使用内存存储"""
        reset_checkpointer()
        monkeypatch.setattr(settings, "session_store_backend", "memory")

        checkpointer = get_checkpointer()
        assert checkpointer is not None
        reset_checkpointer()

    def test_get_checkpointer_returns_sqlite_saver_when_configured(self, monkeypatch):
        """配置SQLite时使用SQLite存储"""
        reset_checkpointer()

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_checkpointer.db")
            monkeypatch.setattr(settings, "session_store_backend", "sqlite")
            monkeypatch.setattr(settings, "session_sqlite_path", db_path)

            checkpointer = get_checkpointer()
            assert checkpointer is not None

        reset_checkpointer()

    def test_checkpointer_singleton(self, monkeypatch):
        """检查点是单例"""
        reset_checkpointer()
        monkeypatch.setattr(settings, "session_store_backend", "memory")

        c1 = get_checkpointer()
        c2 = get_checkpointer()
        assert c1 is c2

        reset_checkpointer()

    def test_reset_checkpointer_creates_new_instance(self, monkeypatch):
        """重置后创建新实例"""
        reset_checkpointer()
        monkeypatch.setattr(settings, "session_store_backend", "memory")

        c1 = get_checkpointer()
        reset_checkpointer()
        c2 = get_checkpointer()

        assert c1 is not c2

        reset_checkpointer()
