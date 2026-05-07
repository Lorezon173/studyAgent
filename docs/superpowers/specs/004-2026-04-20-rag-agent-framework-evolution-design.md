# StudyAgent 12周框架改进设计（质量优先路线）

## 1. 背景与目标

基于 `plan/harness/harness-agent-design-single.md` 的“RAG优先、分层单体 + 可插拔接口”框架，以及 `plan/项目报告2026-04-18.md` 的当前实现状态（LangGraph + FastAPI + Celery + Redis + Langfuse），本设计规划下一阶段 12 周架构演进。

目标是在**不替换现有主栈**的前提下，优先提升回答质量，同时逐步增强编排可控性与系统可运维性，形成可持续迭代的工程闭环。

## 2. 范围与约束

### 2.1 范围（In Scope）

1. RAG 质量体系升级：检索前理解、检索中多路召回、检索后证据治理与可信度标注。  
2. Agent 编排升级：从“意图路由”扩展为“意图 + 证据联合路由”。  
3. 稳定性与运维治理：SLO、灰度发布、容量治理、观测看板、压测与回归机制。

### 2.2 约束（Out of Scope）

1. 不替换 LangGraph/FastAPI/Celery/Redis 主干技术。  
2. 不在本轮引入多 Agent 协作框架。  
3. 不做与当前学习场景无关的大规模通用平台重构。

## 3. 方案对比与选型结论

候选方案：

1. 质量优先：前半程主攻 RAG，后半程补编排与治理。  
2. 平衡双轨：每阶段同步推进三线，主次分明。  
3. 平台优先：先治理与运维，再优化 RAG 与编排。

选型结论：采用**方案1（质量优先）**。  
理由：当前系统已有可用编排和可观测基础，优先提升 RAG 的可解释性与可信度能最快改善用户感知价值；后续通过阶段化治理降低质量改造带来的稳定风险。

## 4. 目标架构（保持现有栈下的增强）

### 4.1 分层保持不变，能力分层增强

1. Interaction Layer：API/CLI 不变，补充质量与状态信息透出。  
2. Orchestration Layer：新增检索策略、证据守门、恢复路径节点。  
3. Retrieval Layer：升级为四级检索管线与证据标准化输出。  
4. Reasoning Layer：按证据置信等级选择回答策略。  
5. Infrastructure Layer：补齐 SLO、容量治理、观测与发布守门。

### 4.2 关键新增/增强组件

1. `query_understanding`：意图识别、术语规范化、查询改写、预算分配。  
2. `retrieval_planner_node`：动态选择 BM25/向量/结构化/Web 组合。  
3. `evidence_validate_node`：覆盖度、冲突度、引用完整性校验。  
4. `answer_policy_node`：依据证据置信等级决定回答模板。  
5. `recovery_node`：节点失败时统一降级与可观测恢复。

## 5. RAG 设计升级

### 5.1 检索前（Query Understanding）

1. 问题类型识别：事实问答、对比分析、总结复习、学习规划。  
2. 查询改写策略：同义扩展、实体标准化、子问题拆分。  
3. 检索预算策略：快速/标准/深度模式，控制成本与时延。

### 5.2 检索中（四级管线）

1. 词法召回：BM25，保障精确命中。  
2. 语义召回：向量检索，保障语义覆盖。  
3. 结构化召回：DB/元数据过滤，保障边界和一致性。  
4. 外部召回：Web 按策略触发，默认受限且可降级。

### 5.3 检索后（证据治理）

1. 去重聚类 + 学习场景重排（教材优先、来源质量加权、时效加权）。  
2. 统一证据对象：`chunk + source + score + reason + freshness`。  
3. 证据置信分级（High/Medium/Low）与回答边界声明强绑定。

## 6. Agent 编排设计升级

### 6.1 路由机制

从单一意图路由升级为联合路由：  
`intent_router -> retrieval_planner_node -> evidence_validate_node -> answer_policy_node -> (summary/replan/recovery)`

### 6.2 状态模型收敛

将状态字段按四类治理：

1. 会话态（用户上下文、主题、历史轮次）  
2. 检索态（策略、源选择、预算、召回统计）  
3. 证据态（覆盖度、冲突、置信等级、引用完整性）  
4. 生成态（回答策略、降级标记、失败码、重试轨迹）

### 6.3 失败恢复与异步协同

1. 长链路节点（深度检索、Web 抓取）由 Celery 执行并持续推送进度。  
2. 编排层显式支持任务取消、超时、部分源失败。  
3. 恢复策略统一输出失败原因码，便于 Langfuse 聚合分析。

## 7. 运维与治理设计

### 7.1 SLO 体系

1. 质量：引用覆盖率、低证据声明覆盖率、关键问集正确率。  
2. 稳定：任务成功率、重试后恢复率、队列积压阈值。  
3. 时延：P95 首字节时延、P95 总响应时延。

### 7.2 发布守门

1. 灰度发布 + 回滚预案。  
2. 未达 SLO 门槛不允许全量发布。  
3. 每次策略变更必须通过固定回归集对比。

### 7.3 容量与成本

1. 分层缓存（query 结果缓存、证据包缓存）。  
2. 模型分级调用（按任务复杂度选择模型）。  
3. Worker 并发与队列优先级（在线对话优先于离线任务）。

## 8. 12周落地路线

### Phase 1（W1-W4）：RAG 质量冲刺

1. 建立离线评测集与线上指标定义。  
2. 上线查询改写与预算策略。  
3. 上线证据治理、置信分级、引用联动。  
4. 完成第一轮质量验收与回归基线固化。

### Phase 2（W5-W8）：编排增强

1. 落地 `retrieval_planner_node` 与 `evidence_gate`。  
2. 落地 `answer_policy_node` 与回答模板策略。  
3. 落地 `recovery_node` 与超时/取消语义。  
4. 完成第二轮端到端回归与链路压测。

### Phase 3（W9-W12）：稳定化治理

1. 固化 SLO 阈值与发布守门策略。  
2. 完成容量治理与队列优先级调优。  
3. 建立问题定位看板与告警联动。  
4. 完成全量发布评审与运维手册冻结。

## 9. 验收标准（建议门槛）

1. 质量：引用覆盖率 >= 85%，低证据声明覆盖率 >= 95%。  
2. 稳定：任务成功率 >= 99%，重试后恢复率 >= 80%。  
3. 时延：P95 首字节 <= 2.5s，P95 总时延 <= 12s。

## 10. 风险与应对

1. 风险：质量策略引入后时延上升。  
   应对：预算分级 + 缓存 + 模型分级调用。  
2. 风险：多路检索导致调参复杂度增加。  
   应对：固定回归集 + 策略版本化 + A/B 对比。  
3. 风险：失败恢复路径覆盖不足。  
   应对：故障注入测试 + 失败码规范化 + 统一回放分析。

## 11. 非目标声明

本设计不覆盖多 Agent 协作编排、跨团队平台化拆分、以及新基础设施栈替换。上述能力在本轮 12 周结束后再进入下一轮架构评估。

## 12. Progress Note

### Phase 1 已交付 ✅
- 已接入查询规划（query planning）并在 RAG 执行阶段生效。
- 已接入证据置信分级与低证据边界声明策略。
- Graph V2 与 Chat API 已透出 RAG 置信度元数据。

### Phase 2 已交付 ✅
- 已实现检索规划节点（retrieval_planner_node）。
- 已实现证据守门节点（evidence_gate_node）。
- 已实现回答策略节点（answer_policy_node）。
- 已实现恢复节点（recovery_node）。
- Graph V2 已集成全部新节点。
- 新增服务：retrieval_strategy、evidence_validator、answer_templates、error_classifier。

### Phase 3 已交付 ✅（截至 2026-05-02）

Phase 3 顶层 spec 升级版见 `docs/superpowers/specs/top-007-2026-05-01-phase3-finalization-design.md`，4 个子阶段全部完成：

#### 3a 异步骨架（PR #1 → origin/master）
- Celery + Redis 接入：`app/worker/celery_app.py`、`app/worker/tasks.py`、`app/services/redis_pubsub.py`、`app/services/task_dispatcher.py`
- 配置：`ASYNC_GRAPH_ENABLED` / `REDIS_URL` / `CELERY_TASK_TIMEOUT_S`
- 21 个测试，flag off 时零依赖。

#### 3b chat API 切到异步路径（PR #2 → origin/master）
- `agent_service.run` 增加 `progress_sink` 参数（重构为薄壳 + `_run_impl`）。
- `run_chat_graph` 由占位替换为真实 graph 调用 + pubsub 桥接。
- `RedisPubSub.open_subscription` 上下文管理器解决订阅惰性问题。
- `chat.py /chat/stream` 按 flag 分流，flag off 完全保留同步路径。
- 15 个测试。

#### 3c SLO 门禁（PR #4 → 待合）
- v1 6 个 SLI 阈值（`slo/thresholds.yaml`）+ 12 题 4 类回归集（`slo/regression_set.yaml`）。
- `slo/loader.py` + `aggregator.py` + `checker.py` 纯函数三件套。
- `uv run python -m slo.run_regression` 一键检查（exit 0/1/2）。
- 22 个测试。
- 与原 §9 阈值差异：accept ≤ 0.5s + first_token ≤ 3.0s（拆分原首字节 ≤ 2.5s，预留 0.5s 桥接）；completion ≤ 15s（原 12s，异步开销）；成功率 0.97（原 0.99，异步真实失败模式）；retry 恢复率 0.70（原 0.80）。质量两项保持。

#### 3d 看板 / 告警 / runbook（PR #4 → 待合）
- `slo/alert_evaluator.py` + `slo/alert_rules.yaml` 三级告警（INFO / WARN / CRIT），纯函数。
- 集成到 `run_regression` CLI（终端输出 alert 摘要 + 写 `logs/slo_alerts.log`）。
- `docs/observability/dashboards/schema.md` 4 类面板字段定义 + `README.md` 入口。
- `docs/runbook/` 6 份核心文档 + `oncall_response.md`。
- `plan/README.md` 顶部加运维入口链接。
- 15 个测试。

### 验收基线（截至 Phase 3d 合并）
- 全量回归：357 PASS / 19 FAIL（19 失败为 Phase 7 起的既有基线，不退化）。
- SLO v1 基线：stub agent 跑 12 题全 PASS，门禁有效性已用恶意阈值验证（exit 1）。
- 文档：7 份 runbook + 1 份 dashboard schema + 4 份 plan（015/016/017/018）+ 1 份顶层 spec（top-007）入仓。

