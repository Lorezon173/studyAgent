# Phase 3 收尾设计：异步链路 + SLO 治理 + 可观测运营化 + Runbook

- 日期：2026-05-01
- 适用阶段：Phase 3（稳定化治理）收尾
- 上游基准：`docs/superpowers/specs/004-2026-04-20-rag-agent-framework-evolution-design.md`
- 当前主线分支：`feature/phase7-langfuse-v4-and-retry-ssot`
- 类型：架构设计 + 落地路线

---

## 1. 背景与目标

### 1.1 当前状态（截至 2026-05-01）

1. Phase 1（RAG 质量冲刺）已交付。
2. Phase 2（编排增强）已交付。
3. Phase 7（约定治理 + Langfuse v4 适配）已交付：`RetryKey` 类型化、`RETRY_POLICIES_MAP` 单一来源、`NodeRegistry.add_to_graph` 节点级 Span 包装、`truncate_payload` 复用、295 PASS / 19 既有失败基线。
4. Celery + Redis 任务队列主线代码**未实现**。`app/worker/celery_app.py`、`app/services/task_dispatcher.py`、`app/services/redis_pubsub.py` 在 `plans/archive/` 中存有历史方案但未落地。
5. 目前 chat 流式接口（`app/api/chat.py`）使用 `Queue + Thread` 在同进程内伪异步，HTTP 长连接阻塞整条 graph_v2 链路。
6. 仓库无 `.github/workflows/`，无 CI 流水线。

### 1.2 顶层 spec 第 12 节剩余未交付项

1. SLO 阈值固化与发布守门自动化。
2. 容量治理与队列优先级调优（先决定异步链路架构走向）。
3. 问题定位看板与告警联动。
4. 全量发布评审与运维手册冻结。

### 1.3 本 spec 目标

在不替换 LangGraph + FastAPI 主干的前提下，**一次性收尾**上述 4 项遗留工作：

1. 引入 Celery + Redis 异步主线，复用现有 SSE 流式 UX。
2. 建立可执行的 SLO 门禁（指标定义 + 阈值文件 + 回归集脚本）。
3. 将 Langfuse trace 能力升级为可运营的看板 + 告警 + on-call 文档。
4. 冻结轻量版 runbook（启停 / 回滚 / 容量 / 故障 / 发布检查）。

### 1.4 非目标

1. 多 Agent 协作框架（顶层 spec §11 已声明）。
2. 真实云上部署（Slack / GitHub Actions / 多节点扩缩容）。仅预留钩子位。
3. 看板自动部署（Langfuse SDK 暂无稳定面板创建 API）。
4. 端到端 SLA 合同（无外部付费用户）。
5. RAG 质量进一步提升（属下一轮架构评估）。
6. 异步任务的多用户配额、计费、租户隔离。

---

## 2. 运营上下文

1. 形态：单人学习项目，运行在本地 / 单机 Docker。
2. SLO 用途：**自律阈值与回归门禁**，不用于呼叫 on-call。
3. 告警目的：开发期发现劣化，写本地日志 + Langfuse 内置告警 + 桌面通知（可选）。
4. Runbook 用途：自我故障复盘 + 学习生产模式 + 上云时直接复用。
5. 全异步路线选定的原因：架构清晰度与学习价值，不是为生产扩展。

---

## 3. 选型结论

### 3.1 候选方案

| 方案 | 描述 | 是否选用 |
|---|---|---|
| A | 异步先打底（Celery + Redis + SSE 桥），并行补 SLO / 看板 / runbook | **选用** |
| B | REST async + polling，放弃现有 SSE | 否 |
| C | 仅建 Celery 骨架，chat 仍 `.get(timeout)` 同步等待 | 否 |

### 3.2 选用 A 的理由

1. 复用现有 `app/api/chat.py` 的 SSE+Queue+Thread 模式，前端零改动。
2. SLO 升级与异步落地同步发生，避免阈值反复调。
3. 单人本地仍可学到生产模式（worker 进程隔离、Redis broker、pub/sub 桥）。
4. Feature flag 保留同步回退路径，支持灰度。

---

## 4. 架构骨架

### 4.1 总览

```
┌──────────────────────────────────────────────────────────────────────┐
│                      Web Process (FastAPI / uvicorn)                 │
│                                                                      │
│  POST /chat/stream                                                   │
│   ├─ open SSE connection                                             │
│   ├─ task_dispatcher.dispatch(payload) -> celery task -> task_id     │
│   └─ redis_pubsub.subscribe(channel=f"chat:{task_id}")               │
│        ↓ event loop forwards Redis msgs to SSE                       │
│        emits: event=accepted | progress | token | stage | done|error │
└──────────────────────────────────────────────────────────────────────┘
                            ↑                    ↓
                    Redis Pub/Sub          Celery broker (Redis)
                            ↑                    ↓
┌──────────────────────────────────────────────────────────────────────┐
│                       Worker Process (Celery)                        │
│                                                                      │
│  @celery_app.task                                                    │
│  def run_chat_graph(payload):                                        │
│   ├─ pubsub.publish(channel, "accepted")                             │
│   ├─ agent_service.run(..., progress_sink=publish_to_channel)        │
│   │     ↑ graph_v2 节点级 span 已存在(Phase 7)，新增 progress hook   │
│   └─ pubsub.publish(channel, "done")                                 │
└──────────────────────────────────────────────────────────────────────┘
```

### 4.2 关键决策

1. Worker 与 Web 进程通过 Redis 解耦，但 SSE 长连接在 Web 进程保留。用户感知零变化。
2. Token 来源从同进程 Thread 换成同主机的 worker 进程。
3. `@node` 装饰器 / `NodeRegistry` / `graph_v2` 契约不动。Phase 7 的 SSOT 与 Span 包装在 worker 进程同样生效。

---

## 5. 组件清单

| 文件 | 类型 | 责任 |
|---|---|---|
| `app/worker/__init__.py` | 新增 | worker 包入口 |
| `app/worker/celery_app.py` | 新增 | Celery 实例 + Redis broker / backend 配置 + 任务注册 |
| `app/worker/tasks.py` | 新增 | `run_chat_graph(payload)` 任务定义 |
| `app/services/task_dispatcher.py` | 新增 | 封装 `task.delay()`，根据 flag 分流 |
| `app/services/redis_pubsub.py` | 新增 | 极简发布订阅封装（publish / subscribe + 超时） |
| `app/services/agent_service.py` | 修改 | `run(..., progress_sink=None)` 增加进度回调，不破坏现有调用 |
| `app/api/chat.py` | 修改 | `/chat/stream` 在 flag on 时通过 dispatcher + pubsub 桥接 |
| `app/config.py` | 修改 | 新增 `ASYNC_GRAPH_ENABLED`、`REDIS_URL`、`CELERY_TASK_TIMEOUT_S` |
| `app/monitoring/alert_evaluator.py` | 新增 | 周期性读 SLI + 比对告警规则 + 写告警日志 |
| `slo/thresholds.yaml` | 新增 | 7 个 SLI 阈值，版本受控 |
| `slo/regression_set.yaml` | 新增 | 12-15 个固定回归问题（4 类） |
| `slo/run_regression.py` | 新增 | 跑回归 → 抓 trace → 算 SLI → 比对阈值 → 退出码 |
| `slo/alert_rules.yaml` | 新增 | 告警分级规则 |
| `Makefile` | 修改 / 新增 | `make slo-check` target |
| `docs/observability/dashboards/*.json` | 新增 | 4 个 Langfuse dashboard 配置导出 |
| `docs/runbook/*.md` | 新增 | 6 个 runbook 文档 |

---

## 6. 数据流（端到端时序）

```
client                 web               redis-pubsub       worker (celery)
  │                     │                     │                   │
  ├── POST /chat/stream►│                     │                   │
  │                     ├── dispatch ───────►│                   │
  │                     │                     ├── enqueue ──────►│
  │                     ├── subscribe(ch:tid)│                   │
  │                     │                     │                   ├── publish accepted
  │ ◄─ SSE accepted ────┤ ◄─── pubsub msg ───┤ ◄─────────────────┤
  │                     │                     │                   ├── agent_service.run
  │                     │                     │                   ├── publish progress*
  │ ◄─ SSE progress ────┤ ◄─── pubsub msg ───┤ ◄─────────────────┤
  │                     │                     │                   ├── publish token*
  │ ◄─ SSE token ───────┤ ◄─── pubsub msg ───┤ ◄─────────────────┤
  │                     │                     │                   ├── publish done
  │ ◄─ SSE done ────────┤ ◄─── pubsub msg ───┤ ◄─────────────────┤
  │ × SSE close          │                     │                   │
```

**事件类型**（在 SSE `event:` 头部）：

1. `accepted` — task_id 已入队，用于度量 `accept_latency_ms`
2. `progress` — 节点级进度（如 `retrieval:hits=12`）
3. `token` — LLM 流式 token，用于度量 `first_token_latency_ms`
4. `stage` — 阶段切换（A / B / C 学习闭环）
5. `done` — 任务完成，用于度量 `completion_latency_ms`
6. `error` — 失败，带分类码（复用 `app/services/error_classifier.py`）

---

## 7. Feature Flag 与降级

### 7.1 配置项

```python
# app/config.py
ASYNC_GRAPH_ENABLED: bool   # 默认 false
REDIS_URL: str              # 默认 redis://localhost:6379/0
CELERY_TASK_TIMEOUT_S: int  # 默认 60
```

### 7.2 降级矩阵

| `ASYNC_GRAPH_ENABLED` | Redis 可达 | 行为 |
|---|---|---|
| `false` | — | 现有同步 SSE + Thread + Queue 路径，零变化 |
| `true` | 是 | 全异步：dispatcher → celery worker → redis pubsub → SSE |
| `true` | 否 | 启动期 health check 失败，**fail loudly + 拒绝启动** |

### 7.3 调用方契约

`task_dispatcher.dispatch(payload)` 内部根据 flag 分流，`app/api/chat.py` 不感知架构差异。回退路径必须有专门测试覆盖。

---

## 8. SLO 体系

### 8.1 SLI 定义

所有 SLI 从 Langfuse trace 派生（已在 Phase 7 接入），不再独立写埋点。

| SLI 名 | 计算方式 | 数据来源 |
|---|---|---|
| `accept_latency_ms` | `accepted` span timestamp - request_received timestamp | trace 根 span |
| `first_token_latency_ms` | 第一个 `token` span - request_received | trace span 序列 |
| `completion_latency_ms` | `done` span - request_received | trace 根 span end |
| `task_success_rate` | done count / (done + error) count | trace status |
| `retry_recovery_rate` | retry 后成功 trace / 总 retry trace | retry policy span 元数据 |
| `citation_coverage` | 含 `citations` 字段的 trace / 含 RAG 的 trace | output 字段 |
| `low_evidence_disclaim_rate` | `rag_low_evidence=true` 且声明已下达 trace / 应声明 trace | `rag_low_evidence` + 回答模板分类 |

### 8.2 SLO 阈值（v1，单人本地基线）

| 类别 | 指标 | 阈值 |
|---|---|---|
| 时延 | P95 `accept_latency_ms` | ≤ 500 |
| 时延 | P95 `first_token_latency_ms` | ≤ 3000 |
| 时延 | P95 `completion_latency_ms` | ≤ 15000 |
| 稳定 | `task_success_rate` | ≥ 0.97 |
| 稳定 | `retry_recovery_rate` | ≥ 0.70 |
| 质量 | `citation_coverage` | ≥ 0.85 |
| 质量 | `low_evidence_disclaim_rate` | ≥ 0.95 |

### 8.3 与上游 spec §9 的差异声明

顶层 spec §9 在同步语境下规定：

1. P95 首字节 ≤ 2.5s
2. P95 总时延 ≤ 12s
3. 任务成功率 ≥ 99%
4. 重试后恢复率 ≥ 80%
5. 引用覆盖率 ≥ 85%
6. 低证据声明覆盖率 ≥ 95%

异步化后调整：

1. 首字节 ≤ 2.5s 拆为 `accept ≤ 0.5s` + `first_token ≤ 3.0s`，新增 0.5s 桥接预算。
2. 总时延 ≤ 12s 调整为 `completion ≤ 15s`，预留异步开销。
3. 成功率从 99% 调整为 97%，对齐异步链路真实失败模式（broker 抖动、worker 重启）。
4. 重试恢复率从 80% 调整为 70%，与新失败模式校准。
5. 质量两项保持不变。

阈值文件：`slo/thresholds.yaml`，每次修改需 commit。

### 8.4 回归门禁

1. `slo/regression_set.yaml`：12-15 个代表性问题，分 4 类（事实 / 对比 / 总结 / 规划）。
2. `slo/run_regression.py`：跑全部问题 → 收集 trace → 聚合 SLI → 与 thresholds.yaml 比对。
3. `Makefile` target `make slo-check`：本地一键执行。
4. 退出码：达标 0 / 违反 1（便于挂 pre-push hook 或未来 CI）。

### 8.5 CI 钩子位（云上预留）

仓库当前无 `.github/workflows/`。本 spec 不引入 CI 文件，但 `make slo-check` 退出码语义已对齐 GitHub Actions，未来加 `actions/checkout + setup-python + make slo-check` 三步即可。

---

## 9. 可观测运营化

### 9.1 Langfuse 看板

1. **时延面板**：三档时延 P50/P95/P99 时序，红线为 SLO 阈值。
2. **稳定面板**：成功率、重试恢复率、错误码分布（按 `error_classifier` 分类）。
3. **质量面板**：引用覆盖率、低证据声明率，按 `query_mode` 切片。
4. **链路面板**：节点级 span 耗时占比（complement Phase 7 已有的 span 包装）。

不写自动化部署面板的脚本（Langfuse SDK 限制）。Dashboard 配置导出为 JSON 存到 `docs/observability/dashboards/`，按文档手动导入。

### 9.2 告警规则

| 严重度 | 触发条件 | 通知方式 |
|---|---|---|
| INFO | 任一 SLI 接近阈值 90% | 写到 `logs/slo_warn.log`（按日轮转） |
| WARN | SLI 连续 5 分钟超阈值 | Langfuse 内置 alert + 本地日志 |
| CRIT | `task_success_rate < 0.90` | 同上 + `notify-send` 桌面通知（可选） |

告警规则文件：`slo/alert_rules.yaml`，与阈值分离。云上钩子位：`alert_rules.yaml` 已结构化，加一个 `webhook_url` 字段就能切到 Slack。

### 9.3 on-call 响应文档

`docs/runbook/oncall_response.md`，3 个场景：

1. 看板红了（SLI 超阈值）→ 按"降级排查矩阵"操作。
2. 全量回归门禁失败 → 不允许 release，按错误码定位。
3. 异步链路异常（worker 卡住、Redis 失联）→ 切 `ASYNC_GRAPH_ENABLED=false`。

---

## 10. Runbook（运维手册）

`docs/runbook/` 目录新建，包含 6 份运维文档 + 1 份 on-call 响应文档（on-call 文档详见 §9.3，物理位置同目录）：

| 文件 | 内容 |
|---|---|
| `00_index.md` | 快速索引 + 决策树 |
| `01_startup_shutdown.md` | 启动 / 停止顺序：Redis → Celery worker → uvicorn |
| `02_rollback.md` | 回滚步骤：feature flag 关闭 → 进程重启 → 验证 |
| `03_capacity.md` | worker 并发 / 队列优先级 / Redis 容量预案 |
| `04_troubleshooting.md` | 5 类典型故障：worker 卡住 / 队列积压 / broker 失联 / SSE 断流 / LLM 限流 |
| `05_release_checklist.md` | 发布检查清单：全量回归、SLO 门禁、阈值差比、变更影响声明 |
| `oncall_response.md` | on-call 响应（§9.3 定义的 3 个场景） |

**冻结口径**：Phase 3 收尾时，6 份 runbook 文档 + 1 份 on-call 文档结构化完成；其中 6 份 runbook 每份至少 2 个具体场景，on-call 文档至少 3 个场景。后续按事故迭代，但不在 Phase 3 范围内。

---

## 11. 子阶段拆分

每个子阶段对应一份独立 plan（由 writing-plans 流程产出），可分别执行。

### 11.1 子阶段 3a — 异步骨架

**目标**：Celery + Redis + dispatcher + pubsub 接入，默认关闭，与同步路径并存。

**交付**：

1. `app/worker/celery_app.py` — Celery 实例，从 `app/config.py` 读 `REDIS_URL`。
2. `app/worker/tasks.py` — 注册 `run_chat_graph` 占位实现。
3. `app/services/redis_pubsub.py` — `publish` / `subscribe` + 超时。
4. `app/services/task_dispatcher.py` — 根据 flag 分流。
5. `app/config.py` — 新增 3 个开关。
6. `tests/test_worker_celery_app.py` — 实例化、任务注册可见。
7. `tests/test_redis_pubsub.py` — pub/sub 收发（用 `fakeredis` 或本地 Redis）。
8. `tests/test_task_dispatcher.py` — flag on/off 分流验证。

**门禁**：全量回归 ≥ 295 PASS（不退化），新增测试全绿。

### 11.2 子阶段 3b — chat API 切到异步路径

**目标**：`/chat/stream` 在 `ASYNC_GRAPH_ENABLED=true` 时走 worker，UX 不变。

**交付**：

1. `app/services/agent_service.py` — `run(..., progress_sink=None)` 增加进度回调。
2. `app/worker/tasks.py` — `run_chat_graph` 调用 `agent_service.run`，进度通过 pubsub 发出。
3. `app/api/chat.py` — `event_generator` 在 flag on 时改为 redis 订阅；flag off 走旧路径。
4. `tests/test_chat_async_api.py` — 端到端：mock worker，验证 SSE 序列。
5. `tests/test_chat_sync_fallback.py` — flag off 旧路径不变。

**门禁**：

1. 全量回归不退化。
2. 同步 / 异步两条路径 e2e 都绿。
3. 手动验证：本地启动 Redis + worker → curl `/chat/stream` → 看到 token 流式输出。

### 11.3 子阶段 3c — SLO 门禁

**目标**：可量化、可执行的 SLO 门禁脚本。

**交付**：

1. `slo/thresholds.yaml` — 7 个 SLI 阈值（§8.2）。
2. `slo/regression_set.yaml` — 12-15 个回归问题。
3. `slo/run_regression.py` — 聚合 + 比对 + 退出码。
4. `Makefile` — `make slo-check` target。
5. `tests/test_slo_threshold_loader.py` — 阈值 / 规则文件解析正确。
6. `tests/test_slo_aggregator.py` — SLI 聚合逻辑（mock trace 数据）。

**门禁**：

1. `make slo-check` 在当前主线代码上达标，建立 v1 基线。
2. 故意调严阈值 / 注入劣化回归 → 脚本退出码 1（验证门禁有效）。

### 11.4 子阶段 3d — 看板 / 告警 / runbook

**目标**：将 trace 能力升级为可运营。

**交付**：

1. `docs/observability/dashboards/01_latency.json` 等 4 个 Langfuse dashboard JSON。
2. `slo/alert_rules.yaml` — 告警规则。
3. `app/monitoring/alert_evaluator.py` — 周期性读 SLI + 比对规则 + 写告警日志。
4. `docs/runbook/00_index.md` 至 `05_release_checklist.md` — 6 个文档。
5. `docs/runbook/oncall_response.md` — 3 个响应场景。
6. `tests/test_alert_evaluator.py` — 阈值触发分级正确。

**门禁**：

1. 每个 runbook 文件至少 2 个具体场景。
2. 告警规则覆盖 SLO 阈值表 100%。
3. README 顶部增加"看板入口 + runbook 入口"链接。

---

## 12. 验收标准（spec 整体）

| 类别 | 项 | 阈值 / 形态 |
|---|---|---|
| 功能 | 异步骨架可灰度 | flag on/off 行为切换，回退路径有测试 |
| 功能 | chat SSE UX 不变 | flag on/off 时事件序列一致（除 `accepted` 是新增） |
| 质量 | 全量回归 | ≥ 295 PASS（不低于 Phase 7 基线），子阶段新增测试全绿 |
| 质量 | SLO v1 基线 | `make slo-check` 通过，所有 7 个指标达标 |
| 文档 | runbook 冻结 | 6 份 runbook（每份 ≥ 2 个场景） + 1 份 on-call 文档（≥ 3 个场景）结构化完成 |
| 文档 | 看板归档 | 4 个 dashboard JSON 入仓 + README 链接可见 |
| 治理 | 阈值调整变更 | 本 spec §8.3 已显式声明与顶层 spec §9 的差异 |

---

## 13. 风险与应对

| 风险 | 影响 | 应对 |
|---|---|---|
| Redis pub/sub 消息丢失（订阅前 publish） | 客户端漏 `accepted` 事件 | dispatcher 在 publish 前先确认订阅就绪（小握手），或 dispatch 后再 publish |
| Celery worker 启动时 import graph 失败 | worker 起不来 | 启动期 health check 任务，启停脚本 wait-for-worker |
| SSE 长连接被反向代理关闭 | token 中断 | runbook 注明 keepalive 配置；本地不涉及，云上钩子位 |
| trace 字段不全导致 SLI 算不出 | SLO 门禁误报 | aggregator 对缺失字段显式分类（`unknown`），不静默跳过 |
| 单人本地无 Redis 时开发受阻 | 开发体验下降 | flag off + 同步路径完全保留 |
| 阈值过严导致门禁卡 release | 推进速度下降 | v1 阈值用历史 P95 + 20% margin；3d 阶段先空跑 1 周校准 |

---

## 14. 测试策略

### 14.1 单元测试（每个新模块）

1. `celery_app` 实例化、任务名单可见。
2. `redis_pubsub` 收发、超时。
3. `task_dispatcher` flag 分流。
4. `slo` aggregator 计算（fixture trace 数据）。
5. `alert_evaluator` 分级触发。

### 14.2 集成测试

1. `test_chat_async_api.py` — flag on，mock celery 同步执行，验证 SSE 事件序列。
2. `test_chat_sync_fallback.py` — flag off，旧路径不变。
3. `test_slo_regression_e2e.py` — fixture 跑全 regression set，断言达标。

### 14.3 手动验证（runbook 内提供脚本）

1. 启动 Redis + Celery worker → curl `/chat/stream` → 浏览器看流式 token。
2. 关闭 Celery → 切 flag off → 验证回退。
3. 故意注入慢节点 → 看板红 → 告警触发。

---

## 15. 与上游文档的关系

1. 本 spec 是顶层 spec `004-2026-04-20-rag-agent-framework-evolution-design.md` 第 12 节"未完成"4 项的收尾。
2. 落地后顶层 spec 第 12 节"Phase 3 进行中"应转为"Phase 3 已交付"。
3. 子阶段 3a/3b/3c/3d 各产出一份独立 plan 文件（编号在 `plans/INDEX.md` 续号），执行日志按现有 Phase 7 模式追加。
4. SLO 阈值差异（§8.3）需同步反向回写到顶层 spec §9，作为最终交付前的最后一步。

---

## 16. 落地路线总图

```
W1   ┌─ 3a 异步骨架（celery_app / tasks 占位 / pubsub / dispatcher / config）
     │   └─ 单测 + flag off 全量回归不退化
W2   ├─ 3b chat 切异步路径（agent_service progress_sink / chat.py 切换）
     │   └─ 双路径 e2e 测试 + 手动验证
W3   ├─ 3c SLO 门禁（thresholds / regression_set / aggregator / make slo-check）
     │   └─ v1 基线达标 + 注入劣化验证退出码
W4   └─ 3d 看板 / 告警 / runbook（dashboard JSON / alert_rules / runbook 6 文 / on-call）
         └─ 全量验收 + 顶层 spec §9 阈值同步回写
```

预算：4 周（单人本地，全职近似估算）。
