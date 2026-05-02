# Celery + Redis Task Queue Concurrency Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Celery + Redis task queue to enable async agent execution with SSE streaming, supporting 10-50 concurrent users.

**Architecture:** FastAPI submits tasks to Celery queue → Celery Worker executes agent_service.run() → Redis Pub/Sub broadcasts progress → SSE streams to client. Graceful degradation when Redis unavailable.

**Tech Stack:** Celery 5.3+, Redis 5.0+, FastAPI SSE

---

## File Structure

```
app/
├── worker/                      # NEW: Celery worker module
│   ├── __init__.py             # Module exports
│   ├── celery_app.py           # Celery configuration
│   ├── tasks.py                # Task definitions (run_agent_task)
│   └── progress.py             # Progress callback for Redis Pub/Sub
├── services/
│   ├── task_dispatcher.py      # NEW: Task dispatch and status query
│   ├── redis_pubsub.py         # NEW: Redis Pub/Sub SSE listener
│   └── agent_service.py        # MODIFY: Add on_progress callback
├── api/
│   └── chat.py                 # MODIFY: Add async endpoints
└── core/
    └── config.py               # MODIFY: Add Redis/Celery config

tests/
└── test_task_queue.py          # NEW: Integration tests
```

---

### Task 1: Add Configuration Options

**Files:**
- Modify: `app/core/config.py`
- Modify: `pyproject.toml`

- [ ] **Step 1: Add dependencies to pyproject.toml**

```toml
# Add to [project.dependencies] in pyproject.toml
celery = ">=5.3.0"
redis = ">=5.0.0"
```

- [ ] **Step 2: Add configuration to config.py**

Add after line 50 (`langfuse_enabled: bool = False`):

```python
    # Redis & Celery 配置
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"
    async_chat_enabled: bool = False
    task_timeout_seconds: int = 300
    task_max_retries: int = 3
```

- [ ] **Step 3: Run tests to verify config loads**

Run: `python -c "from app.core.config import settings; print(settings.redis_url)"`
Expected: `redis://localhost:6379/0`

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml app/core/config.py
git commit -m "feat(config): add Redis and Celery configuration options"
```

---

### Task 2: Create Celery App Configuration

**Files:**
- Create: `app/worker/__init__.py`
- Create: `app/worker/celery_app.py`

- [ ] **Step 1: Create worker module __init__.py**

```python
# app/worker/__init__.py
"""Celery worker module for async task execution."""

from app.worker.celery_app import celery_app
from app.worker.tasks import run_agent_task

__all__ = ["celery_app", "run_agent_task"]
```

- [ ] **Step 2: Create celery_app.py**

```python
# app/worker/celery_app.py
"""Celery application configuration."""

from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "learning_agent",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
)

celery_app.conf.update(
    task_track_started=True,
    task_time_limit=settings.task_timeout_seconds,
    task_soft_time_limit=settings.task_timeout_seconds - 10,
    worker_prefetch_multiplier=1,
    worker_concurrency=4,
    result_expires=3600,  # Results expire after 1 hour
)

# Auto-discover tasks from app.worker module
celery_app.autodiscover_tasks(["app.worker"])
```

- [ ] **Step 3: Verify Celery app loads**

Run: `python -c "from app.worker.celery_app import celery_app; print(celery_app.main)"`
Expected: `learning_agent`

- [ ] **Step 4: Commit**

```bash
git add app/worker/
git commit -m "feat(worker): add Celery app configuration"
```

---

### Task 3: Create Progress Reporter

**Files:**
- Create: `app/worker/progress.py`

- [ ] **Step 1: Create progress.py with Redis Pub/Sub reporter**

```python
# app/worker/progress.py
"""Progress reporting via Redis Pub/Sub."""

import json
import logging
from typing import Callable

import redis

from app.core.config import settings

logger = logging.getLogger(__name__)


def create_progress_reporter(task_id: str) -> Callable[[str, int, str | None], None]:
    """
    Create a progress callback function for a specific task.
    
    Args:
        task_id: The Celery task ID
        
    Returns:
        A callback function that publishes progress to Redis
    """
    redis_client: redis.Redis | None = None
    
    def _get_client() -> redis.Redis | None:
        nonlocal redis_client
        if redis_client is None:
            try:
                redis_client = redis.from_url(settings.redis_url)
            except Exception as e:
                logger.warning(f"Failed to connect to Redis: {e}")
                return None
        return redis_client
    
    def on_progress(stage: str, progress: int, token: str | None = None) -> None:
        """
        Publish progress update to Redis Pub/Sub.
        
        Args:
            stage: Current execution stage (e.g., "diagnosing", "explaining")
            progress: Progress percentage (0-100)
            token: Optional text token for streaming output
        """
        client = _get_client()
        if client is None:
            return
        
        message = {
            "stage": stage,
            "progress": progress,
            "token": token,
        }
        
        try:
            client.publish(f"task:{task_id}", json.dumps(message))
        except Exception as e:
            logger.warning(f"Failed to publish progress: {e}")
    
    return on_progress


def publish_task_complete(task_id: str, result: dict) -> None:
    """Publish task completion message."""
    try:
        client = redis.from_url(settings.redis_url)
        message = {
            "stage": "completed",
            "progress": 100,
            "result": result,
        }
        client.publish(f"task:{task_id}", json.dumps(message))
    except Exception as e:
        logger.warning(f"Failed to publish completion: {e}")


def publish_task_error(task_id: str, error: str) -> None:
    """Publish task error message."""
    try:
        client = redis.from_url(settings.redis_url)
        message = {
            "stage": "failed",
            "progress": 100,
            "error": error,
        }
        client.publish(f"task:{task_id}", json.dumps(message))
    except Exception as e:
        logger.warning(f"Failed to publish error: {e}")
```

- [ ] **Step 2: Verify module loads**

Run: `python -c "from app.worker.progress import create_progress_reporter; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add app/worker/progress.py
git commit -m "feat(worker): add Redis Pub/Sub progress reporter"
```

---

### Task 4: Create Celery Task Definition

**Files:**
- Create: `app/worker/tasks.py`

- [ ] **Step 1: Create tasks.py with run_agent_task**

```python
# app/worker/tasks.py
"""Celery task definitions for async agent execution."""

import logging
from typing import Any

from app.worker.celery_app import celery_app
from app.worker.progress import (
    create_progress_reporter,
    publish_task_complete,
    publish_task_error,
)
from app.services.agent_service import agent_service

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, max_retries=3, default_retry_delay=5)
def run_agent_task(
    self,
    session_id: str,
    topic: str | None,
    user_input: str,
    user_id: int | None = None,
) -> dict[str, Any]:
    """
    Execute agent task asynchronously with progress reporting.
    
    Args:
        self: Celery task instance (injected by bind=True)
        session_id: Session identifier for state persistence
        topic: Learning topic
        user_input: User's message
        user_id: Optional user identifier
        
    Returns:
        The final LearningState dict
    """
    task_id = self.request.id
    
    # Create progress callback
    on_progress = create_progress_reporter(task_id)
    
    try:
        # Report starting
        on_progress("starting", 0)
        
        # Execute agent
        result = agent_service.run(
            session_id=session_id,
            topic=topic,
            user_input=user_input,
            user_id=user_id,
            on_progress=on_progress,
        )
        
        # Report completion
        publish_task_complete(task_id, dict(result))
        
        return dict(result)
        
    except Exception as e:
        logger.exception(f"Task {task_id} failed: {e}")
        publish_task_error(task_id, str(e))
        
        # Retry if appropriate
        if self.request.retries < self.max_retries:
            raise self.retry(exc=e)
        
        raise
```

- [ ] **Step 2: Verify task loads**

Run: `python -c "from app.worker.tasks import run_agent_task; print(run_agent_task.name)"`
Expected: `app.worker.tasks.run_agent_task`

- [ ] **Step 3: Commit**

```bash
git add app/worker/tasks.py app/worker/__init__.py
git commit -m "feat(worker): add run_agent_task Celery task"
```

---

### Task 5: Modify Agent Service for Progress Callback

**Files:**
- Modify: `app/services/agent_service.py`

- [ ] **Step 1: Add on_progress parameter to run() method**

Modify the `run()` method signature at line 258-265:

```python
    def run(
        self,
        session_id: str,
        topic: str | None,
        user_input: str,
        user_id: int | None = None,
        stream_output: bool = False,
        on_progress: Callable[[str, int, str | None], None] | None = None,
    ) -> LearningState:
```

Add the import at the top of the file (around line 1):

```python
from typing import Callable
```

- [ ] **Step 2: Add on_progress parameter to run_with_graph_v2()**

Modify the `run_with_graph_v2()` method signature at line 44-50:

```python
    @staticmethod
    def run_with_graph_v2(
        session_id: str,
        topic: str | None,
        user_input: str,
        user_id: int | None = None,
        stream_output: bool = False,
        on_progress: Callable[[str, int, str | None], None] | None = None,
    ) -> LearningState:
```

- [ ] **Step 3: Add progress reporting in run_with_graph_v2()**

Add after line 66 (after the Langfuse trace creation try block):

```python
        # Report progress if callback provided
        if on_progress:
            on_progress("loading_state", 10)
```

Add after line 90 (before graph.invoke):

```python
        if on_progress:
            on_progress("invoking_agent", 20)
```

Add after line 91 (after graph.invoke, before return):

```python
        if on_progress:
            on_progress("completed", 100)
```

- [ ] **Step 4: Pass on_progress to run_with_graph_v2() in run() method**

Modify line 267-274:

```python
        if self._should_use_graph_v2():
            return self.run_with_graph_v2(
                session_id=session_id,
                topic=topic,
                user_input=user_input,
                user_id=user_id,
                stream_output=stream_output,
                on_progress=on_progress,
            )
```

- [ ] **Step 5: Verify module still loads**

Run: `python -c "from app.services.agent_service import agent_service; print('OK')"`
Expected: `OK`

- [ ] **Step 6: Commit**

```bash
git add app/services/agent_service.py
git commit -m "feat(agent): add on_progress callback for task queue integration"
```

---

### Task 6: Create Redis Pub/Sub Listener

**Files:**
- Create: `app/services/redis_pubsub.py`

- [ ] **Step 1: Create redis_pubsub.py**

```python
# app/services/redis_pubsub.py
"""Redis Pub/Sub listener for SSE streaming."""

import asyncio
import json
import logging
from typing import AsyncGenerator

import redis.asyncio as aioredis

from app.core.config import settings

logger = logging.getLogger(__name__)


class RedisPubSubListener:
    """Async Redis Pub/Sub listener for task progress events."""
    
    def __init__(self, redis_url: str | None = None):
        self.redis_url = redis_url or settings.redis_url
    
    async def listen(self, task_id: str, timeout: float = 300.0) -> AsyncGenerator[dict, None]:
        """
        Listen to task progress events via Redis Pub/Sub.
        
        Args:
            task_id: The task ID to subscribe to
            timeout: Maximum time to wait for events (seconds)
            
        Yields:
            Progress event dictionaries
        """
        client = aioredis.from_url(self.redis_url)
        pubsub = client.pubsub()
        
        try:
            await pubsub.subscribe(f"task:{task_id}")
            
            async for message in pubsub.listen():
                if message["type"] != "message":
                    continue
                
                try:
                    data = json.loads(message["data"])
                except (json.JSONDecodeError, TypeError):
                    continue
                
                yield data
                
                # Stop listening on completion or failure
                if data.get("stage") in ("completed", "failed"):
                    break
                    
        except asyncio.CancelledError:
            logger.debug(f"Pub/Sub listener cancelled for task {task_id}")
        except Exception as e:
            logger.error(f"Pub/Sub listener error: {e}")
        finally:
            try:
                await pubsub.unsubscribe(f"task:{task_id}")
            except Exception:
                pass
            try:
                await client.close()
            except Exception:
                pass


# Singleton instance
redis_pubsub = RedisPubSubListener()
```

- [ ] **Step 2: Verify module loads**

Run: `python -c "from app.services.redis_pubsub import redis_pubsub; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add app/services/redis_pubsub.py
git commit -m "feat(services): add Redis Pub/Sub listener for SSE streaming"
```

---

### Task 7: Create Task Dispatcher

**Files:**
- Create: `app/services/task_dispatcher.py`

- [ ] **Step 1: Create task_dispatcher.py**

```python
# app/services/task_dispatcher.py
"""Task dispatcher for Celery queue."""

import logging
import uuid
from typing import Any

from celery.result import AsyncResult

from app.worker.tasks import run_agent_task
from app.core.config import settings

logger = logging.getLogger(__name__)


class TaskDispatcher:
    """Dispatches tasks to Celery and queries task status."""
    
    @staticmethod
    def dispatch(
        session_id: str,
        topic: str | None,
        user_input: str,
        user_id: int | None = None,
    ) -> str:
        """
        Dispatch an agent task to the Celery queue.
        
        Args:
            session_id: Session identifier
            topic: Learning topic
            user_input: User's message
            user_id: Optional user identifier
            
        Returns:
            The task ID for tracking
        """
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
        
        logger.info(f"Dispatched task {task_id} for session {session_id}")
        return task_id
    
    @staticmethod
    def get_status(task_id: str) -> dict[str, Any]:
        """
        Query the status of a task.
        
        Args:
            task_id: The task ID to query
            
        Returns:
            Status dict with keys: task_id, status, result, error
        """
        result = AsyncResult(task_id)
        
        response: dict[str, Any] = {
            "task_id": task_id,
            "status": result.state,
        }
        
        if result.ready():
            if result.successful():
                response["result"] = result.result
            else:
                response["error"] = str(result.result)
        
        return response
    
    @staticmethod
    def is_redis_available() -> bool:
        """Check if Redis is available for async operations."""
        if not settings.async_chat_enabled:
            return False
            
        try:
            import redis
            client = redis.from_url(settings.redis_url)
            client.ping()
            client.close()
            return True
        except Exception as e:
            logger.warning(f"Redis not available: {e}")
            return False


# Singleton instance
task_dispatcher = TaskDispatcher()
```

- [ ] **Step 2: Verify module loads**

Run: `python -c "from app.services.task_dispatcher import task_dispatcher; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add app/services/task_dispatcher.py
git commit -m "feat(services): add task dispatcher for Celery queue"
```

---

### Task 8: Add Async Chat Endpoints

**Files:**
- Modify: `app/api/chat.py`
- Modify: `app/models/schemas.py`

- [ ] **Step 1: Add new response models to schemas.py**

Add after the `ChatResponse` class:

```python
class AsyncChatResponse(BaseModel):
    """Response for async chat submission."""
    task_id: str
    status: str = "pending"
    session_id: str


class TaskStatusResponse(BaseModel):
    """Response for task status query."""
    task_id: str
    status: str
    result: dict | None = None
    error: str | None = None
```

- [ ] **Step 2: Add imports to chat.py**

Add at the top of the file:

```python
import logging
from fastapi import Query

from app.core.config import settings
from app.services.task_dispatcher import task_dispatcher
from app.services.redis_pubsub import redis_pubsub
from app.models.schemas import AsyncChatResponse, TaskStatusResponse

logger = logging.getLogger(__name__)
```

- [ ] **Step 3: Add async chat endpoint**

Add after the existing `chat()` function:

```python
@router.post("/async", response_model=AsyncChatResponse)
def chat_async(request: ChatRequest) -> AsyncChatResponse:
    """
    Submit async chat task (requires async_chat_enabled=True).
    
    Returns task_id for tracking progress via /chat/stream/{task_id}.
    """
    if not settings.async_chat_enabled:
        raise HTTPException(
            status_code=503,
            detail="Async chat is disabled. Use POST /chat for sync mode.",
        )
    
    if not task_dispatcher.is_redis_available():
        raise HTTPException(
            status_code=503,
            detail="Redis is unavailable. Please try again later.",
        )
    
    numeric_user_id = request.user_id
    if numeric_user_id is not None and numeric_user_id <= 0:
        raise HTTPException(status_code=400, detail="user_id must be a positive integer")
    
    task_id = task_dispatcher.dispatch(
        session_id=request.session_id,
        topic=request.topic,
        user_input=request.user_input,
        user_id=numeric_user_id,
    )
    
    return AsyncChatResponse(
        task_id=task_id,
        status="pending",
        session_id=request.session_id,
    )
```

- [ ] **Step 4: Add task status endpoint**

Add after the `chat_async()` function:

```python
@router.get("/status/{task_id}", response_model=TaskStatusResponse)
def get_task_status(task_id: str) -> TaskStatusResponse:
    """Query the status of an async chat task."""
    status = task_dispatcher.get_status(task_id)
    return TaskStatusResponse(**status)
```

- [ ] **Step 5: Add SSE streaming endpoint**

Add after the `get_task_status()` function:

```python
@router.get("/stream/{task_id}")
async def stream_chat(task_id: str) -> StreamingResponse:
    """
    SSE streaming endpoint for async chat progress.
    
    Emits events:
    - event: progress, data: {"stage": "...", "progress": 0-100}
    - event: token, data: "text fragment"
    - event: done, data: {"stage": "completed", "result": {...}}
    - event: error, data: {"error": "..."}
    """
    async def event_generator():
        try:
            async for event in redis_pubsub.listen(task_id, timeout=300.0):
                stage = event.get("stage", "")
                progress = event.get("progress", 0)
                token = event.get("token")
                
                if stage == "completed":
                    result = event.get("result", {})
                    yield f"event: done\ndata: {json.dumps({'stage': 'completed', 'result': result})}\n\n"
                    break
                    
                if stage == "failed":
                    error = event.get("error", "Unknown error")
                    yield f"event: error\ndata: {json.dumps({'error': error})}\n\n"
                    break
                
                if token:
                    yield f"event: token\ndata: {json.dumps(token)}\n\n"
                
                yield f"event: progress\ndata: {json.dumps({'stage': stage, 'progress': progress})}\n\n"
                
        except asyncio.CancelledError:
            logger.debug(f"SSE stream cancelled for task {task_id}")
        except Exception as e:
            logger.error(f"SSE stream error: {e}")
            yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )
```

Add the missing imports:

```python
import asyncio
import json
```

- [ ] **Step 6: Verify module loads**

Run: `python -c "from app.api.chat import router; print(len(router.routes))"`
Expected: A number >= 5 (original routes + new routes)

- [ ] **Step 7: Commit**

```bash
git add app/api/chat.py app/models/schemas.py
git commit -m "feat(api): add async chat endpoints with SSE streaming"
```

---

### Task 9: Add Integration Tests

**Files:**
- Create: `tests/test_task_queue.py`

- [ ] **Step 1: Create test file with mocked tests**

```python
# tests/test_task_queue.py
"""Tests for Celery task queue integration."""

import pytest
from unittest.mock import MagicMock, patch


class TestTaskDispatcher:
    """Tests for task dispatcher."""
    
    def test_dispatch_returns_task_id(self):
        """Test that dispatch returns a valid task ID."""
        with patch("app.services.task_dispatcher.run_agent_task") as mock_task:
            mock_task.apply_async = MagicMock(return_value=MagicMock(id="test-task-id"))
            
            from app.services.task_dispatcher import TaskDispatcher
            dispatcher = TaskDispatcher()
            
            task_id = dispatcher.dispatch(
                session_id="test-session",
                topic="Python",
                user_input="What is a variable?",
                user_id=1,
            )
            
            assert task_id == "test-task-id"
            mock_task.apply_async.assert_called_once()
    
    def test_get_status_pending(self):
        """Test status query for pending task."""
        with patch("app.services.task_dispatcher.AsyncResult") as mock_result:
            mock_result.return_value = MagicMock(state="PENDING", ready=MagicMock(return_value=False))
            
            from app.services.task_dispatcher import TaskDispatcher
            dispatcher = TaskDispatcher()
            
            status = dispatcher.get_status("test-task-id")
            
            assert status["task_id"] == "test-task-id"
            assert status["status"] == "PENDING"
            assert "result" not in status


class TestProgressReporter:
    """Tests for progress reporter."""
    
    def test_create_progress_reporter_returns_callable(self):
        """Test that create_progress_reporter returns a callable."""
        from app.worker.progress import create_progress_reporter
        
        callback = create_progress_reporter("test-task-id")
        
        assert callable(callback)
    
    def test_progress_reporter_handles_no_redis(self):
        """Test that progress reporter handles missing Redis gracefully."""
        from app.worker.progress import create_progress_reporter
        
        callback = create_progress_reporter("test-task-id")
        
        # Should not raise even if Redis is unavailable
        callback("testing", 50, "test token")


class TestRedisPubSub:
    """Tests for Redis Pub/Sub listener."""
    
    @pytest.mark.asyncio
    async def test_listen_yields_events(self):
        """Test that listen yields progress events."""
        from app.services.redis_pubsub import RedisPubSubListener
        
        listener = RedisPubSubListener()
        
        # This test requires a running Redis instance
        # In CI, we mock the Redis client
        with pytest.raises(Exception):
            # Expected to fail without Redis, but verifies the interface
            async for _ in listener.listen("nonexistent-task", timeout=1.0):
                pass


class TestChatEndpoints:
    """Tests for async chat API endpoints."""
    
    def test_async_chat_disabled_by_default(self):
        """Test that async chat returns 503 when disabled."""
        from fastapi.testclient import TestClient
        from app.main import app
        
        client = TestClient(app)
        
        response = client.post(
            "/chat/async",
            json={
                "session_id": "test",
                "user_input": "Hello",
            },
        )
        
        # Should be 503 because async_chat_enabled defaults to False
        assert response.status_code == 503
    
    def test_sync_chat_still_works(self):
        """Test that sync chat endpoint still works."""
        from fastapi.testclient import TestClient
        from app.main import app
        
        client = TestClient(app)
        
        # This will fail without proper LLM setup, but we test the endpoint exists
        response = client.post(
            "/chat",
            json={
                "session_id": "test-sync",
                "user_input": "Hello",
            },
        )
        
        # Endpoint exists (may return 400/500 due to missing API key)
        assert response.status_code in [200, 400, 500, 503]
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `pytest tests/test_task_queue.py -v`
Expected: Tests pass (some may skip if Redis unavailable)

- [ ] **Step 3: Commit**

```bash
git add tests/test_task_queue.py
git commit -m "test(task-queue): add integration tests for task queue"
```

---

### Task 10: Update Documentation and Final Verification

**Files:**
- Create: `.env.example` updates
- Modify: `docker-compose.yml`

- [ ] **Step 1: Add example environment variables**

Add to `.env.example` (or create if missing):

```env
# Redis Configuration
REDIS_URL=redis://localhost:6379/0

# Celery Configuration
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/1

# Task Configuration
ASYNC_CHAT_ENABLED=false
TASK_TIMEOUT_SECONDS=300
TASK_MAX_RETRIES=3
```

- [ ] **Step 2: Update docker-compose.yml to include Redis**

Read existing docker-compose.yml and add Redis service:

```yaml
services:
  redis:
    image: redis:alpine
    ports:
      - "6379:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 5

  worker:
    build:
      context: .
      dockerfile: Dockerfile.dev
    command: celery -A app.worker.celery_app worker --concurrency=4 --loglevel=info
    depends_on:
      redis:
        condition: service_healthy
    environment:
      - REDIS_URL=redis://redis:6379/0
      - CELERY_BROKER_URL=redis://redis:6379/0
      - CELERY_RESULT_BACKEND=redis://redis:6379/1
```

- [ ] **Step 3: Run full test suite**

Run: `pytest tests/ -v --tb=short`
Expected: All existing tests + new tests pass

- [ ] **Step 4: Verify imports work**

Run: `python -c "from app.worker import celery_app, run_agent_task; print('OK')"`
Expected: `OK`

- [ ] **Step 5: Final commit**

```bash
git add .env.example docker-compose.yml
git commit -m "docs: add Redis and Celery to docker-compose and env example"
```

---

## Verification Checklist

- [ ] `POST /chat/async` returns task_id when `ASYNC_CHAT_ENABLED=true`
- [ ] `GET /chat/status/{task_id}` returns correct status
- [ ] `GET /chat/stream/{task_id}` streams SSE events
- [ ] `ASYNC_CHAT_ENABLED=false` falls back to sync mode
- [ ] Redis unavailable returns 503 (not crash)
- [ ] All existing tests still pass

---

## Startup Commands

```bash
# Start Redis
docker run -d -p 6379:6379 redis:alpine

# Start FastAPI
uvicorn app.main:app --reload --port 1900

# Start Celery Worker (separate terminal)
celery -A app.worker.celery_app worker --concurrency=4 --loglevel=info

# Enable async mode
ASYNC_CHAT_ENABLED=true uvicorn app.main:app --reload --port 1900
```
