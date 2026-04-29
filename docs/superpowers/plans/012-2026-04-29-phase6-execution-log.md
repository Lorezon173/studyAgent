# Phase 6 执行全过程记录（execute-plan 实施日志）

## 1. 文档目的与范围

本文档完整记录本轮 `execute-plan` 的实际执行过程，覆盖：

1. 执行入口与目标
2. 任务分解与状态流转
3. 每一步代码改动
4. 测试与验证过程（含失败与阻塞信息）
5. 产出物与当前工作区状态
6. 风险、遗留与后续建议

本记录对应 Phase 6 计划：  
`docs/superpowers/plans/011-2026-04-28-rag-agent-framework-evolution-phase6-plan.md`

---

## 2. 执行入口（用户指令）

- 用户指令：`execute-plan：执行计划`
- 执行上下文：已存在 3 个待办（Task 1/2/3），状态均为 `pending`
- 工作目标：按既定依赖顺序完成 Task 1 → Task 2 → Task 3

---

## 3. 执行前状态检查

### 3.1 待办就绪检查

通过 SQL 查询 ready todos（无未完成依赖）：

- ready 结果：`phase6-task1-retry-literal`
- 依赖关系确认：
  - Task2 依赖 Task1
  - Task3 依赖 Task2

### 3.2 基线全量测试尝试（首次）

执行（带环境变量）：

```powershell
Set-Location "d:\backup\basic_file\Program\LearningAgent\studyAgent"
$env:PYTHONPATH='.'
uv run pytest tests/ -q
```

结果：测试未进入执行阶段即报配置错误（`pydantic Settings.debug` 解析失败，输入值 `release` 不是 bool）。

处理：后续测试统一增加：

```powershell
$env:DEBUG='false'
```

---

## 4. Task 1 执行明细（retry_key 类型收紧）

### 4.1 目标

将 `retry_key`/`retry` 从宽泛字符串收紧为受限取值，并加运行时防御校验：

- 静态层：`Literal["LLM_RETRY","RAG_RETRY","DB_RETRY"]`
- 运行时层：非法字符串立即 `ValueError`

### 4.2 修改文件

#### 文件 1：`app/agent/node_decorator.py`

关键改动：

1. 新增类型别名与白名单：
   - `RetryKey = Literal[...]`
   - `_VALID_RETRY_KEYS = {...}`
2. `NodeMeta.retry_key` 类型改为 `Optional[RetryKey]`
3. `node(..., retry=...)` 参数类型改为 `Optional[RetryKey]`
4. 在装饰器工厂入口增加运行时校验：
   - `retry not in _VALID_RETRY_KEYS` 时抛 `ValueError`

#### 文件 2：`tests/test_node_decorator.py`

新增 2 个测试：

1. `test_retry_key_only_accepts_known_values_at_runtime`
   - 验证非法 retry 字符串会在装饰阶段抛错
2. `test_retry_key_none_is_accepted`
   - 验证默认 `None` 仍可用

### 4.3 Task 1 测试结果

执行：

```powershell
uv run pytest tests/test_node_decorator.py -v
```

结果：`7 passed`

任务状态更新：

- `phase6-task1-retry-literal`: `in_progress` → `done`

---

## 5. Task 2 执行明细（_append_trace 消费 NodeMeta）

### 5.1 目标

让 trace 写入真正消费 Phase 5 元数据：

- 已注册节点：`phase` 写入 `trace_label`
- `sensitive=True` 节点：payload 自动脱敏
- 未注册 phase（如 `*_error`）：保持原行为

### 5.2 修改文件

#### 文件 1：`app/agent/nodes/_shared.py`

`_append_trace` 从“直接写 phase+data”升级为：

1. 函数内延迟导入：
   - `get_registry`
   - `sanitize_metadata`
2. 通过 `get_registry().get(phase)` 查询元数据
3. `label = meta.trace_label or phase`
4. `meta.sensitive` 为真时使用 `sanitize_metadata(data)`
5. `KeyError` fallback：维持 legacy 行为（不改写 phase、不脱敏）

#### 文件 2：`tests/test_append_trace.py`（新增）

新增 6 个测试覆盖：

1. 未注册 phase 保持兼容（`rag_first_error`）
2. 已注册节点使用 trace_label（如 `RAG First`）
3. 空 label 场景回退到节点名
4. sensitive 节点敏感键过滤
5. 非 sensitive 节点 payload 原样透传
6. 多次调用可累积 branch_trace

### 5.3 Task 2 测试结果

执行：

```powershell
uv run pytest tests/test_append_trace.py tests/test_node_decorator.py -v
```

结果：`13 passed`

任务状态更新：

- `phase6-task2-trace-consume-meta`: `in_progress` → `done`

---

## 6. Task 3 执行明细（E2E + 交付记录）

### 6.1 目标

补全端到端验收：

1. 成功路径 trace label 人类可读
2. 错误路径 phase 向后兼容
3. retry 非法值在装饰阶段即失败

### 6.2 修改文件

#### 文件 1：`tests/test_phase6_e2e.py`（新增）

新增 3 个用例：

1. `test_qa_direct_run_emits_human_readable_trace_labels`
   - 断言 branch_trace 出现 `RAG First`
   - 断言不再出现 `rag_first`
2. `test_error_phase_preserves_legacy_string`
   - 断言 `rag_first_error` 保持原值
3. `test_invalid_retry_key_at_decoration_time`
   - 断言非法 retry 装饰即抛错

#### 文件 2：`docs/superpowers/plans/011-2026-04-28-rag-agent-framework-evolution-phase6-plan.md`

在文件末尾追加“执行记录（2026-04-29）”区块，写入：

- 执行范围
- 变更文件清单
- 相关测试结果
- 全量回归现状
- 验收状态

### 6.3 Task 3 测试结果

先执行 Phase 6 相关回归（含 phase5 兼容）：

```powershell
uv run pytest tests/test_phase6_e2e.py tests/test_phase5_e2e_compat.py tests/test_append_trace.py tests/test_node_decorator.py -q
```

结果：`20 passed`

任务状态更新：

- `phase6-task3-e2e-delivery`: `in_progress` → `done`

---

## 7. 全量回归结果与阻塞说明

执行：

```powershell
uv run pytest tests/ -q
```

结果：

- `259 passed, 19 failed`

失败集中在既有测试（非本次新增用例），主要文件包括：

- `tests/test_agent_replan_branch.py`
- `tests/test_chat_flow.py`
- `tests/test_cli_repl.py`
- `tests/test_harness_engineering.py`
- `tests/test_learning_profile_api.py`
- `tests/test_profile_tail_api.py`
- `tests/test_sessions_api.py`

代表性报错：

- `TypeError: fake_invoke() got an unexpected keyword argument 'stream_output'`

结论：

- Phase 6 范围内新增/修改相关测试全部通过。
- 仓库存在既有全量失败基线，当前未在本次任务范围内修复。

---

## 8. 执行过程中的关键问题与处理

### 8.1 环境配置问题（DEBUG）

问题：测试启动前因 `Settings.debug` 解析失败中断。  
处理：显式设置 `$env:DEBUG='false'` 继续执行。

### 8.2 新增测试文件未出现在 git status

检查发现：

```powershell
git check-ignore -v tests/test_append_trace.py tests/test_phase6_e2e.py
```

命中规则：`.gitignore` 第 9 行 `tests/`。  
影响：新增测试文件被忽略，默认不会被纳入提交。  
处理建议：如需提交，使用 `git add -f` 或调整 `.gitignore` 规则。

---

## 9. SQL 待办流转记录

本轮新增并使用了一个文档任务条目：

- `phase6-execution-doc`（当前文档编写任务）

Phase 6 原始 3 个任务状态已全部完成：

- `phase6-task1-retry-literal`: `done`
- `phase6-task2-trace-consume-meta`: `done`
- `phase6-task3-e2e-delivery`: `done`

---

## 10. 产出物清单（本轮）

### 10.1 代码与测试产出

1. `app/agent/node_decorator.py`（修改）
2. `app/agent/nodes/_shared.py`（修改）
3. `tests/test_node_decorator.py`（修改）
4. `tests/test_append_trace.py`（新增，受 .gitignore 影响）
5. `tests/test_phase6_e2e.py`（新增，受 .gitignore 影响）

### 10.2 文档产出

1. `docs/superpowers/plans/011-2026-04-28-rag-agent-framework-evolution-phase6-plan.md`（追加执行记录）
2. `docs/superpowers/plans/012-2026-04-29-phase6-execution-log.md`（本文档）

---

## 11. 当前结论

本轮 `execute-plan` 在 Phase 6 范围内已完成全部目标：

1. retry_key 约束从“约定字符串”升级为“静态 + 运行时双重约束”
2. `_append_trace` 真正消费 `NodeMeta.trace_label/sensitive`
3. E2E 验证确认成功链路标签可读、错误链路向后兼容

同时确认了两项仓库层现实：

- 全量测试当前存在既有失败基线（19 failed）
- `.gitignore` 当前会忽略 `tests/` 下新增测试文件

以上即本次执行的完整落地记录。
