# RAG Agent 框架演进 Phase 6（安全整理版）

## 1. 文档说明

本文件是对 Phase 6 计划与执行信息的**格式重整版**。  
目标是保留原有信息密度，同时修复以下问题：

1. 章节层级混乱（标题、正文、代码块混排）
2. 重复文本与“编辑”噪音
3. 流程步骤与验收项缺乏清晰边界

> 本版侧重可读性与可执行性，不扩展 Phase 6 既定范围。

---

## 2. Phase 6 目标

补齐 Phase 5 中两处“有元数据、无消费方”的约定闭环：

1. `NodeMeta.retry_key` 类型收紧（`Literal` + 运行时校验）
2. `_append_trace` 消费 `NodeMeta.trace_label` 与 `NodeMeta.sensitive`

预期结果：

1. retry 配置错误在装饰阶段尽早失败
2. branch_trace 的 `phase` 值可读（trace_label）
3. 敏感节点支持追踪数据脱敏
4. 错误事件（`*_error`）保持兼容行为

---

## 3. 范围与非目标

### 3.1 In Scope

1. 修改 `app/agent/node_decorator.py`
2. 修改 `app/agent/nodes/_shared.py`
3. 补充/新增测试：
   - `tests/test_node_decorator.py`
   - `tests/test_append_trace.py`
   - `tests/test_phase6_e2e.py`
4. 记录交付与回归结果

### 3.2 Out of Scope（Phase 7+）

1. Langfuse 实际上报接入
2. OrchestrationView / RecoveryView 引入
3. `/chat/plan` 与 `/chat/execute` API 拆分
4. 跨主题记忆、证据冲突检测等产品能力

---

## 4. 变更文件结构

```text
app/agent/
├── node_decorator.py            # retry_key 类型收紧 + 运行时校验
├── node_registry.py             # 无功能变更
└── nodes/
    └── _shared.py               # _append_trace 消费 NodeMeta 元数据

app/monitoring/
└── desensitize.py               # 复用 sanitize_metadata

tests/
├── test_node_decorator.py       # 补充 retry 校验测试
├── test_append_trace.py         # 新增：trace 元数据消费测试
└── test_phase6_e2e.py           # 新增：端到端验证
```

---

## 5. 执行任务拆分

## 任务 1：retry_key 类型收紧

### 目标

将 `NodeMeta.retry_key` 和 `node(..., retry=...)` 从宽泛字符串改为：

`Optional[Literal["LLM_RETRY", "RAG_RETRY", "DB_RETRY"]]`

并在 `node()` 内加入运行时白名单校验。

### 实施项

1. 在 `node_decorator.py` 增加 `RetryKey` 类型别名
2. 增加 `_VALID_RETRY_KEYS` 常量
3. 非法 retry 值直接 `ValueError`
4. 在 `tests/test_node_decorator.py` 新增/补强用例

### 验收

1. 非法字符串 retry 在装饰阶段报错
2. `retry=None` 正常
3. 合法 retry key 正常

---

## 任务 2：_append_trace 消费 NodeMeta

### 目标

`_append_trace(state, phase, data)` 在写入前：

1. 查询 `NodeRegistry` 获取 `NodeMeta`
2. `phase` 写入 `meta.trace_label`（fallback 原值）
3. `meta.sensitive=True` 时执行 `sanitize_metadata`

### 兼容约束

1. trace 字段名仍为 `phase`（仅 value 变化）
2. 对未注册 phase（含 `*_error`）保持兼容
3. 函数签名不变

### 实施项

1. 修改 `app/agent/nodes/_shared.py`
2. 新增 `tests/test_append_trace.py`
3. 覆盖如下场景：
   - 已注册 phase 标签替换
   - 未注册 phase 保持原值
   - 敏感字段脱敏
   - 非敏感节点透传
   - 多次写入累积
   - `*_error` + sensitive 回查脱敏

---

## 任务 3：E2E 验证与交付记录

### 目标

验证 Phase 6 行为在图执行链路中生效，并记录交付状态。

### 实施项

1. 新增 `tests/test_phase6_e2e.py`
2. 覆盖：
   - 成功链路产生人类可读 phase label
   - 错误链路保留 `rag_first_error`
   - 非法 retry 运行时报错
3. 记录 Phase 6 执行结果与回归现状

---

## 6. 关键设计决策

1. **Literal + 运行时双重约束**  
   Literal 只在静态阶段生效；运行时仍需白名单校验，避免错误延迟到 graph build。

2. **trace 字段名不改**  
   仍写 `phase`，降低下游兼容成本。

3. **函数内延迟导入**  
   在 `_append_trace` 内导入 `get_registry` 与 `sanitize_metadata`，降低潜在循环依赖风险。

4. **错误事件兼容优先**  
   未注册 phase 维持原行为；若是 `*_error` 且基础节点为 sensitive，则进行脱敏保护。

---

## 7. 风险与缓解

| 风险 | 缓解 |
|---|---|
| `_append_trace` 额外查表开销 | in-memory dict O(1)，可接受 |
| 既有断言依赖 snake_case phase | 定向 grep 并迁移断言 |
| retry key 常量漂移 | 后续可统一到 retry policy 单一源 |
| 新增测试被忽略 | 调整 `.gitignore`，显式纳入关键测试文件 |

---

## 8. 测试与验证结果（执行记录）

### 8.1 定向回归（Phase 6 相关）

覆盖测试集：

1. `tests/test_phase6_e2e.py`
2. `tests/test_phase5_e2e_compat.py`
3. `tests/test_append_trace.py`
4. `tests/test_node_decorator.py`

结果：**通过（24 passed）**。

### 8.2 全量回归

结果：**存在仓库既有失败基线**（并非仅由 Phase 6 引入）。  
典型错误集中在旧测试 mock 与新调用参数不一致（例如 `stream_output` 参数）。

---

## 9. 提交与交付建议

1. 代码提交建议按任务切分（Task1 / Task2 / Task3）
2. 确保新增关键测试文件未被 `.gitignore` 屏蔽
3. 在 PR 描述中明确：
   - Phase 6 目标达成项
   - 全量套件既有失败说明
   - 本次变更对应的定向回归结果

---

## 10. 最终结论

Phase 6 的核心目标已闭环：

1. retry_key 从“约定字符串”升级为“类型 + 运行时校验”
2. `_append_trace` 实际消费 `trace_label/sensitive`
3. E2E 与单测覆盖成功路径、错误路径和兼容行为

本文件已完成格式重整，可作为后续实施与审阅的稳定版本。
