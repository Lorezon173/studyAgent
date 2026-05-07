# Phase 3a 异步骨架（Celery + Redis + Dispatcher + PubSub）实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不影响现有同步行为的前提下，引入 Celery 应用、Redis pub/sub 封装与 task dispatcher，建立 Phase 3 后续子阶段（3b/3c/3d）的异步运行时基础。

**Architecture:** 新增 `app/worker/` 包（celery 实例 + 占位任务）与 `app/services/{redis_pubsub,task_dispatcher}.py`；用 `ASYNC_GRAPH_ENABLED` feature flag 控制 dispatcher 路由，flag off 时所有调用方走原同步路径，行为零变化。Celery 与 Redis 通过 `REDIS_URL` 共用 broker / backend。所有新模块单元测试用 `fakeredis` 与 Celery `task_always_eager` 模式，无需真实 Redis 进程。

**Tech Stack:** Python 3.12, Celery 5.x, redis-py, fakeredis（dev），pytest，pydantic-settings。

**Spec 来源:** [docs/superpowers/specs/top-007-2026-05-01-phase3-finalization-design.md](../specs/top-007-2026-05-01-phase3-finalization-design.md) §11.1（子阶段 3a）。

---

## File Structure

| 文件 | 类型 | 责任 | 边界 |
|---|---|---|---|
| `pyproject.toml` | 修改 | 加 celery / redis 运行时依赖 + fakeredis dev 依赖 | 仅依赖声明 |
| `app/core/config.py` | 修改 | 新增 3 个 Settings 字段 | 仅配置定义 |
| `app/services/redis_pubsub.py` | 新增 | `RedisPubSub` 类：publish/subscribe + 超时 + 工厂函数 | 不感知业务、不依赖 celery |
| `app/worker/__init__.py` | 新增 | worker 包入口（空文件） | — |
| `app/worker/celery_app.py` | 新增 | Celery 实例 + broker/backend 配置 + include 任务模块 | 不写业务逻辑 |
| `app/worker/tasks.py` | 新增 | `run_chat_graph` 占位任务（3a 不接 graph_v2，3b 再接） | 仅 echo + pubsub publish |
| `app/services/task_dispatcher.py` | 新增 | `dispatch(payload) -> DispatchResult` 按 flag 分流 | 不感知 SSE 与 chat |
| `tests/test_config_async_settings.py` | 新增 | 验证 3 个新配置字段默认值与覆盖 | — |
| `tests/test_redis_pubsub.py` | 新增 | RedisPubSub 单元测试（fakeredis） | — |
| `tests/test_worker_celery_app.py` | 新增 | Celery 实例与任务注册可见 | — |
| `tests/test_worker_tasks.py` | 新增 | 占位任务 eager 执行 + pubsub 发出 | — |
| `tests/test_task_dispatcher.py` | 新增 | flag on/off 分流分支 | — |

**边界原则**：

1. `redis_pubsub` 不依赖 celery；celery_app 不依赖 redis_pubsub；dispatcher 同时依赖二者但仅做路由。
2. 3a 不修改 `app/api/chat.py` 与 `app/services/agent_service.py`（那是 3b 的工作）。
3. 占位 task 仅返回 echo + 发出 `accepted`/`done` 两个 pubsub 事件，便于 3b 替换。

---

## Task 1：添加运行时 / 测试依赖

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1：修改 `pyproject.toml`**

将 `dependencies` 列表追加 2 项，将 `dev` 列表追加 1 项：

```toml
[project]
# ... existing fields ...
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
    "celery>=5.4.0",
    "redis>=5.0.0",
]

[dependency-groups]
dev = [
    "pytest>=9.0.2",
    "ruff>=0.15.7",
    "fakeredis>=2.23.0",
]
```

- [ ] **Step 2：同步依赖**

Run: `uv sync`
Expected: `Resolved` 输出含 `+ celery`、`+ redis`、`+ fakeredis`，无错误。

- [ ] **Step 3：验证导入**

Run: `uv run python -c "import celery, redis, fakeredis; print(celery.__version__, redis.__version__, fakeredis.__version__)"`
Expected: 三个版本号成功打印，无 `ImportError`。

- [ ] **Step 4：Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "chore(deps): add celery / redis / fakeredis for phase3a async skeleton"
```

---

## Task 2：新增 3 个 Settings 字段（TDD）

**Files:**
- Modify: `app/core/config.py`
- Test: `tests/test_config_async_settings.py`

- [ ] **Step 1：写失败测试**

Create `tests/test_config_async_settings.py`:

```python
"""Phase 3a：验证异步骨架新增的 Settings 字段默认值与可覆盖性。"""
import pytest
from app.core.config import Settings


def test_async_graph_enabled_default_false():
    s = Settings()
    assert s.async_graph_enabled is False


def test_redis_url_default_localhost():
    s = Settings()
    assert s.redis_url == "redis://localhost:6379/0"


def test_celery_task_timeout_default_60_seconds():
    s = Settings()
    assert s.celery_task_timeout_s == 60


def test_async_graph_enabled_can_be_overridden_via_env(monkeypatch):
    monkeypatch.setenv("ASYNC_GRAPH_ENABLED", "true")
    s = Settings()
    assert s.async_graph_enabled is True


def test_redis_url_can_be_overridden_via_env(monkeypatch):
    monkeypatch.setenv("REDIS_URL", "redis://other-host:6380/1")
    s = Settings()
    assert s.redis_url == "redis://other-host:6380/1"


def test_celery_task_timeout_can_be_overridden_via_env(monkeypatch):
    monkeypatch.setenv("CELERY_TASK_TIMEOUT_S", "120")
    s = Settings()
    assert s.celery_task_timeout_s == 120
```

- [ ] **Step 2：运行测试，验证失败**

Run: `uv run pytest tests/test_config_async_settings.py -v`
Expected: 6 个测试 FAIL，错误信息含 `AttributeError: 'Settings' object has no attribute 'async_graph_enabled'` 或类似。

- [ ] **Step 3：实现 Settings 字段**

Modify `app/core/config.py`，在 `langfuse_enabled: bool = False` 之后、`model_config` 之前插入：

```python
    # Phase 3a 异步骨架开关
    async_graph_enabled: bool = False
    redis_url: str = "redis://localhost:6379/0"
    celery_task_timeout_s: int = 60
```

- [ ] **Step 4：运行测试，验证通过**

Run: `uv run pytest tests/test_config_async_settings.py -v`
Expected: 6 PASS / 0 FAIL.

- [ ] **Step 5：Commit**

```bash
git add app/core/config.py tests/test_config_async_settings.py
git commit -m "feat(config): add async_graph_enabled / redis_url / celery_task_timeout_s settings (phase 3a)"
```

---

## Task 3：实现 RedisPubSub 封装（TDD）

**Files:**
- Create: `app/services/redis_pubsub.py`
- Test: `tests/test_redis_pubsub.py`

设计契约：

- `RedisPubSub(client)` — 构造时注入 `redis.Redis | fakeredis.FakeRedis` 实例。
- `publish(channel, event, data)` — 发布单条消息，channel 字符串、event 短标签（如 `accepted`、`token`、`done`）、data 任意字符串负载。底层用 JSON 编码 `{"event": ..., "data": ...}`。
- `subscribe(channel, timeout_s)` — 生成器，逐条 yield `(event, data)`；遇到 `event=done` 或 `event=error` 自然结束；超时则 raise `TimeoutError`。
- `get_default_pubsub()` — 工厂：从 `settings.redis_url` 构造默认实例。

- [ ] **Step 1：写失败测试**

Create `tests/test_redis_pubsub.py`:

```python
"""Phase 3a：RedisPubSub 单元测试，使用 fakeredis 避免真实 Redis 依赖。"""
import threading
import time
import pytest
import fakeredis

from app.services.redis_pubsub import RedisPubSub


@pytest.fixture
def pubsub():
    client = fakeredis.FakeRedis(decode_responses=False)
    return RedisPubSub(client)


def test_publish_then_subscribe_roundtrip(pubsub):
    """订阅者先订阅，发布者后发布，订阅方应收到消息序列直至 done。"""
    received: list[tuple[str, str]] = []

    def consumer():
        for event, data in pubsub.subscribe("ch:test1", timeout_s=2.0):
            received.append((event, data))

    t = threading.Thread(target=consumer, daemon=True)
    t.start()

    # 给订阅一个就绪窗口
    time.sleep(0.1)
    pubsub.publish("ch:test1", "accepted", "task-123")
    pubsub.publish("ch:test1", "token", "hello")
    pubsub.publish("ch:test1", "done", "[DONE]")

    t.join(timeout=3.0)
    assert received == [
        ("accepted", "task-123"),
        ("token", "hello"),
        ("done", "[DONE]"),
    ]


def test_subscribe_terminates_on_error_event(pubsub):
    received: list[tuple[str, str]] = []

    def consumer():
        for event, data in pubsub.subscribe("ch:test2", timeout_s=2.0):
            received.append((event, data))

    t = threading.Thread(target=consumer, daemon=True)
    t.start()
    time.sleep(0.1)
    pubsub.publish("ch:test2", "error", "boom")

    t.join(timeout=3.0)
    assert received == [("error", "boom")]


def test_subscribe_raises_timeout_when_no_message(pubsub):
    with pytest.raises(TimeoutError):
        # 没有发布者，应在 0.5s 后超时
        for _ in pubsub.subscribe("ch:silent", timeout_s=0.5):
            pytest.fail("should not yield any message")


def test_channels_are_isolated(pubsub):
    received_a: list[tuple[str, str]] = []
    received_b: list[tuple[str, str]] = []

    def consumer(channel, sink):
        for event, data in pubsub.subscribe(channel, timeout_s=2.0):
            sink.append((event, data))

    ta = threading.Thread(target=consumer, args=("ch:A", received_a), daemon=True)
    tb = threading.Thread(target=consumer, args=("ch:B", received_b), daemon=True)
    ta.start()
    tb.start()
    time.sleep(0.1)
    pubsub.publish("ch:A", "token", "alpha")
    pubsub.publish("ch:A", "done", "[DONE]")
    pubsub.publish("ch:B", "token", "beta")
    pubsub.publish("ch:B", "done", "[DONE]")

    ta.join(timeout=3.0)
    tb.join(timeout=3.0)
    assert received_a == [("token", "alpha"), ("done", "[DONE]")]
    assert received_b == [("token", "beta"), ("done", "[DONE]")]
```

- [ ] **Step 2：运行测试，验证失败**

Run: `uv run pytest tests/test_redis_pubsub.py -v`
Expected: 4 个测试全部 FAIL，错误为 `ModuleNotFoundError: No module named 'app.services.redis_pubsub'`。

- [ ] **Step 3：实现 RedisPubSub**

Create `app/services/redis_pubsub.py`:

```python
"""Redis Pub/Sub 极简封装，供 Phase 3 异步链路在 web 与 worker 进程间桥接事件。"""
from __future__ import annotations

import json
import time
from typing import Iterator, Protocol

import redis

from app.core.config import settings

_TERMINAL_EVENTS = ("done", "error")


class _RedisLike(Protocol):
    def publish(self, channel: str, message: bytes | str) -> int: ...
    def pubsub(self): ...


class RedisPubSub:
    """对 redis-py 的薄封装，统一 `(event, data)` 字符串协议与终止语义。"""

    def __init__(self, client: _RedisLike) -> None:
        self._client = client

    def publish(self, channel: str, event: str, data: str) -> None:
        payload = json.dumps({"event": event, "data": data}, ensure_ascii=False)
        self._client.publish(channel, payload)

    def subscribe(self, channel: str, timeout_s: float = 30.0) -> Iterator[tuple[str, str]]:
        ps = self._client.pubsub(ignore_subscribe_messages=True)
        ps.subscribe(channel)
        deadline = time.monotonic() + timeout_s
        try:
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError(f"pubsub timeout on channel={channel}")
                msg = ps.get_message(timeout=min(remaining, 0.1))
                if msg is None:
                    continue
                if msg.get("type") != "message":
                    continue
                raw = msg.get("data")
                if isinstance(raw, bytes):
                    raw = raw.decode("utf-8")
                payload = json.loads(raw)
                event = str(payload.get("event", ""))
                data = str(payload.get("data", ""))
                yield event, data
                if event in _TERMINAL_EVENTS:
                    return
        finally:
            try:
                ps.unsubscribe(channel)
                ps.close()
            except Exception:
                pass


def get_default_pubsub() -> RedisPubSub:
    """从全局 settings 构造默认实例。生产路径使用。"""
    client = redis.from_url(settings.redis_url)
    return RedisPubSub(client)
```

- [ ] **Step 4：运行测试，验证通过**

Run: `uv run pytest tests/test_redis_pubsub.py -v`
Expected: 4 PASS / 0 FAIL.

- [ ] **Step 5：Commit**

```bash
git add app/services/redis_pubsub.py tests/test_redis_pubsub.py
git commit -m "feat(services): add RedisPubSub publish/subscribe wrapper (phase 3a)"
```

---

## Task 4：创建 `app/worker/` 包与 Celery 应用（TDD）

**Files:**
- Create: `app/worker/__init__.py`
- Create: `app/worker/celery_app.py`
- Test: `tests/test_worker_celery_app.py`

设计契约：

- `celery_app` 名为 `study_agent`。
- broker / backend 都使用 `settings.redis_url`。
- `include=["app.worker.tasks"]` 让 worker 启动时自动注册任务。
- 单测用 `task_always_eager=True`（直接同步执行）+ `task_eager_propagates=True`，避免拉起 Redis。

- [ ] **Step 1：创建空包初始化文件**

Create `app/worker/__init__.py`（内容为空文件，建立 Python 包标识）：

```python
```

- [ ] **Step 2：写失败测试**

Create `tests/test_worker_celery_app.py`:

```python
"""Phase 3a：验证 Celery 应用实例与配置。"""
from celery import Celery

from app.worker.celery_app import celery_app
from app.core.config import settings


def test_celery_app_is_celery_instance():
    assert isinstance(celery_app, Celery)


def test_celery_app_main_name():
    assert celery_app.main == "study_agent"


def test_broker_url_matches_settings():
    assert celery_app.conf.broker_url == settings.redis_url


def test_result_backend_matches_settings():
    assert celery_app.conf.result_backend == settings.redis_url


def test_task_module_included():
    """worker 启动时会 import app.worker.tasks，验证 include 配置正确。"""
    includes = celery_app.conf.include or []
    assert "app.worker.tasks" in includes
```

- [ ] **Step 3：运行测试，验证失败**

Run: `uv run pytest tests/test_worker_celery_app.py -v`
Expected: 5 FAIL，`ModuleNotFoundError: No module named 'app.worker.celery_app'`.

- [ ] **Step 4：实现 celery_app**

Create `app/worker/celery_app.py`:

```python
"""Celery 应用实例。worker 进程入口；3a 阶段仅完成实例化与任务发现。"""
from __future__ import annotations

from celery import Celery

from app.core.config import settings


celery_app = Celery(
    "study_agent",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.worker.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_time_limit=settings.celery_task_timeout_s,
    task_soft_time_limit=max(settings.celery_task_timeout_s - 5, 1),
)
```

- [ ] **Step 5：运行测试，验证通过**

Run: `uv run pytest tests/test_worker_celery_app.py -v`
Expected: 5 PASS / 0 FAIL（注意：测试会尝试 import `app.worker.tasks`，但 `include` 是惰性的；如有 import 错误，确认 Task 5 已经把 tasks.py 创建好。如果还没到 Task 5，可暂时把 `include=["app.worker.tasks"]` 注释，单跑这一步，然后 Task 5 再恢复——**不推荐**。推荐顺序就是按本计划走 Task 5）。

- [ ] **Step 6：Commit**

```bash
git add app/worker/__init__.py app/worker/celery_app.py tests/test_worker_celery_app.py
git commit -m "feat(worker): add celery_app instance for phase 3a async skeleton"
```

---

## Task 5：实现占位任务 `run_chat_graph`（TDD）

**Files:**
- Create: `app/worker/tasks.py`
- Test: `tests/test_worker_tasks.py`

设计契约：

- 任务名 `app.worker.tasks.run_chat_graph`（默认基于函数路径）。
- 入参：`payload: dict`（3b 阶段会演化为 `ChatTaskPayload` 类型）。
- 行为：通过 pubsub 在 `chat:{task_id}` 频道发出 `accepted`，echo 出固定结构化结果，发出 `done`。
- 返回值：`{"status": "ok", "echo": payload}`，便于 3b 替换为真正 graph 调用结果。

- [ ] **Step 1：写失败测试**

Create `tests/test_worker_tasks.py`:

```python
"""Phase 3a：占位任务 run_chat_graph 在 eager 模式下的行为。"""
import threading
import time
import pytest
import fakeredis

from app.worker.celery_app import celery_app
from app.worker import tasks as worker_tasks
from app.services.redis_pubsub import RedisPubSub


@pytest.fixture(autouse=True)
def eager_mode():
    """让 .delay() 同步执行，避免拉起 worker 进程。"""
    prev = (celery_app.conf.task_always_eager, celery_app.conf.task_eager_propagates)
    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = True
    yield
    celery_app.conf.task_always_eager = prev[0]
    celery_app.conf.task_eager_propagates = prev[1]


@pytest.fixture
def fake_pubsub(monkeypatch):
    """注入 fakeredis 替代 get_default_pubsub。"""
    client = fakeredis.FakeRedis(decode_responses=False)
    instance = RedisPubSub(client)
    monkeypatch.setattr(
        worker_tasks,
        "get_default_pubsub",
        lambda: instance,
    )
    return instance


def test_run_chat_graph_returns_echo_structure(fake_pubsub):
    payload = {"session_id": "s1", "user_input": "hi"}
    result = worker_tasks.run_chat_graph.delay(payload).get(timeout=5)
    assert result == {"status": "ok", "echo": payload}


def test_run_chat_graph_emits_accepted_and_done(fake_pubsub):
    payload = {"session_id": "s2", "user_input": "x"}
    received: list[tuple[str, str]] = []

    def consumer():
        for event, data in fake_pubsub.subscribe("chat:s2", timeout_s=2.0):
            received.append((event, data))

    t = threading.Thread(target=consumer, daemon=True)
    t.start()
    time.sleep(0.1)
    worker_tasks.run_chat_graph.delay(payload).get(timeout=5)
    t.join(timeout=3.0)
    events = [e for e, _ in received]
    assert events == ["accepted", "done"]


def test_task_is_registered_with_expected_name():
    assert "app.worker.tasks.run_chat_graph" in celery_app.tasks
```

- [ ] **Step 2：运行测试，验证失败**

Run: `uv run pytest tests/test_worker_tasks.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'app.worker.tasks'` 或 `AttributeError`.

- [ ] **Step 3：实现占位任务**

Create `app/worker/tasks.py`:

```python
"""Celery 任务集合。

3a 阶段：仅占位 run_chat_graph，验证 web→broker→worker→pubsub 通路。
3b 阶段：将占位替换为对 agent_service.run 的真实调用 + 进度回调。
"""
from __future__ import annotations

from typing import Any

from app.services.redis_pubsub import get_default_pubsub
from app.worker.celery_app import celery_app


@celery_app.task(name="app.worker.tasks.run_chat_graph")
def run_chat_graph(payload: dict[str, Any]) -> dict[str, Any]:
    """Phase 3a 占位实现。

    通过 pubsub 在 chat:{session_id} 频道发出 accepted / done，回 echo 给调用方。
    后续 3b 阶段会引入 progress / token / stage 事件。
    """
    channel = f"chat:{payload.get('session_id', 'unknown')}"
    pubsub = get_default_pubsub()
    pubsub.publish(channel, "accepted", payload.get("session_id", ""))
    result = {"status": "ok", "echo": payload}
    pubsub.publish(channel, "done", "[DONE]")
    return result
```

- [ ] **Step 4：运行测试，验证通过**

Run: `uv run pytest tests/test_worker_tasks.py -v`
Expected: 3 PASS / 0 FAIL.

- [ ] **Step 5：Commit**

```bash
git add app/worker/tasks.py tests/test_worker_tasks.py
git commit -m "feat(worker): add run_chat_graph placeholder task with pubsub events (phase 3a)"
```

---

## Task 6：实现 `task_dispatcher`（TDD）

**Files:**
- Create: `app/services/task_dispatcher.py`
- Test: `tests/test_task_dispatcher.py`

设计契约：

- `DispatchResult(mode, task_id)` 数据类；`mode` 取值 `"sync"` 或 `"async"`。
- `dispatch(payload)`：
    - `settings.async_graph_enabled=False` → 返回 `DispatchResult(mode="sync", task_id=None)`，不入队（实际同步路径在 3b 由 chat.py 自行处理）。
    - `settings.async_graph_enabled=True` → 调用 `run_chat_graph.delay(payload)` 并返回 `DispatchResult(mode="async", task_id=<celery id>)`。
- 不感知 SSE / chat 协议；纯路由组件。

- [ ] **Step 1：写失败测试**

Create `tests/test_task_dispatcher.py`:

```python
"""Phase 3a：task_dispatcher 按 ASYNC_GRAPH_ENABLED flag 分流。"""
import pytest

from app.core.config import settings
from app.worker.celery_app import celery_app
from app.services.task_dispatcher import dispatch, DispatchResult


@pytest.fixture(autouse=True)
def eager_mode():
    prev = (celery_app.conf.task_always_eager, celery_app.conf.task_eager_propagates)
    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = True
    yield
    celery_app.conf.task_always_eager = prev[0]
    celery_app.conf.task_eager_propagates = prev[1]


@pytest.fixture
def fake_pubsub(monkeypatch):
    """避免占位任务真正去连 Redis。"""
    import fakeredis
    from app.services.redis_pubsub import RedisPubSub
    from app.worker import tasks as worker_tasks

    client = fakeredis.FakeRedis(decode_responses=False)
    monkeypatch.setattr(
        worker_tasks, "get_default_pubsub",
        lambda: RedisPubSub(client),
    )


def test_dispatch_returns_sync_result_when_flag_off(monkeypatch, fake_pubsub):
    monkeypatch.setattr(settings, "async_graph_enabled", False)
    result = dispatch({"session_id": "s1", "user_input": "x"})
    assert isinstance(result, DispatchResult)
    assert result.mode == "sync"
    assert result.task_id is None


def test_dispatch_returns_async_result_when_flag_on(monkeypatch, fake_pubsub):
    monkeypatch.setattr(settings, "async_graph_enabled", True)
    result = dispatch({"session_id": "s2", "user_input": "y"})
    assert result.mode == "async"
    assert result.task_id is not None
    assert isinstance(result.task_id, str)
    assert len(result.task_id) > 0


def test_dispatch_passes_payload_to_task(monkeypatch, fake_pubsub):
    """flag on 时 payload 必须原样传递，由 worker 任务消费。"""
    monkeypatch.setattr(settings, "async_graph_enabled", True)
    captured: list[dict] = []

    from app.worker import tasks as worker_tasks
    real_task = worker_tasks.run_chat_graph

    def spy_delay(payload):
        captured.append(payload)
        return real_task.apply(args=(payload,))

    monkeypatch.setattr(real_task, "delay", spy_delay)

    payload = {"session_id": "s3", "user_input": "z"}
    dispatch(payload)
    assert captured == [payload]
```

- [ ] **Step 2：运行测试，验证失败**

Run: `uv run pytest tests/test_task_dispatcher.py -v`
Expected: 3 FAIL，`ModuleNotFoundError: No module named 'app.services.task_dispatcher'`.

- [ ] **Step 3：实现 dispatcher**

Create `app/services/task_dispatcher.py`:

```python
"""Task dispatcher：根据 ASYNC_GRAPH_ENABLED flag 决定走同步还是异步路径。

调用方（如 app/api/chat.py）只关心 DispatchResult.mode，不感知 celery。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from app.core.config import settings


@dataclass(frozen=True)
class DispatchResult:
    mode: Literal["sync", "async"]
    task_id: str | None


def dispatch(payload: dict[str, Any]) -> DispatchResult:
    if not settings.async_graph_enabled:
        return DispatchResult(mode="sync", task_id=None)

    from app.worker.tasks import run_chat_graph
    async_result = run_chat_graph.delay(payload)
    return DispatchResult(mode="async", task_id=async_result.id)
```

- [ ] **Step 4：运行测试，验证通过**

Run: `uv run pytest tests/test_task_dispatcher.py -v`
Expected: 3 PASS / 0 FAIL.

- [ ] **Step 5：Commit**

```bash
git add app/services/task_dispatcher.py tests/test_task_dispatcher.py
git commit -m "feat(services): add task_dispatcher with flag-based routing (phase 3a)"
```

---

## Task 7：全量回归 + 基线对账

**Files:**
- 无新增/修改

- [ ] **Step 1：跑 Phase 3a 新测试集**

Run: `uv run pytest tests/test_config_async_settings.py tests/test_redis_pubsub.py tests/test_worker_celery_app.py tests/test_worker_tasks.py tests/test_task_dispatcher.py -v`
Expected: 全部 PASS（共约 21 个测试）。

- [ ] **Step 2：跑全量回归**

Run（PowerShell 上 Windows 用户参考）:

```bash
PYTHONPATH=. DEBUG=false uv run pytest tests/ -q
```

Expected: 至少 `316 passed / 19 failed`（295 PASS 基线 + 本计划新增约 21 个 = 316，失败数维持 19）。

如果失败数 > 19：

1. 先确认是否是新增模块的导入副作用（如 celery_app 加载顺序）。
2. 若是，回到对应 Task 修复；不要把失败基线扩大。

- [ ] **Step 3：记录基线**

Create or append `docs/superpowers/plans/phase3a-execution-log.md`（不在本计划范围内，留给执行阶段产出 — 此处仅作 placeholder 提醒，**本步不写文件，仅在 git log 中体现**）。

- [ ] **Step 4：最终 commit（可选，仅在前面有未 commit 的文件时）**

```bash
git status
# 若 working tree 干净，跳过；若仍有未提交内容，分文件提交并写明
```

---

## 验收清单（Phase 3a 整体）

| 项 | 阈值 / 验证方式 |
|---|---|
| 依赖 | celery / redis 在运行时依赖；fakeredis 在 dev 依赖；`uv sync` 通过 |
| 配置 | `Settings.async_graph_enabled / redis_url / celery_task_timeout_s` 默认值正确，可被 env 覆盖 |
| RedisPubSub | publish/subscribe 双向、超时、终止事件、频道隔离 4 类测试通过 |
| Celery 实例 | `celery_app.main == "study_agent"`，broker/backend 来自 settings，`app.worker.tasks` 在 include |
| 占位任务 | `run_chat_graph` 注册名正确，eager 模式下返回 echo + 发 accepted/done |
| Dispatcher | flag off → mode=sync；flag on → mode=async + task_id 非空；payload 透传 |
| 回归 | 全量测试集 ≥ 316 PASS / 19 FAIL（不退化） |
| 不变量 | `app/api/chat.py` 与 `app/services/agent_service.py` 在本计划中**未被修改**（这是 3b 的工作） |

---

## Self-Review 备注

1. Spec §11.1 列出 8 项交付，本 plan 覆盖：
    - `app/worker/celery_app.py` → Task 4 ✓
    - `app/worker/tasks.py` → Task 5 ✓
    - `app/services/redis_pubsub.py` → Task 3 ✓
    - `app/services/task_dispatcher.py` → Task 6 ✓
    - `app/config.py` 新增 3 个开关 → Task 2 ✓
    - `tests/test_worker_celery_app.py` → Task 4 ✓
    - `tests/test_redis_pubsub.py` → Task 3 ✓
    - `tests/test_task_dispatcher.py` → Task 6 ✓

   补充：`app/worker/__init__.py`（Task 4 步骤 1）+ `tests/test_worker_tasks.py`（Task 5）+ `tests/test_config_async_settings.py`（Task 2），覆盖更完整。

2. Spec §11.1 门禁条件"全量回归 ≥ 295 PASS（不退化），新增测试全绿" → Task 7 验证。

3. Spec §7.2 降级矩阵中 `ASYNC_GRAPH_ENABLED=true + Redis 不可达` 的"启动期 health check 失败 + fail loudly"在 3a 不实现（health check 是部署期能力，3b/3d 再决策）。这点仅记录在执行日志，非缺口。

4. 类型一致性：`DispatchResult.mode` 全程 `"sync" | "async"`；`RedisPubSub.subscribe` 终止事件全程 `("done", "error")`；任务名全程 `app.worker.tasks.run_chat_graph`。

5. 占位任务 echo 结构 `{"status": "ok", "echo": payload}` 在 3b 会被真实 graph 输出替换，echo 协议本身只是 3a 自检桩，不构成长期契约。
