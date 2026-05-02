# 容量治理

## 场景 1：CPU 满载（uvicorn 或 worker）

**症状**：响应慢、SLO completion_latency P95 > 15s。

**诊断**：

```bash
# Windows: 任务管理器
# Linux/macOS:
top -p $(pgrep -f uvicorn)
top -p $(pgrep -f celery)
```

**调优**（无 worker 主线 → 调 uvicorn）：

```bash
# 增加 uvicorn worker 数（默认 1，CPU 核心数 N → 设 N）
PYTHONPATH=. uv run uvicorn app.main:app --workers 4 --host 127.0.0.1 --port 1900
```

**调优**（有 worker → 调 Celery 并发）：

```bash
# Celery worker --concurrency 默认 = CPU 核心数；想限制：
uv run celery -A app.worker.celery_app worker --concurrency=2 --loglevel=info
```

## 场景 2：Redis OOM 或队列积压

**症状**：worker 任务等待时间长、Redis `INFO memory` 接近 maxmemory。

**诊断**：

```bash
# 看 Redis 内存
docker exec learning-agent-redis redis-cli INFO memory | grep used_memory_human

# 看 Celery 队列长度
docker exec learning-agent-redis redis-cli LLEN celery
```

**应对**：

```bash
# 1. 临时清队列（**会丢任务**，仅在确认积压无意义时用）
docker exec learning-agent-redis redis-cli DEL celery

# 2. 限制 Redis 内存上限 + 淘汰策略
docker run -d --name learning-agent-redis -p 6379:6379 redis:7-alpine \
  redis-server --maxmemory 256mb --maxmemory-policy allkeys-lru

# 3. 临时切回同步路径降压（见 02_rollback.md 场景 1）
```

## 队列优先级（暂不启用）

Phase 3d 不启用 Celery routing。未来如分"在线对话 / 离线分析"队列，参考：
- 在 `app/worker/celery_app.py` `task_routes` 配置
- 启动 worker 时 `-Q chat,offline` 指定监听队列
