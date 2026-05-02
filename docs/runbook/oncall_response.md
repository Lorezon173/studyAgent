# On-Call 响应

本文档定义 3 个值班响应场景。单人本地形态下 on-call 即"开发者自己"，但保留响应矩阵以便上云后切到 webhook 通知。

## 场景 1：看板红了（SLI 超阈值）

**告警来源**：Langfuse dashboard 红线 / `logs/slo_alerts.log` WARN 或 CRIT 行。

**响应步骤**：

1. 看 `logs/slo_alerts.log` 最近 10 行，定位红线 SLI 名
2. 跑 `uv run python -m slo.run_regression` 确认 SLI 当前值
3. 按 SLI 类型查 runbook：
   - `*_latency_ms` 超阈值 → `03_capacity.md`
   - `task_success_rate` 跌 → `04_troubleshooting.md`
   - `citation_coverage` / `low_evidence_disclaim_rate` 跌 → 对照 git log 看是否最近改了 RAG 链路
4. 修复后再跑 SLO check 验证恢复

**升级条件**：CRIT alert（task_success_rate < 0.90）连续 2 次出现 → 立即关 ASYNC_GRAPH_ENABLED 切同步路径。

## 场景 2：全量回归门禁失败（PR 阻塞）

**告警来源**：PR pipeline 失败 / `pytest tests/ -q` failed > 19。

**响应步骤**：

1. 对比当前失败列表 vs 既有失败基线（Phase 7 起 19 个固定失败）
2. 如果失败 > 19，找出**新增**的失败：
   ```bash
   PYTHONPATH=. DEBUG=false uv run pytest tests/ -q 2>&1 | grep FAILED > /tmp/now.txt
   git stash && PYTHONPATH=. DEBUG=false uv run pytest tests/ -q 2>&1 | grep FAILED > /tmp/before.txt
   git stash pop
   diff /tmp/before.txt /tmp/now.txt
   ```
3. 按错误码定位：
   - `TypeError: ... got an unexpected keyword argument` → 调用方与被调方签名不匹配（最近改了 service 层 API？）
   - `ModuleNotFoundError` → 漏 commit 文件 / 漏更新 .gitignore 白名单
   - `AssertionError` → 业务逻辑变化导致期望值过期，需双向确认
4. 不允许 merge 前用 `git revert` 撤销引入失败的 commit；或在 PR 中提供修复 commit

## 场景 3：异步链路异常（worker 卡住 / Redis 失联）

**告警来源**：手动观察（用户报告）/ Celery worker 退出。

**响应步骤**（按顺序，能快就快）：

1. **立即降级**：把 `ASYNC_GRAPH_ENABLED` 设为 false，重启 uvicorn（见 `02_rollback.md` 场景 1）
2. **取证**：在切之前抓一份 Celery worker 日志、Redis `INFO`、最近 5 条 `chat:*` pubsub 消息
3. **修复**：参考 `04_troubleshooting.md` 第 1/3 节
4. **回归**：修复后切 `ASYNC_GRAPH_ENABLED=true`，跑：
   ```bash
   uv run pytest tests/test_chat_async_api.py tests/test_worker_tasks_real_graph.py -q
   ```
5. **复盘**：把根因写到本文件下方"已知 incident"段（首次 incident 时新建）

## 升级矩阵（云上预留）

| 严重度 | 当前响应 | 上云后扩展 |
|---|---|---|
| INFO | 仅记日志 | 仍仅记日志 |
| WARN | 看日志手动检查 | 推 Slack `#slo-warn` 频道 |
| CRIT | 立即降级 | 推 Slack `#slo-crit` + 寻呼 on-call |

切换方式：在 `slo/alert_rules.yaml` 启用 `webhook_url` 字段（v1 已注释占位）。
