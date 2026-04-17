# RAG 与 Agent 决策冲突治理设计（Decision Orchestrator）

## 1. 问题定义

当前链路中，`route_intent`、`decide_rag_call`、`route_tool` 分散在不同层做判断，导致：

1. `teach_loop` 场景出现“应检索却未检索”。
2. Agent 意图与工具路由不一致，执行层发生二次改判。
3. 单轮请求缺乏统一决策主键，排障困难。

## 2. 设计目标

1. 单轮请求只生成一份统一决策合同（DecisionContract）。
2. `teach_loop` 默认 `need_rag=True`（仅允许策略显式关闭）。
3. 执行层只读合同，不允许重判“是否检索”。
4. 决策可观测：全链路携带 `decision_id`。

## 3. 目标架构

新增：`app/services/decision_orchestrator.py`

- 输入：`user_input`, `topic`, `user_id`, `current_stage`
- 输出：`DecisionContract`

建议合同结构：

```python
{
  "decision_id": "uuid",
  "intent": "teach_loop|qa_direct|review|replan",
  "intent_confidence": 0.0,
  "need_rag": True,
  "rag_scope": "global|personal|both|web|none",
  "tool_plan": ["search_local_textbook", "search_personal_memory"],
  "fallback_policy": "no_evidence_template",
  "reason": "..."
}
```

职责收敛：

- `AgentService`：只调用 orchestrator 并按合同执行。
- `ContextBuilder`：仅根据 `need_rag/tool_plan` 执行或跳过。
- `ToolExecutor`：严格执行 `tool_plan`，不做隐式扩展。

## 4. 决策流

固定顺序：

1. IntentDecision（确定意图）
2. RetrievalDecision（确定 `need_rag + rag_scope`）
3. ExecutionPlan（生成 `tool_plan`）

核心规则：

- `teach_loop`：默认检索。
- `qa_direct/review/replan`：默认不检索，按策略例外开启。
- `rag_scope="both"` 时，`tool_plan` 必须包含双轨工具。
- 检索空结果：走 `fallback_policy` 并显式说明未命中证据。

## 5. 可观测性

在 `branch_trace` 增加：

```json
{
  "phase": "decision_orchestrator",
  "decision_id": "...",
  "intent": "teach_loop",
  "need_rag": true,
  "rag_scope": "both",
  "tool_plan": ["search_local_textbook", "search_personal_memory"],
  "reason": "..."
}
```

并在后续 `rag/executor` 事件中复用同一 `decision_id`。

## 6. 迁移策略

### 阶段一（接入）

1. 新增 orchestrator 与合同类型。
2. `agent_service.run` 改为先决策后执行。
3. 保留旧函数仅作兼容，不作为主链路入口。

### 阶段二（收口）

1. 清理外部对旧决策函数的直接调用。
2. 确保“是否检索”只在 orchestrator 出现一次。

## 7. 验收标准

1. 一轮请求只存在一份决策合同。
2. `teach_loop` 默认必检索。
3. `tool_route` 不再拥有检索开关决策权。
4. 执行前后 `intent/need_rag/tool_plan` 不变。
5. 回归覆盖命中与未命中场景。

## 8. 非目标

1. 不替换 RAG 存储底座。
2. 不重写 LangGraph 教学子图。
3. 不引入额外外部基础设施。
