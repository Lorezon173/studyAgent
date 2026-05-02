# 故障排查（5 类典型）

## 1. Worker 卡住（任务长时间不完成）

**症状**：`/chat/stream` 收到 `accepted` 后无 token / done 事件。

**排查**：

```bash
# 1. 看 worker 日志最近一条任务
# 在 Celery worker 终端检查输出，是否卡在某个节点

# 2. 看任务状态（如果 Celery 启用了 result backend）
uv run python -c "
from app.worker.celery_app import celery_app
i = celery_app.control.inspect()
print('active:', i.active())
print('reserved:', i.reserved())
"

# 3. 强制结束 worker（任务会被 Celery 标记为 failed）
# Celery worker 终端 Ctrl+C
```

**修复后**：跑 `uv run python -m slo.run_regression` 验证。

## 2. 队列积压

**症状**：worker active task 数量 ≈ concurrency，reserved 队列持续增长。

**步骤**：见 `03_capacity.md` 场景 2。

## 3. Broker（Redis）失联

**症状**：worker 启动报错 `redis.exceptions.ConnectionError`。

**排查**：

```bash
# 1. Redis 容器是否在跑
docker ps | grep redis

# 2. Redis 是否监听 6379
docker exec learning-agent-redis redis-cli ping

# 3. REDIS_URL 是否正确
echo $REDIS_URL  # 期望 redis://localhost:6379/0
```

**应急**：切回同步路径（见 `02_rollback.md` 场景 1）。

## 4. SSE 断流（chat/stream 中途断开）

**症状**：浏览器 / curl 在收到部分 token 后连接关闭。

**排查**：

- 异步路径下 → 检查 `pubsub.subscribe` 超时（`celery_task_timeout_s + 5`）
- 同步路径下 → 检查 `agent_service.run` 是否抛异常（看 uvicorn 日志）
- 反向代理（如 nginx）→ 确认 keepalive、proxy_read_timeout

**临时绕过**：用 `POST /chat`（非流式）替代 `/chat/stream`。

## 5. LLM 限流 / 超时

**症状**：`agent_service.run` 抛 `openai.RateLimitError` 或 `openai.APITimeoutError`。

**应对**：

- 检查 `LLM_TIMEOUT_SECONDS`（默认 30，必要时调到 60）
- 检查 `LLM_MAX_RETRIES`（默认 2）
- Phase 7 的 `RETRY_POLICIES_MAP` 已经按节点配置 retry，限流时通常会自动重试 1-2 次
- 长期：在 `app/services/llm.py` 加 token bucket 限流（不在本 phase 范围）
