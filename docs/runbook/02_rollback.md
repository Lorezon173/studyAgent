# 回滚

## 场景 1：异步链路异常 → 关 flag 回退到同步

**触发**：Celery worker 卡住、Redis 失联、SSE token 中断。

**步骤**：

```bash
# 1. 把 ASYNC_GRAPH_ENABLED 设为 false（环境变量或 .env）
export ASYNC_GRAPH_ENABLED=false

# 2. 重启 uvicorn（Celery / Redis 不需要）
# 在 uvicorn 终端 Ctrl+C 后重启：
PYTHONPATH=. uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 1900

# 3. 验证同步路径（不会有 accepted 事件）
curl -N -X POST http://127.0.0.1:1900/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"session_id": "rollback-test", "topic": "math", "user_input": "test"}'
# 期望：event: token → event: stage → event: done（无 accepted）
```

回退后 `tests/test_chat_sync_fallback.py` 覆盖的同步路径完全可用。

## 场景 2：代码回滚到上一个 commit

**触发**：刚刚的 commit 造成回归（SLO 门禁失败 / 测试退化）。

**步骤**：

```bash
# 1. 看最近 commit
git log --oneline -5

# 2. 创建撤销 commit（推荐，不破坏历史）
git revert HEAD

# 3. 跑全量回归 + SLO 门禁验证回滚生效
PYTHONPATH=. DEBUG=false uv run pytest tests/ -q
uv run python -m slo.run_regression
```

> 不推荐 `git reset --hard`：会丢失 commit 历史，多人协作时几乎一定出事。
