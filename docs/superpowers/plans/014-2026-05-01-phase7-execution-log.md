# Phase 7 执行日志（2026-05-01）

## 1. 执行目标

基于 `013-2026-05-01-rag-agent-framework-evolution-phase7-plan.md`，在“先检查现状、只补缺口”的前提下完成 Phase 7：

1. Retry Policy 单一事实源（SSOT）
2. Langfuse v4 真实可用
3. `add_to_graph` 节点级 Span 包装
4. `truncate_payload` 在 Span 与 branch_trace 复用
5. `.gitignore` 白名单与交付收尾

---

## 2. 执行前现状检查（已完成项识别）

本次先对照现有代码，确认以下项目已落地或部分落地：

1. `retry_policy.py` 已存在 `RETRY_POLICIES_MAP`
2. `node_decorator.py` 已使用 `RETRY_POLICIES_MAP.keys()` 做运行时 retry 校验，保留 `RetryKey Literal`
3. `graph_v2.py` 已改为 `retries=RETRY_POLICIES_MAP`
4. `langfuse_client.py` 已无 `langfuse.decorators` 依赖
5. `trace_wrapper.py` 已使用 v4 的 `start_as_current_observation`
6. `desensitize.py` 已有 `truncate_payload`
7. `_shared.py` 已在 `_append_trace` 使用 `truncate_payload`
8. `tests/test_langfuse_v4_adapter.py`、`tests/test_retry_policy_ssot.py`、`tests/test_truncate_payload.py` 已存在（但此前受 `.gitignore` 影响未显式纳入）

仍缺口：

1. `node_registry.add_to_graph` 里没有节点 Span 包装（Task 2 缺失）
2. 缺少 `tests/test_node_registry_span.py`
3. `.gitignore` 未对白名单放行 Phase 7 新增测试

---

## 3. 基线信息

### 3.1 全量基线（执行前）

命令：

```powershell
$env:PYTHONPATH='.'
$env:DEBUG='false'
uv run pytest tests/ -q
```

结果：`291 passed / 19 failed`（既有失败基线）。

### 3.2 Langfuse v4 API 探针

命令（一次性）：

```powershell
uv run python -c "from langfuse import Langfuse, get_client; ..."
```

结论：

1. `get_client()` 可用
2. `start_as_current_observation` 可用
3. `start_as_current_span` / `start_span` 不可用（当前环境）

因此 Phase 7 统一继续使用 `start_as_current_observation`。

---

## 4. 本次实际变更

## Task 2：`add_to_graph` 节点 Span 包装（补齐缺口）

### 变更文件

1. `app/agent/node_registry.py`
2. `tests/test_node_registry_span.py`（新增）

### 关键实现

在 `NodeRegistry.add_to_graph` 中新增 `_wrap_with_span(meta, fn)`，并对注册到 graph 的函数统一包裹：

1. `langfuse_enabled=False` 或 client 为 `None` 时直接透传原函数
2. 启用时创建 observation span，name 使用 `meta.trace_label or meta.name`
3. `span.update(input=truncate_payload(...))`
4. `meta.sensitive=True` 时 input/output 先 `sanitize_metadata`
5. 节点异常时记录 `span.update(level="ERROR", status_message=...)` 后原样抛出
6. 包装只发生在 `add_to_graph` 路径，保持 `@node` 纯元数据契约不变

### 新增测试覆盖

`tests/test_node_registry_span.py` 覆盖：

1. disabled 模式零侵入透传
2. 启用时 span 创建与命名正确
3. sensitive 节点 input/output 脱敏并截断
4. 异常路径记录 ERROR 且 re-raise

---

## Task 4：交付收尾

### 4.1 `.gitignore` 白名单

更新为显式放行以下测试文件：

1. `!tests/test_retry_policy_ssot.py`
2. `!tests/test_langfuse_v4_adapter.py`
3. `!tests/test_node_registry_span.py`
4. `!tests/test_truncate_payload.py`

### 4.2 Task 状态

`phase7-task0..4` 已在 SQL todo 中流转并完成。

---

## 5. 测试结果

### 5.1 Phase 7 相关测试集

命令：

```powershell
uv run pytest tests/test_node_registry_span.py tests/test_langfuse_v4_adapter.py tests/test_retry_policy_ssot.py tests/test_truncate_payload.py tests/test_append_trace.py tests/test_node_decorator.py -q
```

结果：`49 passed / 0 failed`。

### 5.2 全量回归（执行后）

命令：

```powershell
$env:PYTHONPATH='.'
$env:DEBUG='false'
uv run pytest tests/ -q
```

结果：`295 passed / 19 failed`。

对比执行前基线：失败数未上升（仍 19），满足“基线不退化”。

---

## 6. 验收结论

对应 Phase 7 验收项，结论如下：

1. Task 0：已满足（v4 API 可用、adapter 正常）
2. Task 1：已满足（SSOT + 一致性测试已存在且通过）
3. Task 2：已满足（`add_to_graph` 包装生效，sensitive/异常行为已测）
4. Task 3：已满足（`truncate_payload` 已在 Span 与 `_append_trace` 路径使用）
5. Task 4：已满足（`.gitignore` 白名单已补、回归不退化、交付日志已写）
6. 架构契约：`@node` 仍不改变函数签名和直接调用行为（包装仅在 graph 注册路径）
7. 回滚路径：`LANGFUSE_ENABLED=false` 时全部 Span 包装短路透传

---

## 7. 本次变更文件清单

1. `app/agent/node_registry.py`
2. `.gitignore`
3. `tests/test_node_registry_span.py`
4. `docs/superpowers/plans/014-2026-05-01-phase7-execution-log.md`

