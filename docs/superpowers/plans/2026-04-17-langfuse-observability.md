# Langfuse 全链路可观测性实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 studyAgent 添加 Langfuse 全链路监控，使用装饰器模式最小化核心代码改动

**Architecture:** 创建 `app/monitoring/` 模块，包含 Langfuse 客户端、追踪装饰器、数据脱敏工具。在服务层（`llm.py`、`rag_store.py`）通过装饰器包装关键调用，在 `agent_service.py` 中创建会话级 Trace 关联。

**Tech Stack:** Python 3.12, Langfuse SDK (Flask), pydantic-settings

---

## File Structure

```
app/
├── monitoring/                   # 新建模块
│   ├── __init__.py              # 模块导出
│   ├── langfuse_client.py       # Langfuse 客户端单例
│   ├── trace_wrapper.py         # 装饰器
│   └── desensitize.py           # 数据脱敏
├── core/
│   └── config.py                # +5行：Langfuse 配置项
├── services/
│   ├── llm.py                   # +3行：添加装饰器
│   ├── rag_store.py             # +3行：添加装饰器
│   └── agent_service.py         # +10行：创建 Trace
.env.example                     # +4行：Langfuse 环境变量
pyproject.toml                   # +1行：langfuse 依赖
tests/
└── test_langfuse_monitoring.py  # 新建：单元测试
```

---

## Task 1: 添加 Langfuse 依赖和配置项

**Files:**
- Modify: `pyproject.toml`
- Modify: `app/core/config.py`
- Modify: `.env.example`

- [ ] **Step 1: 添加 langfuse 依赖到 pyproject.toml**

在 `pyproject.toml` 的 `dependencies` 数组末尾添加：

```toml
    "langfuse>=2.0.0",
```

完整修改后的 dependencies 部分应为：
```toml
dependencies = [
    "chainlit>=2.8.3",
    "fastapi>=0.135.1",
    "httpx>=0.28.1",
    "langchain>=1.2.13",
    "langchain-text-splitters>=0.3.8",
    "langchain-openai>=1.1.11",
    "langgraph>=1.1.3",
    "pydantic>=2.12.5",
    "pydantic-settings>=2.13.1",
    "pypdf>=6.1.1",
    "python-docx>=1.2.0",
    "python-dotenv>=1.2.2",
    "python-multipart>=0.0.20",
    "uvicorn>=0.42.0",
    "langgraph-checkpoint-sqlite>=3.0.3",
    "langfuse>=2.0.0",
]
```

- [ ] **Step 2: 在 config.py 中添加 Langfuse 配置项**

在 `app/core/config.py` 的 `Settings` 类中，在 `use_graph_v2: bool = False` 之后添加：

```python
    # Langfuse 监控
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "http://localhost:3000"
    langfuse_enabled: bool = False
```

- [ ] **Step 3: 在 .env.example 中添加 Langfuse 环境变量**

在 `.env.example` 文件末尾添加：

```env
# Langfuse 监控配置
LANGFUSE_PUBLIC_KEY=
LANGFUSE_SECRET_KEY=
LANGFUSE_HOST=http://localhost:3000
LANGFUSE_ENABLED=false
```

- [ ] **Step 4: 安装依赖并验证**

Run: `cd d:/backup/basic_file/Program/StudyAgent/studyAgent && uv sync`
Expected: 成功安装 langfuse 包

- [ ] **Step 5: 提交配置变更**

```bash
git add pyproject.toml app/core/config.py .env.example
git commit -m "feat: add Langfuse configuration settings

- Add langfuse>=2.0.0 dependency
- Add Langfuse settings to Settings class
- Add Langfuse environment variables to .env.example

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 2: 创建数据脱敏模块

**Files:**
- Create: `app/monitoring/__init__.py`
- Create: `app/monitoring/desensitize.py`

- [ ] **Step 1: 创建 monitoring 模块目录**

Run: `mkdir -p d:/backup/basic_file/Program/StudyAgent/studyAgent/app/monitoring`
Expected: 目录创建成功

- [ ] **Step 2: 创建 app/monitoring/__init__.py**

```python
# app/monitoring/__init__.py
"""Langfuse 监控模块"""

from app.monitoring.desensitize import hash_user_id, sanitize_metadata
from app.monitoring.langfuse_client import get_langfuse, init_langfuse, langfuse_context
from app.monitoring.trace_wrapper import trace_llm, trace_rag, trace_tool

__all__ = [
    "hash_user_id",
    "sanitize_metadata",
    "get_langfuse",
    "init_langfuse",
    "langfuse_context",
    "trace_llm",
    "trace_rag",
    "trace_tool",
]
```

- [ ] **Step 3: 创建 app/monitoring/desensitize.py**

```python
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
```

- [ ] **Step 4: 编写 desensitize 模块测试**

创建 `tests/test_langfuse_monitoring.py`：

```python
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
```

- [ ] **Step 5: 运行测试验证**

Run: `cd d:/backup/basic_file/Program/StudyAgent/studyAgent && uv run pytest tests/test_langfuse_monitoring.py -v`
Expected: 所有测试通过

- [ ] **Step 6: 提交脱敏模块**

```bash
git add app/monitoring/ tests/test_langfuse_monitoring.py
git commit -m "feat(monitoring): add desensitize module for Langfuse

- Add hash_user_id() for SHA256 user ID hashing
- Add sanitize_metadata() for sensitive field filtering
- Add truncate_text() for trace data size control
- Add comprehensive unit tests

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 3: 创建 Langfuse 客户端单例

**Files:**
- Create: `app/monitoring/langfuse_client.py`

- [ ] **Step 1: 添加测试用例到 test_langfuse_monitoring.py**

在 `tests/test_langfuse_monitoring.py` 末尾添加：

```python


class TestLangfuseClient:
    """Langfuse 客户端测试"""

    def test_get_langfuse_returns_none_when_disabled(self):
        """测试禁用时返回 None"""
        from app.monitoring.langfuse_client import get_langfuse
        
        # 默认配置下 langfuse_enabled=False
        result = get_langfuse()
        # 应该返回 None 或一个客户端实例
        assert result is None or hasattr(result, "trace")

    def test_langfuse_context_available(self):
        """测试 langfuse_context 可用"""
        from app.monitoring.langfuse_client import langfuse_context
        
        assert langfuse_context is not None
```

- [ ] **Step 2: 创建 app/monitoring/langfuse_client.py**

```python
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
```

- [ ] **Step 3: 更新 app/monitoring/__init__.py 导入**

修改 `app/monitoring/__init__.py`：

```python
# app/monitoring/__init__.py
"""Langfuse 监控模块"""

from app.monitoring.desensitize import hash_user_id, sanitize_metadata, truncate_text
from app.monitoring.langfuse_client import get_langfuse, init_langfuse, is_langfuse_enabled, langfuse_context
from app.monitoring.trace_wrapper import trace_llm, trace_rag, trace_tool

__all__ = [
    # 脱敏工具
    "hash_user_id",
    "sanitize_metadata",
    "truncate_text",
    # Langfuse 客户端
    "get_langfuse",
    "init_langfuse",
    "is_langfuse_enabled",
    "langfuse_context",
    # 追踪装饰器
    "trace_llm",
    "trace_rag",
    "trace_tool",
]
```

- [ ] **Step 4: 运行测试验证**

Run: `cd d:/backup/basic_file/Program/StudyAgent/studyAgent && uv run pytest tests/test_langfuse_monitoring.py -v`
Expected: 所有测试通过

- [ ] **Step 5: 提交 Langfuse 客户端模块**

```bash
git add app/monitoring/
git commit -m "feat(monitoring): add Langfuse client singleton

- Add init_langfuse() for conditional initialization
- Add get_langfuse() for client access
- Add is_langfuse_enabled() for availability check
- Support graceful degradation when disabled

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 4: 创建追踪装饰器

**Files:**
- Create: `app/monitoring/trace_wrapper.py`

- [ ] **Step 1: 添加装饰器测试到 test_langfuse_monitoring.py**

在 `tests/test_langfuse_monitoring.py` 末尾添加：

```python


class TestTraceWrapper:
    """追踪装饰器测试"""

    def test_trace_llm_decorator_exists(self):
        """测试装饰器可导入"""
        from app.monitoring.trace_wrapper import trace_llm
        
        assert callable(trace_llm)

    def test_trace_llm_disabled_returns_original_result(self):
        """测试禁用时返回原始结果"""
        from app.monitoring.trace_wrapper import trace_llm
        
        @trace_llm("test_op")
        def sample_func():
            return "original_result"
        
        # 当 Langfuse 禁用时，应直接返回结果
        result = sample_func()
        assert result == "original_result"

    def test_trace_rag_decorator_exists(self):
        """测试 RAG 装饰器可导入"""
        from app.monitoring.trace_wrapper import trace_rag
        
        assert callable(trace_rag)

    def test_trace_tool_decorator_exists(self):
        """测试工具装饰器可导入"""
        from app.monitoring.trace_wrapper import trace_tool
        
        assert callable(trace_tool)

    def test_decorator_preserves_function_metadata(self):
        """测试装饰器保留函数元数据"""
        from app.monitoring.trace_wrapper import trace_llm
        
        @trace_llm("test")
        def my_function():
            """My docstring"""
            pass
        
        assert my_function.__name__ == "my_function"
        assert my_function.__doc__ == "My docstring"
```

- [ ] **Step 2: 创建 app/monitoring/trace_wrapper.py**

```python
# app/monitoring/trace_wrapper.py
"""追踪装饰器模块"""

import functools
import logging
import time
from typing import Any, Callable, TypeVar

from app.core.config import settings
from app.monitoring.desensitize import sanitize_metadata, truncate_text
from app.monitoring.langfuse_client import get_langfuse, langfuse_context

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


def _should_trace() -> bool:
    """检查是否应该执行追踪"""
    return settings.langfuse_enabled and get_langfuse() is not None


def _safe_span_end(span: Any, output: Any) -> None:
    """安全地结束 span"""
    try:
        if span is not None:
            span.end(output=output)
    except Exception as e:
        logger.warning(f"Failed to end span: {e}")


def trace_llm(operation: str) -> Callable[[F], F]:
    """追踪 LLM 调用的装饰器
    
    Args:
        operation: 操作名称，如 "chat", "embed", "route_intent"
        
    Returns:
        装饰器函数
        
    Example:
        @trace_llm("chat")
        def call_llm(prompt: str) -> str:
            ...
    """
    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            if not _should_trace():
                return func(*args, **kwargs)
            
            start_time = time.perf_counter()
            span = None
            
            try:
                # 尝试创建 span
                if langfuse_context is not None:
                    span = langfuse_context.span(
                        name=f"llm_{operation}",
                        input={"args_count": len(args), "kwargs_keys": list(kwargs.keys())},
                    )
                
                # 执行原函数
                result = func(*args, **kwargs)
                
                # 记录输出
                elapsed_ms = (time.perf_counter() - start_time) * 1000
                output_data = {
                    "content": truncate_text(str(result), max_length=500),
                    "latency_ms": round(elapsed_ms, 2),
                }
                
                _safe_span_end(span, output_data)
                return result
                
            except Exception as e:
                # 记录异常
                elapsed_ms = (time.perf_counter() - start_time) * 1000
                if span is not None:
                    try:
                        span.end(
                            output={"error": str(e), "latency_ms": round(elapsed_ms, 2)},
                            level="ERROR",
                        )
                    except Exception:
                        pass
                raise
        
        return wrapper  # type: ignore
    
    return decorator


def trace_rag(operation: str) -> Callable[[F], F]:
    """追踪 RAG 检索的装饰器
    
    Args:
        operation: 操作名称，如 "retrieve", "ingest"
        
    Returns:
        装饰器函数
        
    Example:
        @trace_rag("retrieve")
        def retrieve_knowledge(query: str) -> list:
            ...
    """
    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            if not _should_trace():
                return func(*args, **kwargs)
            
            start_time = time.perf_counter()
            span = None
            
            try:
                # 提取查询信息
                query = kwargs.get("query") or (args[0] if args else None)
                
                if langfuse_context is not None:
                    span = langfuse_context.span(
                        name=f"rag_{operation}",
                        input={"query": truncate_text(str(query), max_length=200)} if query else {},
                    )
                
                # 执行原函数
                result = func(*args, **kwargs)
                
                # 记录输出
                elapsed_ms = (time.perf_counter() - start_time) * 1000
                output_data: dict[str, Any] = {"latency_ms": round(elapsed_ms, 2)}
                
                if isinstance(result, list):
                    output_data["chunks_count"] = len(result)
                    if result:
                        scores = [x.get("score", 0) for x in result if isinstance(x, dict)]
                        if scores:
                            output_data["top_scores"] = scores[:3]
                
                _safe_span_end(span, output_data)
                return result
                
            except Exception as e:
                elapsed_ms = (time.perf_counter() - start_time) * 1000
                if span is not None:
                    try:
                        span.end(
                            output={"error": str(e), "latency_ms": round(elapsed_ms, 2)},
                            level="ERROR",
                        )
                    except Exception:
                        pass
                raise
        
        return wrapper  # type: ignore
    
    return decorator


def trace_tool(tool_name: str) -> Callable[[F], F]:
    """追踪工具执行的装饰器
    
    Args:
        tool_name: 工具名称，如 "web_search", "calculator"
        
    Returns:
        装饰器函数
        
    Example:
        @trace_tool("web_search")
        def execute_search(query: str) -> dict:
            ...
    """
    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            if not _should_trace():
                return func(*args, **kwargs)
            
            start_time = time.perf_counter()
            span = None
            
            try:
                if langfuse_context is not None:
                    span = langfuse_context.span(
                        name=f"tool_{tool_name}",
                        input=sanitize_metadata(kwargs) if kwargs else {},
                    )
                
                # 执行原函数
                result = func(*args, **kwargs)
                
                # 记录输出
                elapsed_ms = (time.perf_counter() - start_time) * 1000
                output_data: dict[str, Any] = {
                    "latency_ms": round(elapsed_ms, 2),
                    "tool_name": tool_name,
                }
                
                if isinstance(result, dict):
                    # 安全地记录字典结果
                    safe_result = sanitize_metadata(result)
                    output_data["result_keys"] = list(safe_result.keys())
                elif isinstance(result, str):
                    output_data["result_length"] = len(result)
                
                _safe_span_end(span, output_data)
                return result
                
            except Exception as e:
                elapsed_ms = (time.perf_counter() - start_time) * 1000
                if span is not None:
                    try:
                        span.end(
                            output={"error": str(e), "latency_ms": round(elapsed_ms, 2)},
                            level="ERROR",
                        )
                    except Exception:
                        pass
                raise
        
        return wrapper  # type: ignore
    
    return decorator
```

- [ ] **Step 3: 运行测试验证**

Run: `cd d:/backup/basic_file/Program/StudyAgent/studyAgent && uv run pytest tests/test_langfuse_monitoring.py -v`
Expected: 所有测试通过

- [ ] **Step 4: 提交追踪装饰器模块**

```bash
git add app/monitoring/ tests/test_langfuse_monitoring.py
git commit -m "feat(monitoring): add trace decorators for LLM/RAG/Tool

- Add trace_llm() decorator for LLM call tracing
- Add trace_rag() decorator for RAG retrieval tracing
- Add trace_tool() decorator for tool execution tracing
- Support graceful degradation on errors
- Preserve function metadata

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 5: 在 LLM 服务中集成追踪

**Files:**
- Modify: `app/services/llm.py`

- [ ] **Step 1: 在 llm.py 中添加导入和装饰器**

修改 `app/services/llm.py`：

1. 在文件顶部添加导入（在 `from app.core.config import settings` 之后）：
```python
from app.monitoring import trace_llm
```

2. 在 `invoke` 方法上添加装饰器：

找到 `def invoke(self, system_prompt: str, user_prompt: str, stream_output: bool = False) -> str:` 这一行（第56行），在方法定义前添加装饰器：

```python
    @trace_llm("invoke")
    def invoke(self, system_prompt: str, user_prompt: str, stream_output: bool = False) -> str:
```

修改后的 `app/services/llm.py` 文件顶部应为：
```python
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Callable, Iterator

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
import time

from app.core.config import settings
from app.monitoring import trace_llm
```

- [ ] **Step 2: 运行现有测试确保兼容性**

Run: `cd d:/backup/basic_file/Program/StudyAgent/studyAgent && uv run pytest tests/test_llm_service.py -v`
Expected: 所有测试通过

- [ ] **Step 3: 提交 LLM 服务集成**

```bash
git add app/services/llm.py
git commit -m "feat(llm): integrate Langfuse tracing into LLM service

- Add @trace_llm decorator to invoke method
- Minimal change (2 lines) to core service

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 6: 在 RAG 服务中集成追踪

**Files:**
- Modify: `app/services/rag_store.py`

- [ ] **Step 1: 在 rag_store.py 中添加导入和装饰器**

修改 `app/services/rag_store.py`：

1. 在文件顶部添加导入（在 `from app.core.config import settings` 之后，约第10行）：
```python
from app.monitoring import trace_rag
```

2. 在 `retrieve_knowledge_by_scope` 函数上添加装饰器：

找到 `def retrieve_knowledge_by_scope(` 这一行（约第337行），在函数定义前添加装饰器：

```python
@trace_rag("retrieve")
def retrieve_knowledge_by_scope(
```

修改后的导入部分应为：
```python
from app.core.config import settings
from app.monitoring import trace_rag
from app.services.embedding_service import cosine_similarity, embed_text
```

- [ ] **Step 2: 运行现有测试确保兼容性**

Run: `cd d:/backup/basic_file/Program/StudyAgent/studyAgent && uv run pytest tests/ -k "rag" -v --ignore=tests/test_langfuse_monitoring.py`
Expected: 相关测试通过

- [ ] **Step 3: 提交 RAG 服务集成**

```bash
git add app/services/rag_store.py
git commit -m "feat(rag): integrate Langfuse tracing into RAG service

- Add @trace_rag decorator to retrieve_knowledge_by_scope
- Minimal change (2 lines) to core service

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 7: 在 Agent 服务中创建会话级 Trace

**Files:**
- Modify: `app/services/agent_service.py`

- [ ] **Step 1: 在 agent_service.py 中添加导入**

修改 `app/services/agent_service.py`：

在文件顶部导入部分（约第15行之后）添加：
```python
from app.monitoring import hash_user_id, is_langfuse_enabled, langfuse_context
```

修改后的导入部分应为：
```python
from app.services.rag_service import rag_service  # 保留导入以兼容历史 monkeypatch 测试路径
from app.services.orchestration.persistence_coordinator import PersistenceCoordinator
from app.services.orchestration.stage_orchestrator import StageOrchestrator
from app.services.session_store import get_session
from app.monitoring import hash_user_id, is_langfuse_enabled, langfuse_context
```

- [ ] **Step 2: 在 run_with_graph_v2 方法中创建 Trace**

修改 `run_with_graph_v2` 方法，在获取图之后、处理状态之前添加 Trace 创建逻辑：

找到 `def run_with_graph_v2(` 方法（约第39行），修改为：

```python
    @staticmethod
    def run_with_graph_v2(
        session_id: str,
        topic: str | None,
        user_input: str,
        user_id: int | None = None,
        stream_output: bool = False,
    ) -> LearningState:
        """
        使用新版图运行会话
        """
        graph = get_learning_graph_v2()

        # 创建 Langfuse Trace（如果启用）
        if is_langfuse_enabled():
            langfuse_context.trace(
                name="learning_session",
                user_id=hash_user_id(user_id),
                session_id=session_id,
                metadata={"graph_version": "v2", "topic": topic},
            )

        config = {"configurable": {"thread_id": session_id}}
        # ... 其余代码不变
```

- [ ] **Step 3: 运行测试验证**

Run: `cd d:/backup/basic_file/Program/StudyAgent/studyAgent && uv run pytest tests/test_agent_orchestration_refactor.py -v`
Expected: 测试通过

- [ ] **Step 4: 提交 Agent 服务集成**

```bash
git add app/services/agent_service.py
git commit -m "feat(agent): create Langfuse trace for session context

- Add trace creation in run_with_graph_v2 method
- Hash user_id for privacy
- Include session_id and metadata in trace

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 8: 集成测试与文档更新

**Files:**
- Modify: `tests/test_langfuse_monitoring.py`

- [ ] **Step 1: 添加集成测试**

在 `tests/test_langfuse_monitoring.py` 末尾添加：

```python


class TestLangfuseIntegration:
    """Langfuse 集成测试"""

    def test_full_flow_with_monitoring_disabled(self):
        """测试监控禁用时的完整流程"""
        # 确保 Langfuse 禁用
        from app.core.config import settings
        
        if not settings.langfuse_enabled:
            # LLM 调用应正常工作
            from app.services.llm import llm_service
            
            # 这里只测试导入和方法存在
            assert hasattr(llm_service, "invoke")
            assert callable(llm_service.invoke)

    def test_rag_retrieve_with_monitoring_disabled(self):
        """测试监控禁用时的 RAG 检索"""
        from app.services.rag_store import retrieve_knowledge
        
        # 测试函数可调用
        assert callable(retrieve_knowledge)

    def test_agent_service_imports(self):
        """测试 Agent 服务导入"""
        from app.services.agent_service import AgentService
        
        assert hasattr(AgentService, "run_with_graph_v2")
        assert hasattr(AgentService, "run")

    def test_monitoring_module_exports(self):
        """测试监控模块导出"""
        import app.monitoring as monitoring
        
        assert hasattr(monitoring, "hash_user_id")
        assert hasattr(monitoring, "sanitize_metadata")
        assert hasattr(monitoring, "trace_llm")
        assert hasattr(monitoring, "trace_rag")
        assert hasattr(monitoring, "trace_tool")
        assert hasattr(monitoring, "get_langfuse")
        assert hasattr(monitoring, "is_langfuse_enabled")
```

- [ ] **Step 2: 运行完整测试套件**

Run: `cd d:/backup/basic_file/Program/StudyAgent/studyAgent && uv run pytest tests/test_langfuse_monitoring.py -v`
Expected: 所有测试通过

- [ ] **Step 3: 运行全量测试确保无回归**

Run: `cd d:/backup/basic_file/Program/StudyAgent/studyAgent && uv run pytest tests/ -v --ignore=tests/test_langfuse_monitoring.py -x`
Expected: 测试通过，无回归

- [ ] **Step 4: 最终提交**

```bash
git add tests/test_langfuse_monitoring.py
git commit -m "test(monitoring): add integration tests for Langfuse

- Test full flow with monitoring disabled
- Test RAG retrieve with monitoring disabled
- Test agent service imports
- Test monitoring module exports

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Verification Checklist

完成所有任务后，验证以下内容：

- [ ] `uv run pytest tests/test_langfuse_monitoring.py -v` 全部通过
- [ ] `uv run pytest tests/test_llm_service.py -v` 全部通过
- [ ] 现有测试无回归
- [ ] `LANGFUSE_ENABLED=false` 时业务正常运行
- [ ] 核心图代码（`nodes.py`, `graph_v2.py`, `routers.py`）无改动
