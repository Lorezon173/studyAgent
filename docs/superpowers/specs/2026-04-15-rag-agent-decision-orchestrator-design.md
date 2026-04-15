# RAG 与 Agent 决策冲突治理设计（Decision Orchestrator）

## 1. 问题与目标

当前系统中，`route_intent`、`decide_rag_call`、`route_tool` 在不同层分别决策，导致以下冲突：

1. `teach_loop` 场景下出现“应检索却跳过”，回答偏离上下文。
2. Agent 意图与工具路由不一致，执行阶段发生“二次改判”。
3. 单轮请求缺少统一决策主键，追踪和排障成本高。

本次重构目标：

- 单轮请求只产生一份统一决策，执行链路只读不改。
- `teach_loop` 默认必走 RAG（可被显式策略关闭）。
- `tool_route` 不再拥有“是否检索”决策权，只负责执行下发计划。

## 2. 设计原则

1. **单一决策入口**：所有关键决策收敛到一个编排器。
2. **决策与执行分离**：决策模块只产出合同，执行模块不改合同。
3. **可回放可审计**：每轮请求携带 `decision_id`，全链路可追溯。
4. **低风险迁移**：先接入新入口，再逐步去除旧外部调用路径。

## 3. 目标架构

新增模块：`app/services/decision_orchestrator.py`

- 输入：`user_input`, `topic`, `user_id`, `current_stage`, `history_summary`（可选）
- 输出：`DecisionContract`

`DecisionContract` 建议结构：

```python
{
  "decision_id": "uuid",
  "intent": "teach_loop|qa_direct|review|replan",
  "need_rag": True|False,
  "rag_scope": "global|personal|both|web|none",
  "tool_plan": ["search_local_textbook", "search_personal_memory"],
  "fallback_policy": "no_evidence_template",
  "reason": "...",
  "confidence": 0.0
}
```

模块职责调整：

- `AgentService`：调用 orchestrator 获取合同，并按合同驱动 StageOrchestrator。
- `route_intent / decide_rag_call / route_tool`：降级为 orchestrator 的内部策略函数。
- `tool_executor`：仅执行 `tool_plan`，不再根据输入再做“是否检索”判断。

## 4. 决策流（冲突消解核心）

固定三阶段：

1. `IntentDecision`：先确定对话意图。
2. `RetrievalDecision`：基于意图、阶段、策略确定 `need_rag + rag_scope`。
3. `ExecutionPlan`：仅在 `need_rag=True` 时生成 `tool_plan`。

关键策略：

- `teach_loop`：默认 `need_rag=True`。
- `qa_direct`：允许按策略与置信度决定 `need_rag`。
- `review/replan`：默认不检索，除非策略显式开启。
- 检索空结果时：执行 `fallback_policy`，使用无证据回答模板并显式标注“未命中知识库”。

## 5. 数据与观测

在 `branch_trace` 增加统一决策事件：

```json
{
  "phase": "decision_orchestrator",
  "decision_id": "...",
  "intent": "...",
  "need_rag": true,
  "rag_scope": "...",
  "tool_plan": ["..."],
  "reason": "...",
  "confidence": 0.87
}
```

执行阶段沿用同一 `decision_id` 记录 `rag`、`tool_router`、`executor` 事件，确保同轮可串联。

## 6. 迁移方案

### 第一步：接入新入口（兼容期）

- 新增 orchestrator 与 `DecisionContract`。
- `agent_service.run` 改为先调用 orchestrator，再执行。
- 旧函数保留，但只允许 orchestrator 内部调用。

### 第二步：收口旧路径（清理期）

- 清理外部直接调用旧决策函数的路径。
- 在代码审计中确认“是否检索”判断只存在 orchestrator 一处。

## 7. 验收标准

必须同时满足：

1. 同一轮请求只产生一份统一决策，执行链路仅读不改。
2. `teach_loop` 默认必走 RAG（除非策略显式关闭）。
3. `tool_route` 不再拥有“是否检索”决策权。
4. 同一请求中 `intent/need_rag/tool_plan` 在执行前后保持一致。
5. 回归覆盖 `teach_loop` 与 `qa_direct` 的命中/未命中场景。

## 8. 风险与缓解

- 风险：旧逻辑残留导致双路径并存。  
  缓解：通过代码搜索和单测断言“唯一入口”。
- 风险：策略过严导致不必要检索。  
  缓解：将 `qa_direct` 保留策略开关和阈值。
- 风险：trace 字段扩展影响旧消费方。  
  缓解：新增字段保持向后兼容，不移除旧字段。

## 9. 非目标（本轮不做）

- 不更换 RAG 存储底座与召回算法。
- 不改动 LangGraph 教学子图节点逻辑。
- 不引入新的外部基础设施。
