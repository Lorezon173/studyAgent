# tests/test_langfuse_monitoring.py
"""Langfuse 监控模块单元测试"""

import pytest

from app.monitoring.desensitize import (
    hash_user_id,
    sanitize_metadata,
    truncate_text,
)


class TestHashUserId:
    """user_id 哈希脱敏测试"""

    def test_hash_string_user_id(self):
        """测试字符串 user_id 哈希"""
        result = hash_user_id("user123")
        assert result.startswith("hash_")
        assert len(result) == 13  # "hash_" + 8 chars

    def test_hash_integer_user_id(self):
        """测试整数 user_id 哈希"""
        result = hash_user_id(12345)
        assert result.startswith("hash_")
        assert len(result) == 13

    def test_hash_none_user_id(self):
        """测试 None user_id"""
        result = hash_user_id(None)
        assert result == "hash_unknown"

    def test_hash_empty_string(self):
        """测试空字符串"""
        result = hash_user_id("")
        assert result == "hash_unknown"

    def test_hash_consistency(self):
        """测试相同输入产生相同输出"""
        result1 = hash_user_id("same_user")
        result2 = hash_user_id("same_user")
        assert result1 == result2

    def test_hash_different_inputs(self):
        """测试不同输入产生不同输出"""
        result1 = hash_user_id("user1")
        result2 = hash_user_id("user2")
        assert result1 != result2


class TestSanitizeMetadata:
    """元数据脱敏测试"""

    def test_sanitize_removes_password(self):
        """测试移除 password 字段"""
        data = {"name": "test", "password": "secret123"}
        result = sanitize_metadata(data)
        assert result == {"name": "test"}

    def test_sanitize_removes_api_key(self):
        """测试移除 api_key 字段"""
        data = {"model": "gpt-4", "api_key": "sk-xxx"}
        result = sanitize_metadata(data)
        assert result == {"model": "gpt-4"}

    def test_sanitize_case_insensitive(self):
        """测试大小写不敏感"""
        data = {"API_KEY": "xxx", "Token": "yyy", "SECRET": "zzz"}
        result = sanitize_metadata(data)
        assert result == {}

    def test_sanitize_keeps_safe_fields(self):
        """测试保留安全字段"""
        data = {"model": "gpt-4", "tokens": 100, "latency_ms": 50}
        result = sanitize_metadata(data)
        assert result == data

    def test_sanitize_none_input(self):
        """测试 None 输入"""
        result = sanitize_metadata(None)
        assert result == {}

    def test_sanitize_empty_dict(self):
        """测试空字典"""
        result = sanitize_metadata({})
        assert result == {}


class TestTruncateText:
    """文本截断测试"""

    def test_truncate_short_text(self):
        """测试短文本不截断"""
        text = "short text"
        result = truncate_text(text, max_length=100)
        assert result == text

    def test_truncate_long_text(self):
        """测试长文本截断"""
        text = "a" * 2000
        result = truncate_text(text, max_length=1000)
        assert len(result) == 1014  # 1000 + "...[truncated]"
        assert result.endswith("...[truncated]")

    def test_truncate_none(self):
        """测试 None 输入"""
        result = truncate_text(None)
        assert result == ""

    def test_truncate_empty(self):
        """测试空字符串"""
        result = truncate_text("")
        assert result == ""
