# Celery Task Queue Concurrency Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不破坏现有同步 `/chat` 行为的前提下，新增 Celery+Redis 异步任务队列与 SSE 流式回传，支持多用户并发访问。

**Architecture:** 通过 `async_chat_enabled` 开关控制新旧路径：异步开启时，`POST /chat` 仅提交任务并返回 `task_id`；客户端通过 `/chat/stream/{task_id}` 与 `/chat/status/{task_id}` 拉取进度与结果。Worker 端调用现有 `agent_service.run()`，通过 Redis Pub/Sub 推送阶段进度和 token 事件，API 层仅做分发与转发，保持核心编排逻辑最小改动。

**Tech Stack:** FastAPI, Celery, Redis (sync + asyncio client), Pydantic, pytest, docker-compose

## 实施落地记录（2026-04-18）

- **当前状态：已完成**
- **分支：** `feature/task-queue-concurrency`（worktree: `.worktrees/task-queue-concurrency`）
- **实现结果：**
  - 已落地 Celery Worker、Task Dispatcher、Redis Pub/Sub Listener、异步 `/chat` 提交、`/chat/status/{task_id}`、`/chat/stream/{task_id}`。
  - 已保留同步路径 `/chat/sync`，并通过 `ASYNC_CHAT_ENABLED` 开关控制行为。
  - 已补齐重试语义、SSE race 条件、超时终止语义与资源清理等关键稳定性修复。
- **结果验证：** 关键测试集 `tests/test_chat_async_api.py tests/test_chat_stream_api.py tests/test_task_dispatcher.py tests/test_redis_pubsub.py` 全部通过（33 passed）。

---

## File Structure

- Create: `app/worker/__init__.py`
- Create: `app/worker/celery_app.py`
- Create: `app/worker/tasks.py`
- Create: `app/worker/progress.py`
- Create: `app/services/task_dispatcher.py`
- Create: `app/services/redis_pubsub.py`
- Modify: `app/core/config.py`
- Modify: `app/models/schemas.py`
- Modify: `app/services/agent_service.py`
- Modify: `app/api/chat.py`
- Modify: `pyproject.toml`
- Modify: `.env.example`
- Modify: `docker-compose.yml`
- Test: `tests/test_chat_async_api.py` (new)
- Test: `tests/test_task_dispatcher.py` (new)
- Test: `tests/test_redis_pubsub.py` (new)
- Test: `tests/test_chat_stream_api.py` (modify)

### Task 1: 配置与依赖基线（开关、依赖、响应模型）

**Files:**
- Modify: `app/core/config.py`
- Modify: `app/models/schemas.py`
- Modify: `pyproject.toml`
- Modify: `.env.example`
- Test: `tests/test_chat_async_api.py`

- [ ] **Step 1: 写失败测试（异步开关开启时 `/chat` 返回 task_id 响应）**

```python
# tests/test_chat_async_api.py
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_chat_returns_task_id_when_async_enabled(monkeypatch):
    monkeypatch.setattr("app.api.chat.settings.async_chat_enabled", True)
    monkeypatch.setattr("app.api.chat.task_dispatcher.dispatch", lambda **kwargs: "task-123")

    resp = client.post(
        "/chat",
        json={"session_id": "s-1", "topic": "二分查找", "user_input": "解释一下", "user_id": 1},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["task_id"] == "task-123"
    assert body["status"] == "pending"
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `uv run pytest tests/test_chat_async_api.py::test_chat_returns_task_id_when_async_enabled -v`  
Expected: FAIL（`task_dispatcher` 未实现或 `/chat` 仍返回旧同步模型）。

- [ ] **Step 3: 增加配置、模型与依赖（最小实现）**

```python
# app/core/config.py (新增字段)
redis_url: str = "redis://localhost:6379/0"
celery_broker_url: str = "redis://localhost:6379/0"
celery_result_backend: str = "redis://localhost:6379/1"
async_chat_enabled: bool = False
task_timeout_seconds: int = 300
task_max_retries: int = 3
```

```python
# app/models/schemas.py (新增模型)
class AsyncChatSubmitResponse(BaseModel):
    task_id: str
    status: str


class TaskStatusResponse(BaseModel):
    task_id: str
    status: str
    result: dict | None = None
    error: str | None = None
```

```toml
# pyproject.toml (dependencies 新增)
"celery>=5.3.0",
"redis>=5.0.0",
```

```env
# .env.example 新增
REDIS_URL=redis://localhost:6379/0
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/1
ASYNC_CHAT_ENABLED=false
TASK_TIMEOUT_SECONDS=300
TASK_MAX_RETRIES=3
```

- [ ] **Step 4: 运行测试（仍可能因任务模块缺失失败，符合 TDD 过渡）**

Run: `uv run pytest tests/test_chat_async_api.py::test_chat_returns_task_id_when_async_enabled -v`  
Expected: FAIL（若 `app.api.chat` 尚未接入异步路径）。

- [ ] **Step 5: 提交**

```bash
git add app/core/config.py app/models/schemas.py pyproject.toml .env.example tests/test_chat_async_api.py
git commit -m "chore: add async queue config and response schemas baseline"
```

### Task 2: Worker 与任务分发层（Celery/Redis）

**Files:**
- Create: `app/worker/__init__.py`
- Create: `app/worker/celery_app.py`
- Create: `app/worker/progress.py`
- Create: `app/worker/tasks.py`
- Create: `app/services/task_dispatcher.py`
- Test: `tests/test_task_dispatcher.py`

- [ ] **Step 1: 写失败测试（dispatch 返回 task_id 并调用 apply_async）**

```python
# tests/test_task_dispatcher.py
from app.services.task_dispatcher import task_dispatcher


def test_dispatch_calls_apply_async(monkeypatch):
    captured = {}

    def fake_apply_async(*, kwargs, task_id):
        captured["kwargs"] = kwargs
        captured["task_id"] = task_id

    monkeypatch.setattr("app.services.task_dispatcher.run_agent_task.apply_async", fake_apply_async)

    task_id = task_dispatcher.dispatch(
        session_id="s-1",
        topic="图论",
        user_input="解释最短路",
        user_id=1,
    )

    assert task_id == captured["task_id"]
    assert captured["kwargs"]["session_id"] == "s-1"
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `uv run pytest tests/test_task_dispatcher.py::test_dispatch_calls_apply_async -v`  
Expected: FAIL（`task_dispatcher` 或 `run_agent_task` 尚未实现）。

- [ ] **Step 3: 实现 Celery app、ProgressReporter、task 与 dispatcher**

```python
# app/worker/celery_app.py
from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "learning_agent",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    task_track_started=True,
    task_time_limit=settings.task_timeout_seconds,
)
```

```python
# app/worker/progress.py
import json
import redis

from app.core.config import settings


class ProgressReporter:
    def __init__(self, task_id: str):
        self.task_id = task_id
        self.client = redis.from_url(settings.redis_url)

    def publish(self, event: str, payload: dict) -> None:
        self.client.publish(f"task:{self.task_id}", json.dumps({"event": event, **payload}, ensure_ascii=False))
```

```python
# app/worker/tasks.py
from app.services.agent_service import agent_service
from app.worker.celery_app import celery_app
from app.worker.progress import ProgressReporter


@celery_app.task(bind=True, max_retries=3)
def run_agent_task(self, session_id: str, topic: str | None, user_input: str, user_id: int | None):
    reporter = ProgressReporter(self.request.id)
    reporter.publish("progress", {"stage": "started"})
    result = agent_service.run(session_id=session_id, topic=topic, user_input=user_input, user_id=user_id)
    reporter.publish("done", {"stage": result.get("stage", "unknown"), "reply": result.get("reply", "")})
    return result
```

```python
# app/services/task_dispatcher.py
import uuid
from celery.result import AsyncResult

from app.worker.tasks import run_agent_task


class TaskDispatcher:
    @staticmethod
    def dispatch(*, session_id: str, topic: str | None, user_input: str, user_id: int | None) -> str:
        task_id = str(uuid.uuid4())
        run_agent_task.apply_async(
            kwargs={"session_id": session_id, "topic": topic, "user_input": user_input, "user_id": user_id},
            task_id=task_id,
        )
        return task_id

    @staticmethod
    def get_status(task_id: str) -> dict:
        result = AsyncResult(task_id)
        return {
            "task_id": task_id,
            "status": result.state,
            "result": result.result if result.ready() and not result.failed() else None,
            "error": str(result.result) if result.failed() else None,
        }


task_dispatcher = TaskDispatcher()
```

- [ ] **Step 4: 运行测试并确认通过**

Run: `uv run pytest tests/test_task_dispatcher.py -v`  
Expected: PASS.

- [ ] **Step 5: 提交**

```bash
git add app/worker/__init__.py app/worker/celery_app.py app/worker/progress.py app/worker/tasks.py app/services/task_dispatcher.py tests/test_task_dispatcher.py
git commit -m "feat: add celery worker and task dispatcher"
```

### Task 3: Redis Pub/Sub SSE 监听器

**Files:**
- Create: `app/services/redis_pubsub.py`
- Test: `tests/test_redis_pubsub.py`

- [ ] **Step 1: 写失败测试（监听器返回 message 并在 done 停止）**

```python
# tests/test_redis_pubsub.py
import asyncio

from app.services.redis_pubsub import RedisPubSubListener


def test_listener_yields_events_and_stops(monkeypatch):
    class FakePubSub:
        async def subscribe(self, channel):  # noqa: ARG002
            return None

        async def unsubscribe(self, channel):  # noqa: ARG002
            return None

        async def listen(self):
            yield {"type": "message", "data": b'{"event":"progress","stage":"running"}'}
            yield {"type": "message", "data": b'{"event":"done","stage":"completed"}'}

    class FakeClient:
        def pubsub(self):
            return FakePubSub()

        async def close(self):
            return None

    monkeypatch.setattr("app.services.redis_pubsub.redis.from_url", lambda url: FakeClient())  # noqa: ARG005
    listener = RedisPubSubListener()

    async def run():
        events = []
        async for item in listener.listen("task-1"):
            events.append(item["event"])
        return events

    assert asyncio.run(run()) == ["progress", "done"]
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `uv run pytest tests/test_redis_pubsub.py::test_listener_yields_events_and_stops -v`  
Expected: FAIL（监听器未实现）。

- [ ] **Step 3: 实现监听器**

```python
# app/services/redis_pubsub.py
import json
from typing import AsyncGenerator

import redis.asyncio as redis

from app.core.config import settings


class RedisPubSubListener:
    async def listen(self, task_id: str) -> AsyncGenerator[dict, None]:
        client = redis.from_url(settings.redis_url)
        pubsub = client.pubsub()
        channel = f"task:{task_id}"
        try:
            await pubsub.subscribe(channel)
            async for message in pubsub.listen():
                if message.get("type") != "message":
                    continue
                raw = message.get("data")
                data = json.loads(raw.decode("utf-8") if isinstance(raw, bytes) else raw)
                yield data
                if data.get("event") == "done":
                    break
        finally:
            await pubsub.unsubscribe(channel)
            await client.close()
```

- [ ] **Step 4: 运行测试并确认通过**

Run: `uv run pytest tests/test_redis_pubsub.py -v`  
Expected: PASS.

- [ ] **Step 5: 提交**

```bash
git add app/services/redis_pubsub.py tests/test_redis_pubsub.py
git commit -m "feat: add redis pubsub listener for task stream"
```

### Task 4: API 路由改造（`/chat` 异步提交 + `/chat/sync` + `/chat/status` + `/chat/stream/{task_id}`）

**Files:**
- Modify: `app/api/chat.py`
- Modify: `tests/test_chat_async_api.py`
- Modify: `tests/test_chat_stream_api.py`

- [ ] **Step 1: 写失败测试（`/chat/sync` 保留旧行为）**

```python
def test_chat_sync_keeps_previous_behavior(monkeypatch):
    monkeypatch.setattr("app.api.chat.settings.async_chat_enabled", True)
    monkeypatch.setattr(
        "app.api.chat.agent_service.run",
        lambda **kwargs: {"session_id": "s-1", "stage": "explained", "reply": "ok", "summary": None, "citations": []},
    )
    resp = client.post("/chat/sync", json={"session_id": "s-1", "user_input": "解释"})
    assert resp.status_code == 200
    assert resp.json()["reply"] == "ok"
```

- [ ] **Step 2: 写失败测试（`/chat/status/{task_id}` 返回状态）**

```python
def test_chat_status_endpoint(monkeypatch):
    monkeypatch.setattr(
        "app.api.chat.task_dispatcher.get_status",
        lambda task_id: {"task_id": task_id, "status": "SUCCESS", "result": {"reply": "done"}, "error": None},
    )
    resp = client.get("/chat/status/task-1")
    assert resp.status_code == 200
    assert resp.json()["status"] == "SUCCESS"
```

- [ ] **Step 3: 改造 chat API**

```python
# app/api/chat.py (关键路由形态)
@router.post("", response_model=AsyncChatSubmitResponse | ChatResponse)
def chat(request: ChatRequest):
    if settings.async_chat_enabled:
        task_id = task_dispatcher.dispatch(
            session_id=request.session_id,
            topic=request.topic,
            user_input=request.user_input,
            user_id=request.user_id,
        )
        return AsyncChatSubmitResponse(task_id=task_id, status="pending")
    return _run_sync_chat(request)


@router.post("/sync", response_model=ChatResponse)
def chat_sync(request: ChatRequest) -> ChatResponse:
    return _run_sync_chat(request)


@router.get("/status/{task_id}", response_model=TaskStatusResponse)
def chat_status(task_id: str) -> TaskStatusResponse:
    return TaskStatusResponse(**task_dispatcher.get_status(task_id))


@router.get("/stream/{task_id}")
async def chat_stream_async(task_id: str) -> StreamingResponse:
    listener = RedisPubSubListener()

    async def event_generator():
        async for item in listener.listen(task_id):
            event = item.get("event", "progress")
            yield f"event: {event}\ndata: {item}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
```

- [ ] **Step 4: 运行测试并确认通过**

Run:
```bash
uv run pytest tests/test_chat_async_api.py tests/test_chat_stream_api.py -v
```

Expected: PASS.

- [ ] **Step 5: 提交**

```bash
git add app/api/chat.py tests/test_chat_async_api.py tests/test_chat_stream_api.py
git commit -m "feat: add async chat submit/status/stream endpoints with sync fallback"
```

### Task 5: Worker 进度上报接入 AgentService（最小侵入）

**Files:**
- Modify: `app/services/agent_service.py`
- Modify: `app/worker/tasks.py`
- Modify: `tests/test_chat_async_api.py`

- [ ] **Step 1: 写失败测试（任务执行时至少推送 started + done）**

```python
def test_run_agent_task_publishes_started_and_done(monkeypatch):
    events = []

    class FakeReporter:
        def __init__(self, task_id):  # noqa: ARG002
            pass

        def publish(self, event, payload):
            events.append((event, payload.get("stage")))

    monkeypatch.setattr("app.worker.tasks.ProgressReporter", FakeReporter)
    monkeypatch.setattr(
        "app.worker.tasks.agent_service.run",
        lambda **kwargs: {"stage": "summarized", "reply": "done", "session_id": "s-1"},
    )

    class Req:
        id = "task-1"

    class SelfObj:
        request = Req()

    result = run_agent_task(SelfObj(), "s-1", "图论", "解释", 1)
    assert result["reply"] == "done"
    assert events[0][0] == "progress"
    assert events[-1][0] == "done"
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `uv run pytest tests/test_chat_async_api.py::test_run_agent_task_publishes_started_and_done -v`  
Expected: FAIL（任务上报细节未接齐）。

- [ ] **Step 3: 最小化改造 AgentService（可选回调参数）**

```python
# app/services/agent_service.py (run 签名补充)
def run(
    self,
    session_id: str,
    topic: str | None,
    user_input: str,
    user_id: int | None = None,
    stream_output: bool = False,
    on_progress: callable | None = None,
) -> LearningState:
    if on_progress is not None:
        on_progress("started", 0, None)
    result = self._run_core_logic(
        session_id=session_id,
        topic=topic,
        user_input=user_input,
        user_id=user_id,
        stream_output=stream_output,
    )
    if on_progress is not None:
        on_progress("completed", 100, result.get("reply", ""))
    return result
```

```python
# app/worker/tasks.py (调用 on_progress)
def _on_progress(stage: str, progress: int, token: str | None) -> None:
    payload = {"stage": stage, "progress": progress}
    if token:
        payload["token"] = token
        reporter.publish("token", payload)
    else:
        reporter.publish("progress", payload)

result = agent_service.run(
    session_id=session_id,
    topic=topic,
    user_input=user_input,
    user_id=user_id,
    on_progress=_on_progress,
)
```

- [ ] **Step 4: 运行测试并确认通过**

Run: `uv run pytest tests/test_chat_async_api.py::test_run_agent_task_publishes_started_and_done -v`  
Expected: PASS.

- [ ] **Step 5: 提交**

```bash
git add app/services/agent_service.py app/worker/tasks.py tests/test_chat_async_api.py
git commit -m "feat: add progress callback bridge from agent service to celery worker"
```

### Task 6: 运行与部署对齐（docker-compose + 全量回归）

**Files:**
- Modify: `docker-compose.yml`
- Modify: `README.md`（仅更新与异步队列相关的启动说明段落）

- [ ] **Step 1: 更新 compose 增加 redis 与 worker**

```yaml
services:
  redis:
    image: redis:alpine
    ports:
      - "6379:6379"

  worker:
    build:
      context: .
      dockerfile: Dockerfile.dev
    env_file:
      - .env
    volumes:
      - .:/workspace
      - ./data:/workspace/data
    command: celery -A app.worker.celery_app worker --concurrency=4 --loglevel=info
    depends_on:
      - redis
```

- [ ] **Step 2: 运行目标测试集**

Run:
```bash
uv run pytest tests/test_chat_async_api.py tests/test_task_dispatcher.py tests/test_redis_pubsub.py tests/test_chat_stream_api.py -v
```

Expected: PASS.

- [ ] **Step 3: 运行全量测试**

Run:
```bash
uv run pytest -q
```

Expected: PASS.

- [ ] **Step 4: 更新 README（仅新增异步模式启动与降级说明）**

```markdown
- `ASYNC_CHAT_ENABLED=true` 时，`POST /chat` 返回 `task_id`，通过 `/chat/stream/{task_id}` 和 `/chat/status/{task_id}` 获取执行进度与结果。
- Redis/Worker 不可用时可设置 `ASYNC_CHAT_ENABLED=false` 回退同步模式（`/chat/sync` 保持可用）。
```

- [ ] **Step 5: 提交**

```bash
git add docker-compose.yml README.md
git commit -m "docs(chore): wire redis worker runtime and async chat runbook"
```

## Self-Review Results

1. **Spec coverage:**  
   - 异步任务提交、SSE 流式回传、状态查询、降级策略、配置开关、启动方式均有对应任务。

2. **Placeholder scan:**  
   - 本计划未包含未定义占位步骤，所有代码步骤均给出可执行示例。

3. **Type consistency:**  
   - `AsyncChatSubmitResponse`、`TaskStatusResponse`、`task_id/status/result/error` 字段命名在 API、dispatcher、测试中保持一致。
