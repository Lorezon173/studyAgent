# plans 文档分类对账（2026-05-01）

## 0) 最顶层规划文档（主路线基准）

- **顶层规划文档**：`docs/superpowers/specs/004-2026-04-20-rag-agent-framework-evolution-design.md`
- **定位**：该文档定义了 12 周主路线（Phase 1/2/3）与验收口径；`plans/` 下各阶段执行计划应视为其落地分解。

### 按顶层规划修正后的当前进度

| 顶层阶段 | 当前状态 | 依据 |
|---|---|---|
| Phase 1（RAG质量冲刺） | 已完成 | `005` 与 spec Progress Note |
| Phase 2（编排增强） | 已完成 | `007/008/009/010/011` 与 spec Progress Note |
| Phase 3（稳定化治理） | 进行中 | `013/014` 覆盖了部分治理项，但 SLO门禁/容量治理/运维手册未闭环 |

### 剩余工作（按顶层文档 Phase 3）

1. 固化 SLO 阈值并接入发布守门（质量、稳定、时延三类门禁）
2. 完成容量治理与队列优先级方案（先明确异步链路架构是否回归主线）
3. 建立统一问题定位看板与告警联动（从“可观测”升级到“可运营”）
4. 冻结发布评审流程与运维手册（runbook/回滚预案/值班响应）

---

## 1) 使用规则（先看这个）

1. **当前主线以 Phase 文档为准**：`005 → 007 → 008 → 009 → 010 → 011 → 013`
2. **执行结果以执行日志为准**：`012`（Phase 6）、`014`（Phase 7）
3. **历史专题文档仅作参考**，不作为当前实施入口

---

## 2) 分类总表

| 文档 | 分类 | 状态 | 对账结论 | 建议动作 |
|---|---|---|---|---|
| `005-2026-04-20-rag-agent-framework-evolution-phase1.md` | 主线阶段计划 | 已交付 | 文档内有 `Progress Note (Phase 1 Delivered)` | 保留 |
| `007-2026-04-21-rag-agent-framework-evolution-phase2-plan.md` | 主线阶段计划 | 已交付 | 文档内有 `Phase 2 已交付 ✅` | 保留 |
| `008-2026-04-27-rag-agent-framework-evolution-phase3-plan.md` | 主线阶段计划 | 已交付 | 有交付记录（`165 PASS / 0 FAIL`） | 保留 |
| `009-2026-04-28-rag-agent-framework-evolution-phase4-plan.md` | 主线阶段计划 | 已交付 | 有交付记录（`174 PASS / 0 FAIL`） | 保留 |
| `010-2026-04-28-rag-agent-framework-evolution-phase5-plan.md` | 主线阶段计划 | 已交付 | 有交付记录（`201 PASS / 0 FAIL`） | 保留 |
| `011-2026-04-28-rag-agent-framework-evolution-phase6-plan.md` | 主线阶段计划 | 已交付 | 文件内追加了执行记录（2026-04-29） | 保留 |
| `013-2026-05-01-rag-agent-framework-evolution-phase7-plan.md` | 主线阶段计划 | 已执行 | 与 `014` 对应；作为当前阶段计划入口 | 保留（当前主入口） |
| `012-2026-04-29-phase6-execution-log.md` | 主线执行日志 | 已完成 | 记录了 Phase 6 执行细节与基线 | 保留 |
| `014-2026-05-01-phase7-execution-log.md` | 主线执行日志 | 已完成 | 记录 Phase 7“先对账后补缺”执行结果 | 保留（当前结果入口） |
| `phase6-safe.md` | 整理版文档 | 已整理 | 为 Phase 6 的格式重整版，不是独立阶段计划 | 保留（辅助阅读） |
| `archive/001-2026-04-15-rag-agent-decision-orchestrator.md` | 历史专题计划 | 已归档 | 代码对账未发现 `app/services/decision_orchestrator.py` | 归档完成 |
| `archive/2026-04-15-rag-agent-decision-orchestrator.md` | 历史专题计划（扩展版） | 已归档 | 与 `001` 同主题，内容更长 | 归档完成 |
| `archive/003-2026-04-17-task-queue-concurrency.md` | 历史专题计划（含落地记录） | 已归档 | 文档称已完成，但当前代码无 `app/worker/*`、`task_dispatcher.py` | 归档完成 |
| `archive/004-2026-04-18-task-queue-concurrency.md` | 历史专题计划（详细版） | 已归档 | 与 `003` 同主题，当前仓库无对应实现文件 | 归档完成 |
| `2026-04-17-langgraph-core-refactoring.md` | 历史基座计划 | 参考价值高 | 后续 Phase 2~7 已部分吸收其思想 | 保留为“架构参考” |
| `2026-04-17-langfuse-observability.md` | 历史专题计划 | 已被 Phase 7 吸收 | Langfuse 能力已由 `013/014` 形成新基线 | 保留为“历史方案” |

---

## 3) 对账证据（代码侧）

以下关键文件存在性检查结果（2026-05-01）：

- `app/services/decision_orchestrator.py` => `False`
- `app/worker/celery_app.py` => `False`
- `app/services/task_dispatcher.py` => `False`
- `app/services/redis_pubsub.py` => `False`
- `tests/test_chat_async_api.py` => `False`
- `tests/test_task_dispatcher.py` => `False`
- `tests/test_redis_pubsub.py` => `False`
- `app/agent/node_registry.py` => `True`
- `app/monitoring/langfuse_client.py` => `True`
- `tests/test_node_registry_span.py` => `True`

说明：

1. `003/004/001/2026-04-15` 代表的专题线索，在当前代码树中不是主线落地状态，已迁入 `archive/`；
2. `013/014` 代表的 Phase 7 主线能力在当前代码中可对上关键实现文件。

---

## 4) 目录整理决议（已执行）

已完成“**第一批物理归档整理**”：  
`plans/archive/` 已创建，并已迁移以下 4 份文档：

1. `001-2026-04-15-rag-agent-decision-orchestrator.md`
2. `2026-04-15-rag-agent-decision-orchestrator.md`
3. `003-2026-04-17-task-queue-concurrency.md`
4. `004-2026-04-18-task-queue-concurrency.md`

当前 `plans` 根目录仅保留主线计划、执行日志与仍有参考价值的历史专题文档。

---

## 5) 当前建议阅读顺序（最短路径）

1. `014-2026-05-01-phase7-execution-log.md`（当前状态）
2. `013-2026-05-01-rag-agent-framework-evolution-phase7-plan.md`（当前目标与验收）
3. `012-2026-04-29-phase6-execution-log.md`（上一阶段背景）
4. `011-2026-04-28-rag-agent-framework-evolution-phase6-plan.md`（设计上下文）
