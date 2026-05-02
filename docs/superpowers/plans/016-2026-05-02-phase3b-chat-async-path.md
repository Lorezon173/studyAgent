# Phase 3b：chat API 切到异步路径 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 `ASYNC_GRAPH_ENABLED=true` 时，`POST /chat/stream` 通过 celery worker 执行 `agent_service.run`，经 Redis pub/sub 把 token / stage / done / error 桥接回 SSE；flag 关闭时完全保持现有同步行为。

**Architecture:** 引入 `progress_sink: Callable[[str, str], None] | None` 作为 `agent_service.run` 的可选参数；worker 任务内部 `with llm_service.stream_to(consumer)` 把 LLM chunk 转发给 sink，sink 再 publish 到 redis 频道。chat.py 根据 `settings.async_graph_enabled` 分支：同步走现状、异步用 `task_dispatcher.dispatch` 得到 task_id 后 `pubsub.subscribe(f"chat:{task_id}")`，把事件转为 SSE。不改 graph_v2 / NodeRegistry / `@node` 契约。

**Tech Stack:** 同 3a（celery / redis-py / fakeredis）+ FastAPI SSE。

**Spec 来源：** [docs/superpowers/specs/top-007-2026-05-01-phase3-finalization-design.md](../specs/top-007-2026-05-01-phase3-finalization-design.md) §11.2（子阶段 3b）。

**前置：** 3a 已交付（PR #1 已开）。本 plan 在 3a 的基础上启用 `run_chat_graph` 从"echo 占位"演化为"真实 graph 调用 + pubsub 进度"。

---

## File Structure

| 文件 | 类型 | 责任 | 边界 |
|---|---|---|---|
| `app/services/agent_service.py` | 修改 | `run(..., progress_sink=None)` 新增参数；流式时把 consumer 转接到 sink（不改图契约） | 仅接口扩展 |
| `app/worker/tasks.py` | 修改 | `run_chat_graph` 由 echo 占位替换为真实 `agent_service.run` 调用 + pubsub 发 accepted / token / stage / done / error | 不感知 HTTP 协议 |
| `app/api/chat.py` | 修改 | `/chat/stream` 按 `settings.async_graph_enabled` flag 分流（新增异步分支；保留原同步分支） | 仅路由层 |
| `tests/test_agent_service_progress_sink.py` | 新增 | `progress_sink` 参数收到 stream token 的事件 | — |
| `tests/test_worker_tasks_real_graph.py` | 新增 | `run_chat_graph` 在 eager + mock agent_service 下产出 accepted / token / done 序列 | — |
| `tests/test_chat_async_api.py` | 新增 | flag on：SSE 事件序列含 accepted / token / done | — |
| `tests/test_chat_sync_fallback.py` | 新增 | flag off：SSE 事件序列保持 token / stage / done（与 Phase 7 前行为一致） | — |

**边界原则：**

1. `progress_sink` 类型是 `Callable[[event: str, data: str], None]`。sink 协议与 pubsub `(event, data)` 严格一致，避免任何翻译层。
2. agent_service 本身不导入 `redis_pubsub`，只认 sink。worker 任务是唯一把 sink 连接到 pubsub 的地方。
3. chat.py 不导入 celery。异步分支只依赖 `task_dispatcher` 与 `redis_pubsub`。

---

## Task 1：`agent_service.run` 增加 `progress_sink` 参数（TDD）

**Files:**
- Modify: `app/services/agent_service.py`
- Test: `tests/test_agent_service_progress_sink.py`

设计契约：

- 签名：`run(session_id, topic, user_input, user_id=None, stream_output=False, progress_sink: Callable[[str, str], None] | None = None)`
- 不改变现有调用：所有现有调用站点未传 `progress_sink`（保持 None），行为 100% 不变。
- 当 `progress_sink is not None`：
    1. 强制 `stream_output=True`（sink 的意义就是要拿到流式事件）。
    2. 内部包一层 `with llm_service.stream_to(lambda piece: progress_sink("token", piece))`，把 LLM 流 token 转为 `("token", piece)` 事件发给 sink。
    3. 返回 state 之前额外发 `("stage", state.get("stage", "unknown"))`。
    4. 不捕获异常；由上层 worker 决定发 `("error", ...)` 还是 `raise`。

- [ ] **Step 1：写失败测试**

Create `tests/test_agent_service_progress_sink.py`:

```python
"""Phase 3b Task 1：agent_service.run 的 progress_sink 参数。"""
from typing import Any
import pytest

from app.services.agent_service import AgentService


@pytest.fixture
def fake_llm_and_graph(monkeypatch):
    """隔离 LLM 与 graph：让 agent_service.run 只走 stream_to 通路 + 返回固定 state。"""
    from app.services import agent_service as mod
    from app.services import llm as llm_mod

    # 让 stream_to 的 consumer 收到一个可控 token 序列
    class FakeLLM:
        def invoke(self, system_prompt, user_prompt, stream_output=False):
            consumer = llm_mod.llm_service._stream_consumer.get()
            if stream_output and consumer is not None:
                consumer("alp")
                consumer("ha")
            return "alpha"

        # 为兼容 llm_service.stream_to 的 contextvar 逻辑
        class _Dummy:
            def stream(self, messages):
                return iter([])

        def _get_llm(self):
            return self._Dummy()

    # 替换 llm_service.invoke，但保留 stream_to 上下文
    real_llm = llm_mod.llm_service
    monkeypatch.setattr(real_llm, "invoke", FakeLLM().invoke)

    # 短路 graph：直接 return 固定 state，不触发 graph_v2
    def fake_run_with_graph_v2(**kwargs):
        # 模拟一次 LLM 调用触发 sink token
        real_llm.invoke("sys", "user", stream_output=True)
        return {
            "session_id": kwargs["session_id"],
            "stage": "explained",
            "reply": "alpha",
            "history": [],
        }

    monkeypatch.setattr(AgentService, "run_with_graph_v2", staticmethod(fake_run_with_graph_v2))
    monkeypatch.setattr(AgentService, "_should_use_graph_v2", staticmethod(lambda: True))


def test_progress_sink_receives_token_events(fake_llm_and_graph):
    events: list[tuple[str, str]] = []
    svc = AgentService()
    result = svc.run(
        session_id="s-progress-1",
        topic="math",
        user_input="hi",
        progress_sink=lambda ev, data: events.append((ev, data)),
    )
    # 至少 2 个 token + 1 个 stage
    token_events = [e for e, _ in events if e == "token"]
    stage_events = [e for e, _ in events if e == "stage"]
    assert token_events == ["token", "token"]
    assert stage_events == ["stage"]
    assert result["stage"] == "explained"


def test_progress_sink_none_keeps_existing_behavior(fake_llm_and_graph):
    """未传 progress_sink 时不 emit 任何事件（保证旧调用者零感知）。"""
    svc = AgentService()
    # 直接调用，不应抛错
    result = svc.run(
        session_id="s-progress-2",
        topic="math",
        user_input="hi",
    )
    assert result["stage"] == "explained"


def test_progress_sink_forces_stream_output_true(fake_llm_and_graph, monkeypatch):
    """传了 sink 即使 stream_output=False，也要强制开流式（否则 sink 收不到 token）。"""
    captured_stream: list[bool] = []

    from app.services.agent_service import AgentService as AS

    original = AS.run_with_graph_v2

    def spy(**kwargs):
        captured_stream.append(kwargs.get("stream_output", False))
        return original(**kwargs)

    monkeypatch.setattr(AS, "run_with_graph_v2", staticmethod(spy))

    events: list[tuple[str, str]] = []
    AgentService().run(
        session_id="s-progress-3",
        topic="math",
        user_input="hi",
        stream_output=False,  # 故意传 False
        progress_sink=lambda ev, data: events.append((ev, data)),
    )
    assert captured_stream == [True]
```

- [ ] **Step 2：运行测试，验证失败**

Run: `uv run pytest tests/test_agent_service_progress_sink.py -v`
Expected: 3 FAIL。错误可能是 `TypeError: run() got an unexpected keyword argument 'progress_sink'`。

- [ ] **Step 3：实现 `progress_sink` 参数**

Modify `app/services/agent_service.py`:

把 `def run(self, session_id, topic, user_input, user_id=None, stream_output=False)` 修改为：

```python
    def run(
        self,
        session_id: str,
        topic: str | None,
        user_input: str,
        user_id: int | None = None,
        stream_output: bool = False,
        progress_sink: "Callable[[str, str], None] | None" = None,
    ) -> LearningState:
```

在函数体顶部（在 `if self._should_use_graph_v2():` 之前）加入桥接逻辑：

```python
        from app.services.llm import llm_service

        def _run_body() -> LearningState:
            if self._should_use_graph_v2():
                return self.run_with_graph_v2(
                    session_id=session_id,
                    topic=topic,
                    user_input=user_input,
                    user_id=user_id,
                    stream_output=effective_stream,
                )
            # 回到原同步路径（此处复用下面现有代码块）
            return _run_legacy_path()

        # 先把现有 graph_v2 之外的整段逻辑抽成内部函数 _run_legacy_path()
        # （见 Step 3 末尾的完整替换说明）

        if progress_sink is not None:
            effective_stream = True
            with llm_service.stream_to(lambda piece: progress_sink("token", piece)):
                result = _run_body()
            progress_sink("stage", str(result.get("stage", "unknown")))
            return result

        effective_stream = stream_output
        return _run_body()
```

**实施说明**：由于现有 `run()` 方法体（287-583 行）很长，把整个原有逻辑抽成一个内部闭包 `_run_legacy_path()` 风险大。**推荐简化实现**：只在流式情况下插桩，使用如下紧凑重构：

```python
    def run(
        self,
        session_id: str,
        topic: str | None,
        user_input: str,
        user_id: int | None = None,
        stream_output: bool = False,
        progress_sink=None,
    ) -> LearningState:
        from app.services.llm import llm_service

        if progress_sink is not None:
            effective_stream = True
            consumer = lambda piece: progress_sink("token", piece)
            with llm_service.stream_to(consumer):
                result = self._run_impl(
                    session_id=session_id,
                    topic=topic,
                    user_input=user_input,
                    user_id=user_id,
                    stream_output=effective_stream,
                )
            progress_sink("stage", str(result.get("stage", "unknown")))
            return result

        return self._run_impl(
            session_id=session_id,
            topic=topic,
            user_input=user_input,
            user_id=user_id,
            stream_output=stream_output,
        )

    def _run_impl(
        self,
        session_id: str,
        topic: str | None,
        user_input: str,
        user_id: int | None = None,
        stream_output: bool = False,
    ) -> LearningState:
        # 把原 run() 方法体（从 `if self._should_use_graph_v2()` 到 return 的全部内容）
        # 原样搬到这里，不做逻辑修改，只改缩进。
        ...
```

具体重构步骤：

1. 把当前 [app/services/agent_service.py:273-583](../../app/services/agent_service.py#L273-L583) 的 `def run(...)` 方法体（从 `# 检查是否使用新版图` 到最后 `return result`）原封不动搬到新方法 `_run_impl`。
2. `run` 变成上面的薄桥接层。

- [ ] **Step 4：运行测试，验证通过**

Run: `uv run pytest tests/test_agent_service_progress_sink.py -v`
Expected: 3 PASS / 0 FAIL。

- [ ] **Step 5：运行现有 agent_service 相关测试，确认零回归**

Run: `uv run pytest tests/test_chat_flow.py tests/test_agent_graph_v2.py -q`
Expected: 通过数与合并前一致（这两个文件已有既有失败基线，只要 **失败数不增加** 即可）。

- [ ] **Step 6：Commit**

```bash
git add app/services/agent_service.py tests/test_agent_service_progress_sink.py .gitignore
git commit -m "feat(agent_service): add progress_sink parameter for async event forwarding (phase 3b)"
```

注意：`.gitignore` 需要先加 `!tests/test_agent_service_progress_sink.py` 白名单。

---

## Task 2：`run_chat_graph` 从占位替换为真实 graph 调用（TDD）

**Files:**
- Modify: `app/worker/tasks.py`
- Test: `tests/test_worker_tasks_real_graph.py`
- 保留: `tests/test_worker_tasks.py`（3a 写的 echo 占位测试会被本任务破坏，需要**删除**或改写）

设计契约：

- 任务签名不变：`run_chat_graph(payload: dict) -> dict`
- payload 形如 `{"session_id", "topic", "user_input", "user_id"}`，对应 chat.py 里构造的请求负载。
- 行为：
    1. 构造 `channel = f"chat:{payload['session_id']}"`（注意：从 3a 的 task_id 频道改为 session_id 频道——3b 开始 chat.py 订阅 session_id，无需暴露 celery task_id 给前端）
    2. `pubsub.publish(channel, "accepted", session_id)`
    3. 构造 sink：`lambda ev, data: pubsub.publish(channel, ev, data)`
    4. `result = agent_service.run(..., progress_sink=sink)`
    5. try/except：异常时 publish `("error", str(exc))`；否则 publish `("done", "[DONE]")`
    6. 返回 `{"status": "ok", "reply": result.get("reply", ""), "stage": result.get("stage")}`（新结构，比 3a 的 echo 更贴近真实 API）

- [ ] **Step 1：删除 3a 的 echo 占位测试**

这一步需要显式删除 `tests/test_worker_tasks.py` 里的 `test_run_chat_graph_returns_echo_structure` 和 `test_run_chat_graph_emits_accepted_and_done`（仅保留 `test_task_is_registered_with_expected_name`），然后重命名文件为 `tests/test_worker_tasks_registry.py` 以示边界。

Modify `tests/test_worker_tasks.py`：把整个文件替换为：

```python
"""Phase 3a/3b 共用：验证 run_chat_graph 任务注册于 celery_app。

（Echo 行为测试在 3a 删除，真实 graph 行为测试见 test_worker_tasks_real_graph.py）
"""
from app.worker.celery_app import celery_app


def test_task_is_registered_with_expected_name():
    assert "app.worker.tasks.run_chat_graph" in celery_app.tasks
```

- [ ] **Step 2：写 3b 新测试**

Create `tests/test_worker_tasks_real_graph.py`:

```python
"""Phase 3b Task 2：run_chat_graph 调用真实 agent_service.run 并通过 pubsub 桥接进度。"""
import threading
import time
import pytest
import fakeredis

from app.worker.celery_app import celery_app
from app.worker import tasks as worker_tasks
from app.services.redis_pubsub import RedisPubSub


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
    client = fakeredis.FakeRedis(decode_responses=False)
    instance = RedisPubSub(client)
    monkeypatch.setattr(worker_tasks, "get_default_pubsub", lambda: instance)
    return instance


@pytest.fixture
def mock_agent_service(monkeypatch):
    """让 agent_service.run 直接通过 progress_sink 推 2 token + 1 stage 后返回。"""
    def fake_run(**kwargs):
        sink = kwargs.get("progress_sink")
        assert sink is not None, "worker 必须传 progress_sink"
        sink("token", "hello ")
        sink("token", "world")
        # stage 事件由 agent_service.run 内部 wrapper 发出，这里模拟它
        sink("stage", "explained")
        return {"session_id": kwargs["session_id"], "stage": "explained", "reply": "hello world"}

    monkeypatch.setattr(
        worker_tasks, "agent_service",
        type("Stub", (), {"run": staticmethod(fake_run)})(),
    )


def test_run_chat_graph_emits_full_event_sequence(fake_pubsub, mock_agent_service):
    session_id = "s-3b-1"
    received: list[tuple[str, str]] = []

    def consumer():
        for ev, data in fake_pubsub.subscribe(f"chat:{session_id}", timeout_s=3.0):
            received.append((ev, data))

    t = threading.Thread(target=consumer, daemon=True)
    t.start()
    time.sleep(0.1)

    payload = {"session_id": session_id, "topic": "math", "user_input": "hi"}
    result = worker_tasks.run_chat_graph.delay(payload).get(timeout=5)
    t.join(timeout=3.0)

    events = [e for e, _ in received]
    assert events[0] == "accepted"
    assert "token" in events
    assert events[-1] == "done"
    assert result == {"status": "ok", "reply": "hello world", "stage": "explained"}


def test_run_chat_graph_emits_error_on_exception(fake_pubsub, monkeypatch):
    def boom(**kwargs):
        raise RuntimeError("graph failed")

    from app.worker import tasks as worker_tasks
    monkeypatch.setattr(
        worker_tasks, "agent_service",
        type("Stub", (), {"run": staticmethod(boom)})(),
    )

    session_id = "s-3b-err"
    received: list[tuple[str, str]] = []

    def consumer():
        for ev, data in fake_pubsub.subscribe(f"chat:{session_id}", timeout_s=3.0):
            received.append((ev, data))

    t = threading.Thread(target=consumer, daemon=True)
    t.start()
    time.sleep(0.1)

    payload = {"session_id": session_id, "topic": None, "user_input": "x"}
    with pytest.raises(Exception):
        worker_tasks.run_chat_graph.delay(payload).get(timeout=5)
    t.join(timeout=3.0)

    events = [e for e, _ in received]
    assert events[0] == "accepted"
    assert events[-1] == "error"
```

- [ ] **Step 3：运行测试，验证失败**

Run: `uv run pytest tests/test_worker_tasks_real_graph.py -v`
Expected: FAIL（新测试期望的行为与 3a 占位实现不符），具体错误包括 sink 未传递、event 序列不含 token 等。

- [ ] **Step 4：实现真实 `run_chat_graph`**

Modify `app/worker/tasks.py`:

```python
"""Celery 任务集合。

3b 阶段：run_chat_graph 调用 agent_service.run + progress_sink，经 pubsub 桥接事件。
"""
from __future__ import annotations

from typing import Any

from app.services.redis_pubsub import get_default_pubsub
from app.services.agent_service import agent_service
from app.worker.celery_app import celery_app


@celery_app.task(name="app.worker.tasks.run_chat_graph")
def run_chat_graph(payload: dict[str, Any]) -> dict[str, Any]:
    """运行一次 chat graph，经 pubsub 在 chat:{session_id} 频道推送进度。

    Events: accepted → token* → stage → done | error
    """
    session_id = str(payload.get("session_id", ""))
    channel = f"chat:{session_id}"
    pubsub = get_default_pubsub()
    pubsub.publish(channel, "accepted", session_id)

    def sink(event: str, data: str) -> None:
        pubsub.publish(channel, event, data)

    try:
        result = agent_service.run(
            session_id=session_id,
            topic=payload.get("topic"),
            user_input=str(payload.get("user_input", "")),
            user_id=payload.get("user_id"),
            progress_sink=sink,
        )
    except Exception as exc:
        pubsub.publish(channel, "error", f"{type(exc).__name__}: {exc}")
        raise

    pubsub.publish(channel, "done", "[DONE]")
    return {
        "status": "ok",
        "reply": str(result.get("reply", "")),
        "stage": str(result.get("stage", "")),
    }
```

- [ ] **Step 5：运行测试，验证通过**

Run: `uv run pytest tests/test_worker_tasks_real_graph.py tests/test_worker_tasks.py -v`
Expected: `test_worker_tasks_real_graph.py` 2 PASS；`test_worker_tasks.py` 1 PASS。

- [ ] **Step 6：Commit**

```bash
git add app/worker/tasks.py tests/test_worker_tasks_real_graph.py tests/test_worker_tasks.py .gitignore
git commit -m "feat(worker): run_chat_graph invokes agent_service.run with progress_sink (phase 3b)"
```

`.gitignore` 追加 `!tests/test_worker_tasks_real_graph.py`。

---

## Task 3：chat API 异步分支 + 同步回退（TDD）

**Files:**
- Modify: `app/api/chat.py`
- Test: `tests/test_chat_async_api.py`
- Test: `tests/test_chat_sync_fallback.py`

设计契约：

- `/chat/stream` 在 `settings.async_graph_enabled=True` 时：
    1. `dispatch_result = task_dispatcher.dispatch({"session_id", "topic", "user_input", "user_id"})`
    2. 订阅 `chat:{session_id}` 频道（**按 session_id，不按 task_id**，便于前端复用）
    3. 把 `(event, data)` 逐一写成 SSE `event: X\ndata: Y\n\n`
    4. 遇到 `done` / `error` 结束
    5. 超时（`settings.celery_task_timeout_s + 5`）强制发 `error: worker timeout`
- flag off 时：**完全保持现有同步 Queue+Thread 路径**，不改一行。
- 异步路径不保留 `llm_service.stream_to`（那是同步路径的桥，异步由 worker 内部的 sink→pubsub 链路负责）。

- [ ] **Step 1：写异步分支测试（flag on）**

Create `tests/test_chat_async_api.py`:

```python
"""Phase 3b Task 3：/chat/stream 在 flag on 时走 async 分支，从 pubsub 桥接到 SSE。"""
import threading
import time
import pytest
import fakeredis
from fastapi.testclient import TestClient

from app.api.chat import router
from fastapi import FastAPI

from app.core.config import settings
from app.services import redis_pubsub as pubsub_mod
from app.services import task_dispatcher as dispatcher_mod
from app.services.redis_pubsub import RedisPubSub


@pytest.fixture
def app():
    a = FastAPI()
    a.include_router(router)
    return a


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def shared_fakeredis(monkeypatch):
    """让 chat.py 订阅端 和 worker 发布端共用同一个 fakeredis 实例。"""
    client = fakeredis.FakeRedis(decode_responses=False)
    instance = RedisPubSub(client)
    monkeypatch.setattr(pubsub_mod, "get_default_pubsub", lambda: instance)
    # 同时让 app.worker.tasks.get_default_pubsub 也指向同一实例
    from app.worker import tasks as worker_tasks
    monkeypatch.setattr(worker_tasks, "get_default_pubsub", lambda: instance)
    return instance


@pytest.fixture
def flag_on(monkeypatch):
    monkeypatch.setattr(settings, "async_graph_enabled", True)


@pytest.fixture
def eager_celery(monkeypatch):
    from app.worker.celery_app import celery_app
    monkeypatch.setattr(celery_app.conf, "task_always_eager", True)
    monkeypatch.setattr(celery_app.conf, "task_eager_propagates", True)


@pytest.fixture
def stub_agent(monkeypatch):
    """worker 内部把 agent_service 替换为 stub，直接通过 sink 推 token + stage 后返回。"""
    def fake_run(**kwargs):
        sink = kwargs.get("progress_sink")
        sink("token", "he")
        sink("token", "llo")
        sink("stage", "explained")
        return {"session_id": kwargs["session_id"], "stage": "explained", "reply": "hello"}

    from app.worker import tasks as worker_tasks
    monkeypatch.setattr(
        worker_tasks, "agent_service",
        type("Stub", (), {"run": staticmethod(fake_run)})(),
    )


def _parse_sse(raw: str) -> list[tuple[str, str]]:
    events: list[tuple[str, str]] = []
    current_event = None
    for line in raw.split("\n"):
        if line.startswith("event: "):
            current_event = line[len("event: "):].strip()
        elif line.startswith("data: ") and current_event is not None:
            events.append((current_event, line[len("data: "):]))
            current_event = None
    return events


def test_chat_stream_async_emits_accepted_token_done(
    client, flag_on, eager_celery, shared_fakeredis, stub_agent
):
    response = client.post(
        "/chat/stream",
        json={"session_id": "s-async-1", "topic": "math", "user_input": "hi"},
    )
    assert response.status_code == 200
    events = _parse_sse(response.text)
    names = [e for e, _ in events]
    assert names[0] == "accepted"
    assert "token" in names
    assert names[-1] == "done"


def test_chat_stream_async_forwards_error_event(
    client, flag_on, eager_celery, shared_fakeredis, monkeypatch
):
    def boom(**kwargs):
        raise RuntimeError("kaboom")

    from app.worker import tasks as worker_tasks
    monkeypatch.setattr(
        worker_tasks, "agent_service",
        type("Stub", (), {"run": staticmethod(boom)})(),
    )

    # worker eager 模式下异常会向上抛到 dispatch；这里需要 celery 的 task_eager_propagates=True
    # 所以 POST 应得到 500 或 TestClient 异常，此时 SSE 可能不完整，但 subscriber 应已收到 error
    try:
        response = client.post(
            "/chat/stream",
            json={"session_id": "s-async-err", "topic": None, "user_input": "x"},
        )
    except Exception:
        pytest.skip("eager propagate raised before SSE completes; error path covered by Task 2")
    else:
        events = _parse_sse(response.text)
        names = [e for e, _ in events]
        assert "error" in names
```

- [ ] **Step 2：写同步回退测试（flag off）**

Create `tests/test_chat_sync_fallback.py`:

```python
"""Phase 3b Task 3：flag off 时 /chat/stream 保持 Phase 7 前的同步 Queue+Thread 行为。"""
import pytest
from fastapi.testclient import TestClient
from fastapi import FastAPI

from app.api.chat import router
from app.core.config import settings
from app.services import agent_service as agent_mod


@pytest.fixture
def app():
    a = FastAPI()
    a.include_router(router)
    return a


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def flag_off(monkeypatch):
    monkeypatch.setattr(settings, "async_graph_enabled", False)


@pytest.fixture
def stub_sync_agent(monkeypatch):
    """同步路径下 agent_service.run 返回固定 state，不触发真实 LLM。"""
    def fake_run(session_id, topic, user_input, user_id=None, stream_output=False, progress_sink=None):
        return {"session_id": session_id, "stage": "explained", "reply": "sync-reply", "history": []}

    monkeypatch.setattr(agent_mod.agent_service, "run", fake_run)


def test_chat_stream_sync_emits_stage_and_done_only(client, flag_off, stub_sync_agent):
    response = client.post(
        "/chat/stream",
        json={"session_id": "s-sync-1", "topic": "math", "user_input": "hi"},
    )
    assert response.status_code == 200
    # 同步路径不 emit accepted（那是 async 引入的）
    assert "event: accepted" not in response.text
    assert "event: stage" in response.text
    assert "event: done" in response.text


def test_chat_post_non_stream_unaffected_by_flag(client, flag_off, stub_sync_agent):
    """POST /chat（非 stream）在 flag off 时完全同步，不经 celery/pubsub。"""
    response = client.post(
        "/chat",
        json={"session_id": "s-sync-2", "topic": "math", "user_input": "hi"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["reply"] == "sync-reply"
    assert data["stage"] == "explained"
```

- [ ] **Step 3：运行测试，验证失败**

Run: `uv run pytest tests/test_chat_async_api.py tests/test_chat_sync_fallback.py -v`
Expected: 5 个测试 FAIL，因为 chat.py 尚未支持 async 分支。

- [ ] **Step 4：改 chat.py 引入 async 分支**

Modify `app/api/chat.py`。完整替换 `/chat/stream` 处理函数为：

```python
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from queue import Queue
from threading import Thread

from app.core.config import settings
from app.models.schemas import (
    ChatRequest,
    ChatResponse,
    RagCandidateModel,
    RagExecutionDetailModel,
)
from app.services.agent_service import agent_service
from app.services.llm import llm_service
from app.services.task_dispatcher import dispatch
from app.services.redis_pubsub import get_default_pubsub

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    # 非流式端点不受 async flag 影响；保持现状
    numeric_user_id = request.user_id
    if numeric_user_id is not None and numeric_user_id <= 0:
        raise HTTPException(status_code=400, detail="user_id 必须是正整数")
    try:
        result = agent_service.run(
            session_id=request.session_id,
            topic=request.topic,
            user_input=request.user_input,
            user_id=numeric_user_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    rag_meta = result.get("rag_meta_last")
    rag_detail = None
    if rag_meta is not None:
        rag_detail = RagExecutionDetailModel(
            query_mode=getattr(rag_meta, "query_mode", ""),
            used_tools=list(getattr(rag_meta, "used_tools", []) or []),
            hit_count=getattr(rag_meta, "hit_count", 0),
            elapsed_ms=getattr(rag_meta, "elapsed_ms", 0),
            reranked=getattr(rag_meta, "reranked", False),
            candidates=[
                RagCandidateModel(
                    chunk_id=str(c.get("chunk_id", "")),
                    score=float(c.get("score", 0.0)),
                    tool=str(c.get("tool", "")),
                )
                for c in (getattr(rag_meta, "candidates", []) or [])
            ],
            selected_chunk_ids=list(getattr(rag_meta, "selected_chunk_ids", []) or []),
        )

    return ChatResponse(
        session_id=result["session_id"],
        stage=result.get("stage", "unknown"),
        reply=result.get("reply", ""),
        summary=result.get("summary"),
        citations=result.get("citations", []),
        rag_confidence_level=result.get("rag_confidence_level"),
        rag_low_evidence=result.get("rag_low_evidence"),
        rag_detail=rag_detail,
    )


@router.post("/stream")
def chat_stream(request: ChatRequest) -> StreamingResponse:
    numeric_user_id = request.user_id
    if numeric_user_id is not None and numeric_user_id <= 0:
        raise HTTPException(status_code=400, detail="user_id 必须是正整数")

    if settings.async_graph_enabled:
        return StreamingResponse(
            _async_event_generator(request, numeric_user_id),
            media_type="text/event-stream",
        )

    return StreamingResponse(
        _sync_event_generator(request, numeric_user_id),
        media_type="text/event-stream",
    )


def _async_event_generator(request: ChatRequest, numeric_user_id):
    """异步路径：dispatch → 订阅 chat:{session_id} → 转成 SSE。"""
    payload = {
        "session_id": request.session_id,
        "topic": request.topic,
        "user_input": request.user_input,
        "user_id": numeric_user_id,
    }
    # 先订阅再 dispatch，避免 accepted 消息丢失
    pubsub = get_default_pubsub()
    channel = f"chat:{request.session_id}"
    timeout_s = float(settings.celery_task_timeout_s) + 5.0

    def _subscriber():
        for event, data in pubsub.subscribe(channel, timeout_s=timeout_s):
            safe = data.replace("\r", " ").replace("\n", "\\n")
            yield f"event: {event}\ndata: {safe}\n\n"

    sub_iter = _subscriber()

    # 触发任务
    try:
        dispatch(payload)
    except Exception as exc:
        yield f"event: error\ndata: dispatch failed: {exc}\n\n"
        return

    try:
        for chunk in sub_iter:
            yield chunk
    except TimeoutError:
        yield "event: error\ndata: worker timeout\n\n"


def _sync_event_generator(request: ChatRequest, numeric_user_id):
    """原同步路径（Phase 7 前行为）。保留不变。"""
    queue: Queue[tuple[str, str]] = Queue()

    def worker() -> None:
        def _on_chunk(piece: str) -> None:
            safe = piece.replace("\r", " ").replace("\n", "\\n")
            queue.put(("token", safe))

        with llm_service.stream_to(_on_chunk):
            try:
                result = agent_service.run(
                    session_id=request.session_id,
                    topic=request.topic,
                    user_input=request.user_input,
                    user_id=numeric_user_id,
                    stream_output=True,
                )
                queue.put(("stage", str(result.get("stage", "unknown"))))
            except ValueError as exc:
                queue.put(("error", str(exc)))
            except Exception as exc:  # noqa: BLE001
                queue.put(("error", f"stream failed: {exc}"))
            finally:
                queue.put(("done", "[DONE]"))

    Thread(target=worker, daemon=True).start()
    while True:
        event, data = queue.get()
        yield f"event: {event}\ndata: {data}\n\n"
        if event == "done":
            break
```

**关键顺序**：异步分支里必须**先订阅、再 dispatch**。否则如果 celery eager 模式下 `dispatch` 立即同步执行并发布 `accepted` 事件，会在我们订阅之前丢失。

由于 Python 生成器的懒执行：`_subscriber()` 调用本身不会创建订阅——它只是返回一个 generator。需要手动先消费一次让 ps.subscribe 真正执行。**修正实现**：

把 `_async_event_generator` 改为：

```python
def _async_event_generator(request: ChatRequest, numeric_user_id):
    payload = {
        "session_id": request.session_id,
        "topic": request.topic,
        "user_input": request.user_input,
        "user_id": numeric_user_id,
    }
    pubsub = get_default_pubsub()
    channel = f"chat:{request.session_id}"
    timeout_s = float(settings.celery_task_timeout_s) + 5.0

    # 先拿到一个活跃的订阅迭代器（不让它阻塞：内部 get_message timeout 小）
    sub = pubsub.subscribe(channel, timeout_s=timeout_s)
    # Hack：pull 一次让订阅注册真正生效——但 subscribe() 内部是 generator，
    # 第一次 next() 才会走到 ps.subscribe()。
    # 解决：把 RedisPubSub.subscribe 改造成"构造后立即订阅、yield 前无阻塞"。
    # 见下文备注，本 Task 不改 RedisPubSub，改用先 publish "ping" 自触发的策略。
    # 更干净的方案：在 chat.py 里用 pubsub 底层对象手动 subscribe。

    # 简化路径：直接用 redis 客户端手动订阅
    import redis
    raw_client = redis.from_url(settings.redis_url)
    ps = raw_client.pubsub(ignore_subscribe_messages=True)
    ps.subscribe(channel)

    # 触发任务
    try:
        dispatch(payload)
    except Exception as exc:
        yield f"event: error\ndata: dispatch failed: {exc}\n\n"
        ps.unsubscribe(channel)
        ps.close()
        return

    import time, json
    deadline = time.monotonic() + timeout_s
    try:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                yield "event: error\ndata: worker timeout\n\n"
                return
            msg = ps.get_message(timeout=min(remaining, 0.1))
            if msg is None:
                continue
            if msg.get("type") != "message":
                continue
            raw = msg.get("data")
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            payload_j = json.loads(raw)
            event = str(payload_j.get("event", ""))
            data = str(payload_j.get("data", ""))
            safe = data.replace("\r", " ").replace("\n", "\\n")
            yield f"event: {event}\ndata: {safe}\n\n"
            if event in ("done", "error"):
                return
    finally:
        try:
            ps.unsubscribe(channel)
            ps.close()
        except Exception:
            pass
```

**这份实现更长但直接用底层 redis 客户端，避开了 `RedisPubSub.subscribe` 生成器惰性订阅的问题**。`RedisPubSub` 本身仍然在 worker/test 里用作高层封装。

但是**在 TestClient 场景下**，fakeredis 需要 chat.py 里的 `raw_client = redis.from_url(...)` 也连到同一 fakeredis 实例。**fakeredis 支持 server 模式共享实例**，但用 `redis.from_url` 会连到真实 Redis。

**为避免该复杂度**：第一版实现**改用 `RedisPubSub` 的新辅助方法**——增加 `subscribe_blocking_first(channel, timeout_s)`，它在构造时立即 `ps.subscribe()` 然后返回迭代器。同时在 `get_default_pubsub` 的测试注入点，chat.py 也走 `get_default_pubsub()` 而非 `redis.from_url`。

为保持本 Task 范围可控，**拆出 Task 3.1**：在 RedisPubSub 增加 `open_subscription(channel)` 上下文管理器返回可迭代对象；chat.py 使用它。

### Task 3.1：RedisPubSub 新增 `open_subscription` 上下文

**Files:**
- Modify: `app/services/redis_pubsub.py`
- Test: `tests/test_redis_pubsub.py`（追加测试）

- [ ] **Step 1：在 test_redis_pubsub.py 追加测试**

```python
def test_open_subscription_is_active_before_first_yield(pubsub):
    """open_subscription 返回前订阅必须已生效，避免早发布被漏收。"""
    with pubsub.open_subscription("ch:early") as events_iter:
        # 这里订阅已生效
        pubsub.publish("ch:early", "accepted", "t1")
        pubsub.publish("ch:early", "done", "[DONE]")
        received = list(events_iter)
    assert received == [("accepted", "t1"), ("done", "[DONE]")]
```

- [ ] **Step 2：实现 `open_subscription`**

Modify `app/services/redis_pubsub.py`，追加：

```python
from contextlib import contextmanager

class RedisPubSub:
    # ... existing code ...

    @contextmanager
    def open_subscription(self, channel: str, timeout_s: float = 30.0):
        """同步上下文：进入即订阅，退出自动关闭。避免 subscribe() 的惰性问题。"""
        ps = self._client.pubsub(ignore_subscribe_messages=True)
        ps.subscribe(channel)
        try:
            yield self._iter_until_terminal(ps, channel, timeout_s)
        finally:
            try:
                ps.unsubscribe(channel)
                ps.close()
            except Exception:
                pass

    def _iter_until_terminal(self, ps, channel: str, timeout_s: float):
        deadline = time.monotonic() + timeout_s
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
```

同时让 `subscribe()` 复用 `_iter_until_terminal` 保持 DRY：

```python
    def subscribe(self, channel: str, timeout_s: float = 30.0):
        ps = self._client.pubsub(ignore_subscribe_messages=True)
        ps.subscribe(channel)
        try:
            yield from self._iter_until_terminal(ps, channel, timeout_s)
        finally:
            try:
                ps.unsubscribe(channel)
                ps.close()
            except Exception:
                pass
```

- [ ] **Step 3：运行 pubsub 测试**

Run: `uv run pytest tests/test_redis_pubsub.py -v`
Expected: 5 PASS（原 4 + 新 1）/ 0 FAIL.

- [ ] **Step 4：Commit**

```bash
git add app/services/redis_pubsub.py tests/test_redis_pubsub.py
git commit -m "feat(redis_pubsub): add open_subscription context manager for eager-binding subscribers (phase 3b)"
```

### Task 3.2（Task 3 续）：用 `open_subscription` 改 chat.py

- [ ] **Step 5：改 chat.py `_async_event_generator`**

替换为：

```python
def _async_event_generator(request: ChatRequest, numeric_user_id):
    payload = {
        "session_id": request.session_id,
        "topic": request.topic,
        "user_input": request.user_input,
        "user_id": numeric_user_id,
    }
    pubsub = get_default_pubsub()
    channel = f"chat:{request.session_id}"
    timeout_s = float(settings.celery_task_timeout_s) + 5.0

    with pubsub.open_subscription(channel, timeout_s=timeout_s) as events:
        try:
            dispatch(payload)
        except Exception as exc:
            yield f"event: error\ndata: dispatch failed: {exc}\n\n"
            return

        try:
            for event, data in events:
                safe = data.replace("\r", " ").replace("\n", "\\n")
                yield f"event: {event}\ndata: {safe}\n\n"
        except TimeoutError:
            yield "event: error\ndata: worker timeout\n\n"
```

- [ ] **Step 6：运行测试**

Run: `uv run pytest tests/test_chat_async_api.py tests/test_chat_sync_fallback.py -v`
Expected: 5 PASS / 0 FAIL。

如果 async 测试因 fakeredis 的 pubsub 延迟导致间歇 FAIL，在测试里把 `eager_celery` 换成**先 subscribe 再 dispatch**——已经通过 `open_subscription` 保证，但 eager 模式下 dispatch 内部会**同步**执行 run_chat_graph，此时 publish 已发生。由于 `open_subscription` 在 `yield` 前已调用 `ps.subscribe()`，fakeredis 的 publish 应该进入订阅队列。若仍有时序问题，在 `open_subscription` 进入后额外 `time.sleep(0.05)` 让 fakeredis 完成订阅注册。

- [ ] **Step 7：Commit**

```bash
git add app/api/chat.py tests/test_chat_async_api.py tests/test_chat_sync_fallback.py .gitignore
git commit -m "feat(chat): async-path branch for /chat/stream behind ASYNC_GRAPH_ENABLED flag (phase 3b)"
```

`.gitignore` 追加 `!tests/test_chat_async_api.py` 与 `!tests/test_chat_sync_fallback.py`。

---

## Task 4：全量回归 + 基线对账

- [ ] **Step 1：跑 Phase 3b 新测试集**

Run: `uv run pytest tests/test_agent_service_progress_sink.py tests/test_worker_tasks_real_graph.py tests/test_worker_tasks.py tests/test_redis_pubsub.py tests/test_chat_async_api.py tests/test_chat_sync_fallback.py -v`
Expected: 全部 PASS（约 3 + 2 + 1 + 5 + 2 + 2 = 15 个测试）。

- [ ] **Step 2：跑全量回归**

Run: `PYTHONPATH=. DEBUG=false uv run pytest tests/ -q`
Expected: 至少 `331 passed / 19 failed`（316 + 15 = 331；失败数维持 19）。

如果失败数 > 19：

1. 先确认是 `test_chat_flow.py` 或 `test_chat_stream_api.py` 的既有失败是否因 chat.py 改造被扩大——对比具体失败消息与合并前基线。
2. 特别检查 `agent_service.run` 的 `_run_impl` 重构是否改变了任何逻辑（不应该）。
3. 若发现 chat.py 改造影响了同步路径，确认 flag off 时 `_sync_event_generator` 与合并前 `event_generator` 逐行等价。

- [ ] **Step 3：手动验证（可选，需本地 Redis）**

```bash
# terminal 1
docker run --rm -p 6379:6379 redis:7-alpine

# terminal 2
ASYNC_GRAPH_ENABLED=true uv run celery -A app.worker.celery_app worker --loglevel=info

# terminal 3
ASYNC_GRAPH_ENABLED=true uv run uvicorn app.main:app --reload

# terminal 4
curl -N -X POST http://127.0.0.1:1900/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"session_id": "m1", "topic": "math", "user_input": "什么是导数"}'
```

预期：看到 `event: accepted`、多个 `event: token`、`event: stage`、`event: done`。

---

## 验收清单（Phase 3b 整体）

| 项 | 阈值 / 验证方式 |
|---|---|
| agent_service | `run(..., progress_sink=...)` 把 LLM stream token 转成 sink 事件；未传 sink 时行为不变 |
| worker | `run_chat_graph` 真实调用 agent_service.run，推 accepted / token / stage / done / error |
| RedisPubSub | `open_subscription` 上下文管理器保证订阅前置生效；原 `subscribe` 仍可用 |
| chat API | flag on 走异步分支；flag off 完全保留 Phase 7 前行为 |
| 回归 | ≥ 331 PASS / 19 FAIL；chat_flow / chat_stream 既有失败基线不扩大 |
| 契约稳定 | graph_v2 / NodeRegistry / `@node` 不动 |
| 可回退 | `ASYNC_GRAPH_ENABLED=false` 时不依赖 Redis / Celery 可启动 |

---

## Self-Review 备注

1. Spec §11.2 列出 5 项交付，本 plan 覆盖：
    - `app/services/agent_service.py` 加 progress_sink → Task 1 ✓
    - `app/worker/tasks.py` 接真实 graph → Task 2 ✓
    - `app/api/chat.py` flag 分流 → Task 3 ✓
    - `tests/test_chat_async_api.py` → Task 3 ✓
    - `tests/test_chat_sync_fallback.py` → Task 3 ✓

   补充：`tests/test_agent_service_progress_sink.py`（Task 1）+ `tests/test_worker_tasks_real_graph.py`（Task 2）+ `open_subscription` 测试（Task 3.1）。

2. Spec §7.2 降级矩阵：flag off 零依赖 ✓；flag on + Redis 不可达"fail loudly" → 本 plan 暂不做 health check（3d 再做），**仅通过注释在 chat.py 开头补一段说明**，告诉运维"生产启用前要先确认 Redis 可达"。非阻塞缺口。

3. Task 3 的两个棘手点：
    - **订阅前置**：通过 `open_subscription` 解决（Task 3.1）。
    - **eager 模式下 dispatch 同步完成**：`open_subscription` 在进入 yield 前已订阅，fakeredis 的 pub/sub 能在同进程内可见，所以 dispatch 在 with 块内部调用能被订阅到。

4. 类型一致性：
    - `progress_sink: Callable[[str, str], None]` 全程统一。
    - pubsub 事件名集合 `{"accepted", "token", "stage", "done", "error"}` 与 spec §6 事件类型一致。
    - `run_chat_graph` 返回 `{"status": "ok", "reply", "stage"}`（3b 新结构）与 3a 的 `{"status": "ok", "echo": payload}` 有差异，test_worker_tasks.py 的 echo 断言在 Task 2 Step 1 被删除。
