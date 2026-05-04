# LearningAgent（学习辅助 Agent）项目现状与进度说明

本项目是一个面向学习场景的 Agent 系统，核心目标是将"提问—理解—复述—纠偏—总结"做成可持续迭代、可追踪、可运营的学习闭环。  
当前代码已完成 **Phase 1 / Phase 2 / Phase 7 / Phase 3（3a~3d）** 的全部主线交付，并进入**下一轮架构评估前的稳定基线阶段**。

---

## 1. 项目定位

LearningAgent 以费曼学习法为主线，提供以下核心流程：

1. 诊断用户已有认知
2. 用更易理解的方式讲解
3. 要求用户复述并评估理解程度
4. 针对错误点追问与补救
5. 输出总结与复习建议

系统不是"单轮聊天助手"，而是"可沉淀学习轨迹、具备检索能力、带有运维基线"的学习编排系统。

---

## 2. 当前技术栈与架构

- Web/API：FastAPI（`app/main.py`）
- Agent 编排：LangGraph（`app/agent/graph_v2.py`）
- LLM 调用：langchain-openai（兼容 OpenAI 协议服务）
- 数据模型：Pydantic + TypedDict
- 检索：BM25 + Dense + RRF + rerank
- 可观测：Langfuse v4（`app/monitoring/`）
- 异步骨架：Celery + Redis（`app/worker/`、`app/services/redis_pubsub.py`、`task_dispatcher.py`）
- SLO 门禁：`slo/loader.py` / `aggregator.py` / `checker.py` / `run_regression.py`
- 前端交互：CLI（`main.py`） + Chainlit MVP（`app/ui/chainlit_app.py`）

分层结构（当前代码）

- `app/api/`：`chat`、`knowledge`、`sessions`、`skills`、`profile`、`auth`
- `app/agent/`：LangGraph 主图、状态、节点注册、retry policy
- `app/agent/nodes/`：`teach`、`qa`、`orchestration`
- `app/services/`：agent_service、RAG、工具执行、画像、评估、orchestration 子模块
- `app/worker/`：Celery app + `run_chat_graph`
- `app/monitoring/`：Langfuse client、trace wrapper、payload 脱敏/截断
- `slo/`：阈值 / 回归集 / 聚合器 / checker / alert_evaluator / CLI
- `docs/runbook/`：启停、回滚、容量、故障、发布、on-call
- `docs/observability/`：dashboard schema 与入口文档

---

## 3. 当前已落地能力（代码与文档一致）

### 3.1 学习主链路

- 多轮学习会话（阶段推进）
- 意图路由分支（teach_loop / qa_direct / review / replan）
- 自动重规划分支与 `branch_trace` 记录
- Graph V2 编排：17 个节点、条件边、节点级 retry policy、节点级 span 包装

### 3.2 RAG 能力

- 入库：`text` / `image`（图片走 OCR）
- 检索：`global` / `personal` 双轨
- 隔离：`personal` 强制 `user_id`
- 算法：BM25 + Dense + RRF + rerank
- Chat 注入：返回 `citations`，包含 `tool/scope/user_id` 等元信息
- 证据守门与回答策略：`evidence_gate` + `answer_policy`

### 3.3 用户与会话能力

- 用户注册 / 登录（`/auth/register`、`/auth/login`）
- 会话列表、详情、清理（`/sessions`）
- 学习档案与聚合查询（`/profile/*`）
- topic 维度长期记忆、timeline、review-plan 等 profile API

### 3.4 工具化检索与扩展

- 已有工具技能：
  - `search_local_textbook`
  - `search_personal_memory`
  - `search_web`
- `tool_route + tool_executor` 已接入主执行链路

### 3.5 交互层

- CLI 命令式交互（支持 `/plan show`、`/trace`、`/kadd`、`/ksearch`、`/klist`）
- Chainlit MVP（默认 2554 端口）
- 前端知识库上传交互（直连后端上传接口）

### 3.6 异步与可运营能力（Phase 3）

- 3a：Celery + Redis 异步骨架、dispatcher、pubsub、feature flag
- 3b：`/chat/stream` 在 `ASYNC_GRAPH_ENABLED=true` 时走异步路径（accepted → token → stage → done）
- 3c：SLO 门禁（6 个 SLI、12 题回归集、CLI 入口 `uv run python -m slo.run_regression`）
- 3d：告警评估器（INFO/WARN/CRIT）、dashboard schema、7 份 runbook 文档、README 运维入口

---

## 4. 顶层里程碑进度

### 已完成

- **Phase 1：RAG 质量冲刺** ✅
- **Phase 2：编排增强** ✅
- **Phase 7：约定治理 + Langfuse v4 收尾** ✅
- **Phase 3：稳定化治理（3a/3b/3c/3d）** ✅

### PR 链路（已全部合入远端）

- PR #1：Phase 7 + top-007 spec + 3a
- PR #2：3b chat 异步路径
- PR #3：Phase 7 残缺补齐
- PR #4：3c SLO 门禁 + 3d 看板/告警/runbook
- PR #5：顶层 spec §12 进度更新 + plans/019 收尾执行日志

### 当前结论

项目已经完成从"原型学习闭环"到"具备异步骨架、SLO 门禁、告警与 runbook 的可运营学习 Agent"的升级，当前 master 是**Phase 3 全部交付后的稳定基线**。

---

## 5. 测试与质量基线

当前全量回归基线：

```bash
PYTHONPATH=. DEBUG=false uv run pytest tests/ -q
```

最新结果：

- **357 passed / 19 failed**

说明：
- 19 个失败是历史既有 fixture/兼容性问题（主要在 `test_chat_flow.py`、`test_agent_replan_branch.py`、部分 API 测试）
- Phase 7 → 3a → 3b → 3c → 3d 全程 **失败数未增加**
- SLO check 入口：

```bash
uv run python -m slo.run_regression
```

该命令会：
1. 读 `slo/thresholds.yaml`
2. 跑 `slo/regression_set.yaml` 中 12 题
3. 聚合 6 个 SLI
4. 比对阈值并给出 exit code 0/1/2
5. 输出 alert 摘要（INFO/WARN/CRIT）

---

## 6. 当前文档入口（建议阅读顺序）

### 架构与阶段设计

1. `docs/superpowers/specs/004-2026-04-20-rag-agent-framework-evolution-design.md`
   - 12 周顶层路线 + 当前 Progress Note
2. `docs/superpowers/specs/top-007-2026-05-01-phase3-finalization-design.md`
   - Phase 3 顶层 spec（3a/3b/3c/3d）

### 计划与执行日志

1. `docs/superpowers/plans/015-2026-05-01-phase3a-async-skeleton.md`
2. `docs/superpowers/plans/016-2026-05-02-phase3b-chat-async-path.md`
3. `docs/superpowers/plans/017-2026-05-02-phase3c-slo-gate.md`
4. `docs/superpowers/plans/018-2026-05-02-phase3d-observability-runbook.md`
5. `docs/superpowers/plans/019-2026-05-02-phase3-finalization-execution-log.md`
6. `docs/superpowers/plans/014-2026-05-01-phase7-execution-log.md`
7. `docs/superpowers/plans/INDEX.md`

### 运维与观测

- `docs/runbook/00_index.md`
- `docs/runbook/oncall_response.md`
- `docs/observability/README.md`
- `docs/observability/dashboards/schema.md`

### 本次整体报告

- `reports/26-05-04-report.md`

---

## 7. 快速启动（当前推荐）

### 7.1 本地同步路径（默认、最稳）

```bash
uv sync
PYTHONPATH=. uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 1900
```

访问：
- API 文档：`http://127.0.0.1:1900/docs`

### 7.2 CLI

```bash
uv run python main.py
```

### 7.3 Chainlit MVP

```bash
uv run chainlit run app/ui/chainlit_app.py --host 0.0.0.0 --port 2554 -w
```

访问：`http://127.0.0.1:2554`

### 7.4 本地异步路径（验证 3a/3b）

```bash
# 1. Redis
docker run -d --name learning-agent-redis -p 6379:6379 redis:7-alpine

# 2. Celery worker
PYTHONPATH=. ASYNC_GRAPH_ENABLED=true \
  uv run celery -A app.worker.celery_app worker --loglevel=info

# 3. uvicorn
PYTHONPATH=. ASYNC_GRAPH_ENABLED=true \
  uv run uvicorn app.main:app --host 127.0.0.1 --port 1900
```

### 7.5 SLO 门禁

```bash
uv run python -m slo.run_regression
```

---

## 8. 运维入口（Phase 3d）

- [Runbook 索引](docs/runbook/00_index.md)：启停 / 回滚 / 容量 / 故障 / 发布检查
- [Observability 入口](docs/observability/README.md)：看板 schema 与 SLO 资产链路
- [On-Call 响应](docs/runbook/oncall_response.md)：3 个值班场景
- SLO 一键检查：`uv run python -m slo.run_regression`

---

## 9. 仍未完成 / 下一轮建议

当前 master 已完成 Phase 3 全部工作，但还有几件**明确未完结**的事项：

1. **19 个既有失败测试** 仍需独立修复（建议作为下一轮第一项）
2. **真实 Langfuse dashboard JSON** 尚未从实例手动导出（当前用 schema + 模板占位）
3. **retry_recovery_rate** 仍是 v1 占位，需接 Langfuse server 或真实 retry 数据后实测
4. **SLO v1 基线** 目前通过 stub agent 校准；首次接真实 LLM 后应重调阈值
5. 可进入下一轮架构评估：
   - 多 Agent 协作框架
   - 平台化拆分
   - 新基础设施栈替换

---

## 10. 当前状态一句话总结

**LearningAgent 现在不是一个“实验性原型”，而是一个已经完成异步骨架、SLO 门禁、告警规则、运维手册与进度文档闭环的学习型 Agent 系统；下一步重点不再是“补地基”，而是修历史失败基线并进入下一轮架构扩展。**
