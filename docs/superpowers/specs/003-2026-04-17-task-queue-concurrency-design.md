# Celery 任务队列并发设计

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Created:** 2026-04-17
**Status:** Approved
**Approach:** 轻量改造（Celery + Redis + SSE）

---

## 1. 概述

### 1.1 目标

为 studyAgent 添加任务队列并发能力，解耦 HTTP 请求与 LangGraph 执行，支持多用户同时访问。

### 1.2 背景

**当前痛点：**
- HTTP 请求同步等待 LangGraph 执行（10s+），导致连接池枯竭
- 多用户同时访问时，请求排队等待
- 无任务状态追踪机制

**解决方案：**
- 使用 Celery 任务队列异步执行 Agent 任务
- 使用 Redis Pub/Sub 实现 SSE 流式响应
- 保持现有代码架构，最小化改动

### 1.3 设计原则

1. **向后兼容：** 默认关闭异步模式，保留现有 `/chat` 同步行为
2. **最小改动：** 不破坏现有 `agent_service.run()` 核心逻辑
3. **优雅降级：** Redis/Worker 不可用时回退到同步模式

---

## 2. 架构设计

### 2.1 整体架构

```
                        ┌──────────────────────────────────────────────────────────┐
                        │                     FastAPI App                          │
                        │  ┌────────────────┐    ┌─────────────────────────────┐   │
                        │  │ POST /chat     │    │ GET /chat/stream/{task_id}  │   │
                        │  │ (提交任务)     │    │ (SSE 流式响应)              │   │
                        │  └───────┬────────┘    └──────────────┬──────────────┘   │
                        │          │                            │                   │
                        │          ▼                            ▼                   │
                        │  ┌────────────────┐    ┌─────────────────────────────┐   │
                        │  │ TaskDispatcher │    │ RedisPubSubListener         │   │
                        │  │ (任务分发器)   │    │ (订阅 task_id 频道)         │   │
                        │  └───────┬────────┘    └──────────────┬──────────────┘   │
                        └──────────┼────────────────────────────┼───────────────────┘
                                   │                            │
                                   ▼                            │
                        ┌─────────────────────┐                │
                        │       Redis         │◀───────────────┘
                        │  ┌───────────────┐  │  Pub/Sub 推送
                        │  │ Task Queue    │  │
                        │  │ Result Store  │  │
                        │  │ Pub/Sub       │  │
                        │  └───────────────┘  │
                        └──────────┬──────────┘
                                   │
                                   ▼
                        ┌─────────────────────┐
                        │   Celery Worker     │
                        │  ┌───────────────┐  │
                        │  │ run_agent_task│──┼──▶ agent_service.run()
                        │  │ (任务执行器)  │  │
                        │  └───────────────┘  │
                        │         │           │
                        │         ▼           │
                        │  ┌───────────────┐  │
                        │  │ ProgressReporter│─┼──▶ Redis Pub/Sub
                        │  │ (进度回调)    │  │
                        │  └───────────────┘  │
                        └─────────────────────┘
```

### 2.2 文件结构

```
app/
├── worker/                    # 新建目录
│   ├── __init__.py           # 模块导出
│   ├── celery_app.py         # Celery 配置
│   ├── tasks.py              # 任务定义
│   └── progress.py           # 进度回调
├── services/
│   ├── task_dispatcher.py    # 新建：任务分发器
│   ├── redis_pubsub.py       # 新建：Pub/Sub 监听器
│   └── agent_service.py      # 修改：添加进度回调参数
├── api/
│   └── chat.py               # 修改：添加异步端点
└── core/
    └── config.py             # 修改：添加配置项
```

---

## 3. API 设计

### 3.1 端点定义

| 端点 | 方法 | 说明 | 响应 |
|------|------|------|------|
| `/chat` | POST | 提交异步任务（异步模式） | `{task_id, status}` |
| `/chat/sync` | POST | 同步执行（保留现有行为） | `{session_id, stage, reply, ...}` |
| `/chat/stream/{task_id}` | GET | SSE 流式响应 | `event: token/progress/done` |
| `/chat/status/{task_id}` | GET | 查询任务状态 | `{status, result, error}` |

### 3.2 配置开关

```python
# config.py
async_chat_enabled: bool = False  # 默认关闭，保持向后兼容
```

### 3.3 请求流程

```
1. POST /chat (async_chat_enabled=True)
   → 返回 {"task_id": "xxx", "status": "pending"}

2. GET /chat/stream/{task_id}
   → SSE 连接，接收实时进度

3. SSE 事件流：
   event: progress
   data: {"stage": "diagnosing", "progress": 20}

   event: token
   data: "AI 回复的文本片段..."

   event: done
   data: {"stage": "completed", "reply": "..."}
```

---

## 4. 组件设计

### 4.1 Celery 配置 (`app/worker/celery_app.py`)

```python
from celery import Celery
from app.core.config import settings

celery_app = Celery(
    "learning_agent",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    task_serializer="json",
    result_serializer="json",
)

celery_app.conf.update(
    task_track_started=True,
    task_time_limit=settings.task_timeout_seconds,
    worker_concurrency=4,
)
```

### 4.2 任务定义 (`app/worker/tasks.py`)

```python
import json
import redis
from app.worker.celery_app import celery_app
from app.services.agent_service import agent_service
from app.core.config import settings

redis_client = redis.from_url(settings.redis_url)

@celery_app.task(bind=True, max_retries=3)
def run_agent_task(self, session_id: str, topic: str | None, 
                   user_input: str, user_id: int | None):
    """执行 Agent 任务，推送进度到 Redis"""
    
    def on_progress(stage: str, progress: int, token: str = None):
        redis_client.publish(
            f"task:{self.request.id}",
            json.dumps({"stage": stage, "progress": progress, "token": token})
        )
    
    result = agent_service.run(
        session_id=session_id,
        topic=topic,
        user_input=user_input,
        user_id=user_id,
        on_progress=on_progress,
    )
    return result
```

### 4.3 Pub/Sub 监听器 (`app/services/redis_pubsub.py`)

```python
import json
from typing import AsyncGenerator
import redis.asyncio as redis
from app.core.config import settings

class RedisPubSubListener:
    def __init__(self):
        self.redis_url = settings.redis_url
    
    async def listen(self, task_id: str) -> AsyncGenerator[dict, None]:
        """监听任务频道，yield 进度事件"""
        client = redis.from_url(self.redis_url)
        pubsub = client.pubsub()
        
        try:
            await pubsub.subscribe(f"task:{task_id}")
            async for message in pubsub.listen():
                if message["type"] == "message":
                    data = json.loads(message["data"])
                    yield data
                    if data.get("stage") == "completed":
                        break
        finally:
            await pubsub.unsubscribe(f"task:{task_id}")
            await client.close()
```

### 4.4 任务分发器 (`app/services/task_dispatcher.py`)

```python
import uuid
from app.worker.tasks import run_agent_task

class TaskDispatcher:
    @staticmethod
    def dispatch(session_id: str, topic: str | None, 
                  user_input: str, user_id: int | None) -> str:
        """分发任务到 Celery 队列，返回 task_id"""
        task_id = str(uuid.uuid4())
        run_agent_task.apply_async(
            kwargs={
                "session_id": session_id,
                "topic": topic,
                "user_input": user_input,
                "user_id": user_id,
            },
            task_id=task_id,
        )
        return task_id
    
    @staticmethod
    def get_status(task_id: str) -> dict:
        """查询任务状态"""
        from celery.result import AsyncResult
        result = AsyncResult(task_id)
        return {
            "task_id": task_id,
            "status": result.state,
            "result": result.result if result.ready() else None,
            "error": str(result.result) if result.failed() else None,
        }

task_dispatcher = TaskDispatcher()
```

---

## 5. 配置设计

### 5.1 环境变量

```env
# Redis 配置
REDIS_URL=redis://localhost:6379/0

# Celery 配置
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/1

# 任务配置
ASYNC_CHAT_ENABLED=false
TASK_TIMEOUT_SECONDS=300
TASK_MAX_RETRIES=3
```

### 5.2 Settings 扩展

```python
# app/core/config.py 新增
redis_url: str = "redis://localhost:6379/0"
celery_broker_url: str = "redis://localhost:6379/0"
celery_result_backend: str = "redis://localhost:6379/1"
async_chat_enabled: bool = False
task_timeout_seconds: int = 300
task_max_retries: int = 3
```

---

## 6. 错误处理与降级

### 6.1 降级策略

| 场景 | 处理方式 |
|------|----------|
| Redis 连接失败 | 回退到同步模式，记录警告日志 |
| Worker 不可用 | 返回 503，提示"服务繁忙，请稍后重试" |
| 任务超时 (5min) | 标记任务失败，返回错误信息 |
| 任务重试 | Celery 自动重试 3 次，指数退避 |
| SSE 连接断开 | 自动重连，最多重试 3 次 |

### 6.2 错误响应格式

```json
{
  "task_id": "xxx",
  "status": "FAILED",
  "error": "Task timed out after 300 seconds",
  "retry_count": 2
}
```

---

## 7. 改动清单

| 文件 | 操作 | 改动量 |
|------|------|--------|
| `app/worker/__init__.py` | 新建 | ~5行 |
| `app/worker/celery_app.py` | 新建 | ~20行 |
| `app/worker/tasks.py` | 新建 | ~40行 |
| `app/worker/progress.py` | 新建 | ~30行 |
| `app/services/task_dispatcher.py` | 新建 | ~40行 |
| `app/services/redis_pubsub.py` | 新建 | ~30行 |
| `app/services/agent_service.py` | 修改 | +10行 |
| `app/api/chat.py` | 修改 | +50行 |
| `app/core/config.py` | 修改 | +6行 |
| `.env.example` | 修改 | +6行 |
| `pyproject.toml` | 修改 | +2行 |

**总改动量：** 新建 ~165 行，修改 ~70 行

---

## 8. 依赖

```toml
[project.dependencies]
celery = ">=5.3.0"
redis = ">=5.0.0"
```

---

## 9. 启动方式

```bash
# 启动 Redis
docker run -d -p 6379:6379 redis:alpine

# 启动 FastAPI
uvicorn app.main:app --reload

# 启动 Celery Worker
celery -A app.worker.celery_app worker --concurrency=4 --loglevel=info
```

---

## 10. 验收标准

1. **功能验收：**
   - [ ] POST /chat 返回 task_id（异步模式）
   - [ ] GET /chat/stream/{task_id} 正确推送 SSE 事件
   - [ ] GET /chat/status/{task_id} 返回正确状态
   - [ ] 多用户同时访问无阻塞

2. **降级验收：**
   - [ ] `ASYNC_CHAT_ENABLED=false` 时回退到同步模式
   - [ ] Redis 不可用时业务正常运行

3. **性能验收：**
   - [ ] 50 并发用户请求无超时
   - [ ] 任务执行延迟 < 500ms
