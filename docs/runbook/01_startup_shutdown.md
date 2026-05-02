# 启停顺序

## 场景 1：本地开发（默认同步路径）

启动顺序：

```bash
# 1. 拉取依赖
uv sync

# 2. 启动 uvicorn（同步路径，不需要 Redis/Celery）
PYTHONPATH=. uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 1900
```

停止：`Ctrl+C` 即可。

## 场景 2：本地异步路径（验证 Phase 3a/3b）

启动顺序（必须按序）：

```bash
# 1. 启动 Redis（Docker 推荐）
docker run -d --name learning-agent-redis -p 6379:6379 redis:7-alpine

# 2. 验证 Redis 可达
docker exec learning-agent-redis redis-cli ping  # 期望 PONG

# 3. 启动 Celery worker（新终端）
PYTHONPATH=. ASYNC_GRAPH_ENABLED=true \
  uv run celery -A app.worker.celery_app worker --loglevel=info

# 4. 启动 uvicorn（再新终端）
PYTHONPATH=. ASYNC_GRAPH_ENABLED=true \
  uv run uvicorn app.main:app --host 127.0.0.1 --port 1900

# 5. 验证（新终端）
curl -N -X POST http://127.0.0.1:1900/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"session_id": "smoke-1", "topic": "math", "user_input": "什么是导数"}'
# 期望看到 event: accepted → event: token (多条) → event: stage → event: done
```

停止顺序（与启动相反）：

```bash
# 1. 停 uvicorn（Ctrl+C）
# 2. 停 Celery worker（Ctrl+C，等任务结束 ~5s）
# 3. 停 Redis
docker stop learning-agent-redis && docker rm learning-agent-redis
```
