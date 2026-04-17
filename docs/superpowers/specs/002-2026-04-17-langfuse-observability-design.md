# Langfuse 全链路可观测性设计

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Created:** 2026-04-17
**Status:** Approved
**Approach:** 轻量接入（装饰器模式）

---

## 1. 概述

### 1.1 目标

为 studyAgent 添加 Langfuse 全链路可观测性，在**尽量不对 agent 核心代码改动**的前提下实现监控功能。

### 1.2 范围

- **监控范围：** LLM 调用、RAG 检索、工具执行、会话上下文
- **部署方式：** Langfuse 自托管（Docker）
- **数据策略：** user_id 哈希脱敏，敏感字段过滤

### 1.3 设计原则

1. **最小侵入：** 核心图代码（`nodes.py`、`graph_v2.py`、`routers.py`）零改动
2. **优雅降级：** 监控禁用或失败时，业务逻辑不受影响
3. **配置驱动：** 通过环境变量控制开关，无需代码修改

---

## 2. 架构设计

### 2.1 整体架构

```
┌─────────────────────────────────────────────────────────┐
│                    Agent Service                        │
│  ┌─────────────────────────────────────────────────┐   │
│  │              Langfuse Callback Handler           │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐        │   │
│  │  │ LLM Trace│ │ RAG Trace│ │Tool Trace│        │   │
│  │  └────┬─────┘ └────┬─────┘ └────┬─────┘        │   │
│  └───────┼────────────┼────────────┼──────────────┘   │
│          │            │            │                   │
│  ┌───────▼────────────▼────────────▼──────────────┐   │
│  │              Langfuse SDK (Flask)              │   │
│  └───────────────────────┬────────────────────────┘   │
└──────────────────────────┼────────────────────────────┘
                           │
                           ▼
              ┌────────────────────────┐
              │   Langfuse Self-Host   │
              │      (Docker)          │
              └────────────────────────┘
```

### 2.2 文件结构

```
app/
├── monitoring/
│   ├── __init__.py          # 模块导出
│   ├── langfuse_client.py   # Langfuse 客户端单例
│   ├── trace_wrapper.py     # 装饰器/上下文管理器
│   └── desensitize.py       # 敏感数据脱敏
├── services/
│   ├── llm.py               # 添加 @trace_llm 装饰器
│   └── rag_store.py         # 添加 @trace_rag 装饰器
├── core/
│   └── config.py            # 新增 Langfuse 配置项
└── services/
    └── agent_service.py     # 创建 Trace 会话关联
```

---

## 3. 组件设计

### 3.1 Langfuse 客户端 (`langfuse_client.py`)

**职责：**
- 初始化 Langfuse SDK 连接
- 提供全局 `langfuse` 实例和 `langfuse_context`
- 支持条件初始化（禁用时返回 None）

**接口：**
```python
from langfuse import Langfuse
from langfuse.decorators import langfuse_context

langfuse: Langfuse | None = None

def init_langfuse():
    """根据配置初始化 Langfuse 客户端"""
    ...

def get_langfuse() -> Langfuse | None:
    """获取 Langfuse 客户端实例"""
    return langfuse
```

### 3.2 追踪包装器 (`trace_wrapper.py`)

**职责：**
- 提供 `@trace_llm`、`@trace_rag`、`@trace_tool` 装饰器
- 自动记录输入输出、耗时、元数据
- 处理异常，确保监控失败不影响业务

**装饰器签名：**
```python
def trace_llm(operation: str):
    """追踪 LLM 调用
    Args:
        operation: 操作名称，如 "chat", "embed"
    """
    ...

def trace_rag(operation: str):
    """追踪 RAG 检索
    Args:
        operation: 操作名称，如 "retrieve", "ingest"
    """
    ...

def trace_tool(tool_name: str):
    """追踪工具执行
    Args:
        tool_name: 工具名称
    """
    ...
```

### 3.3 数据脱敏 (`desensitize.py`)

**职责：**
- 对 user_id 进行 SHA256 哈希
- 提供敏感字段过滤功能

**接口：**
```python
import hashlib

def hash_user_id(user_id: str) -> str:
    """对 user_id 进行 SHA256 哈希脱敏
    Returns:
        格式: "hash_<前8位哈希值>"
    """
    if not user_id:
        return "hash_unknown"
    hash_value = hashlib.sha256(user_id.encode()).hexdigest()[:8]
    return f"hash_{hash_value}"

def sanitize_metadata(metadata: dict) -> dict:
    """过滤敏感字段（password, token, api_key 等）"""
    SENSITIVE_KEYS = {"password", "token", "api_key", "secret", "credential"}
    return {k: v for k, v in metadata.items() if k.lower() not in SENSITIVE_KEYS}
```

---

## 4. 数据流设计

### 4.1 Trace 层级结构

```
Trace (Session)
├── user_id: "hash_abc123..."      # 脱敏后的用户ID
├── session_id: "session_xyz"      # 会话ID
├── metadata: {"graph_version": "v2"}
│
├── Span: LLM Call
│   ├── name: "llm_chat"
│   ├── input: {"messages": [...]}  # 脱敏敏感字段
│   ├── output: {"content": "..."}
│   ├── metadata: {"model": "gpt-4", "tokens": 150}
│   └── level: DEFAULT
│
├── Span: RAG Retrieval
│   ├── name: "rag_retrieve"
│   ├── input: {"query": "..."}
│   ├── output: {"chunks_count": 3, "top_scores": [0.9, 0.85]}
│   └── metadata: {"provider": "simple", "latency_ms": 50}
│
└── Span: Tool Execution
    ├── name: "tool_web_search"
    ├── input: {"query": "..."}
    ├── output: {"results": [...]}
    └── metadata: {"tool_name": "web_search"}
```

### 4.2 会话关联机制

在 `agent_service.py` 中，每次调用图时创建 Trace：

```python
from app.monitoring.langfuse_client import langfuse_context
from app.monitoring.desensitize import hash_user_id

def run_with_graph_v2(user_id: str, session_id: str, ...):
    # 创建 Trace（会话开始时）
    trace = langfuse_context.trace(
        name="learning_session",
        user_id=hash_user_id(user_id),
        session_id=session_id,
        metadata={"graph_version": "v2"}
    )
    # 后续 span 自动关联到此 trace
    ...
```

---

## 5. 配置设计

### 5.1 环境变量

```env
# Langfuse 配置
LANGFUSE_PUBLIC_KEY=pk-lf-xxx
LANGFUSE_SECRET_KEY=sk-lf-xxx
LANGFUSE_HOST=http://localhost:3000  # 自托管地址
LANGFUSE_ENABLED=true                 # 开关，方便开发时关闭
```

### 5.2 Settings 扩展

```python
# app/core/config.py
class Settings(BaseSettings):
    # ... 现有配置 ...

    # Langfuse 监控
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "http://localhost:3000"
    langfuse_enabled: bool = False
```

---

## 6. 错误处理与降级

### 6.1 降级策略

| 场景 | 行为 |
|------|------|
| `LANGFUSE_ENABLED=false` | 跳过所有监控，零开销 |
| Langfuse 服务不可用 | 记录警告日志，业务继续 |
| 脱敏失败 | 原始值传空，记录警告 |
| Span 记录异常 | 捕获异常，业务继续 |

### 6.2 装饰器降级实现

```python
def trace_llm(operation: str):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            if not langfuse or not settings.langfuse_enabled:
                # 监控禁用时，直接执行原函数
                return func(*args, **kwargs)

            try:
                with langfuse_context.span(name=f"llm_{operation}") as span:
                    result = func(*args, **kwargs)
                    span.end(output={"content": str(result)[:1000]})
                    return result
            except Exception as e:
                # 监控出错不影响业务
                logger.warning(f"Langfuse trace error: {e}")
                return func(*args, **kwargs)
        return wrapper
    return decorator
```

---

## 7. 改动清单

| 文件 | 操作 | 改动量 |
|------|------|--------|
| `app/monitoring/__init__.py` | 新建 | ~5行 |
| `app/monitoring/langfuse_client.py` | 新建 | ~30行 |
| `app/monitoring/trace_wrapper.py` | 新建 | ~80行 |
| `app/monitoring/desensitize.py` | 新建 | ~20行 |
| `app/core/config.py` | 修改 | +5行 |
| `app/services/llm.py` | 修改 | +3行 |
| `app/services/rag_store.py` | 修改 | +3行 |
| `app/services/agent_service.py` | 修改 | +10行 |
| `.env.example` | 修改 | +4行 |
| `pyproject.toml` | 修改 | +1行（依赖） |

**总改动量：** 新建 ~135 行，修改 ~25 行
**核心图代码改动：** 0 行

---

## 8. 依赖

```toml
[project.dependencies]
langfuse = ">=2.0.0"
```

---

## 9. 验收标准

1. **功能验收：**
   - [ ] Langfuse 自托管实例可访问
   - [ ] LLM 调用被正确追踪（prompt、completion、tokens）
   - [ ] RAG 检索被正确追踪（query、chunks、scores）
   - [ ] 会话上下文正确关联（user_id 脱敏、session_id）

2. **降级验收：**
   - [ ] `LANGFUSE_ENABLED=false` 时业务正常运行
   - [ ] Langfuse 服务不可用时业务正常运行

3. **性能验收：**
   - [ ] 监控开销 < 5% 延迟增加
