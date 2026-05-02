# RAG Agent 框架演进 Phase 7：约定治理收尾与 Langfuse 真实接入

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Phase 7 是约定治理的收尾阶段，包含三件事：
1. 把重试策略（Retry Policy）统一为 Single Source of Truth；
2. **修复** Langfuse 监控管道（当前在 v4.x SDK 下事实上是死代码）；
3. 让节点入出口真实生成 Langfuse Span，并对超大 payload 应用 `truncate_text` 防止 OOM / 上报失败。

**Architecture:**

1. **重试策略统一**：以 [app/agent/retry_policy.py](app/agent/retry_policy.py) 为中心，导出 `RETRY_POLICIES_MAP`，[app/agent/node_decorator.py](app/agent/node_decorator.py) 的运行时校验集合改为派生自该 map；[app/agent/graph_v2.py](app/agent/graph_v2.py) 不再硬编码字典。`RetryKey: Literal[...]` **手抄列表保留**（PEP 586 不允许从 dict.keys() 派生），通过一致性测试守住同步。

2. **Langfuse v4 SDK 适配**：当前 [app/monitoring/langfuse_client.py](app/monitoring/langfuse_client.py) 仍按 v2 SDK 写法 `from langfuse.decorators import langfuse_context`，但已安装的 langfuse 4.3.1 已无该模块——`langfuse_context` 永远为 `None`，[app/monitoring/trace_wrapper.py](app/monitoring/trace_wrapper.py) 里所有 span 创建被 None-check 短路，事实上是死代码。Task 0 修复 SDK 适配层。

3. **Span 包裹位置**：保持 `@node` 的纯元数据契约不变（Phase 5 已立的 `@node 不改变函数签名或运行时行为` 约定），将 Span 包装放在 [app/agent/node_registry.py](app/agent/node_registry.py) 的 `add_to_graph` 内——**只在节点真正进入 LangGraph 运行时才被包裹**，对单测直接调用节点函数零影响。

4. **双观测管道分工**：保留两条互补管道：
   - `state["branch_trace"]`（Phase 6 完成）：业务可读的会话回放，由节点显式 `_append_trace(...)` 调用，写入特定字段（如 `citations_count`、`reply_length`）。
   - Langfuse Span（Phase 7 新增）：通用的入参/返回值/异常/耗时上报，由 `add_to_graph` 包装自动产生，无需改节点代码。两者非冗余，分别服务"业务回放"与"系统可观测"。

**Tech Stack:** Python 3.12、FastAPI、LangGraph、Langfuse 4.x、pytest、uv

**前置依赖：** Phase 6 已完成并合并到 master ✅
- [app/agent/node_decorator.py](app/agent/node_decorator.py) 已具备强类型的 `NodeMeta`
- [app/agent/nodes/_shared.py](app/agent/nodes/_shared.py) 的 `_append_trace` 已消费 `trace_label`/`sensitive`
- [app/monitoring/langfuse_client.py](app/monitoring/langfuse_client.py) 单例骨架存在 ⚠️ **但 v2 API 导入已失效**
- [app/monitoring/desensitize.py](app/monitoring/desensitize.py) 含 `sanitize_metadata` 与 `truncate_text`
- [tests/conftest.py](tests/conftest.py) 已有 `NodeRegistry` autouse 快照恢复

---

## File Structure

```text
app/agent/
├── retry_policy.py              # 修改：导出 RETRY_POLICIES_MAP（SSOT）
├── node_decorator.py            # 修改：_VALID_RETRY_KEYS 派生自 RETRY_POLICIES_MAP；Literal 保留（一致性测试守同步）
├── node_registry.py             # 修改：add_to_graph 内对每个节点函数包一层 Span 装饰器
└── graph_v2.py                  # 修改：从 retry_policy 导入字典，不再硬编码

app/monitoring/
├── langfuse_client.py           # 修改：升级到 v4 API（移除 langfuse.decorators 导入；改用 get_client + start_as_current_span）
├── trace_wrapper.py             # 修改：同步 v4 API；保持原对外签名以避免影响调用站点
└── desensitize.py               # 修改：新增 truncate_payload(dict, max_length) 递归工具

tests/
├── test_retry_policy_ssot.py        # 新增：Literal/RETRY_POLICIES_MAP/_VALID_RETRY_KEYS 三方一致性
├── test_langfuse_v4_adapter.py      # 新增：langfuse_client v4 适配的回归
├── test_node_registry_span.py       # 新增：add_to_graph 包装产生 Span，sensitive 节点被脱敏，异常进入 ERROR span
├── test_truncate_payload.py         # 新增：递归截断行为
└── conftest.py                      # 不变（Langfuse 通过 langfuse_enabled=False 默认禁用）

docs/superpowers/plans/
└── 014-2026-05-01-phase7-execution-log.md  # 新增：交付日志（按实际执行日期命名）
```

---

## 范围分解概览

| 任务 | 引入物 | 风险 | 改动文件 | 估时 |
|---|---|---|---|---|
| **Task 0**（前置）| Langfuse v4 SDK 适配 | 中（修复死代码，需要验证 v4 API 实际可用） | 2 | 2-3h |
| Task 1 | 统一 `RETRY_POLICIES_MAP` 为 SSOT | 极低（纯组织调整 + 一致性测试） | 3 + 1 测试 | 1h |
| Task 2 | `add_to_graph` 内包 Span（非 `@node`） | 中（行为变更但隔离在 graph 构建路径） | 1 + 1 测试 | 3-4h |
| Task 3 | `truncate_payload` 递归 + 两处复用 | 低（只截顶 + 限定深度） | 2 + 1 测试 | 1.5h |
| Task 4 | E2E + .gitignore 白名单 + 交付日志 | 极低 | 1 + 1 文档 | 1h |

**总估时：8.5-10.5h。** 任务依赖关系：Task 0 → Task 2 → Task 3；Task 1 与上述并行；Task 4 收尾。

---

## 任务 0（前置）：Langfuse v4 SDK 适配

**目标：** 让监控管道**真的工作起来**。当前已安装 langfuse 4.3.1，但 `from langfuse.decorators import langfuse_context` 在 v4 已被移除，所有 trace 调用被 None-check 静默短路。

**Files:**
- Modify: [app/monitoring/langfuse_client.py](app/monitoring/langfuse_client.py)
- Modify: [app/monitoring/trace_wrapper.py](app/monitoring/trace_wrapper.py)
- Add: [tests/test_langfuse_v4_adapter.py](tests/test_langfuse_v4_adapter.py)

### 步骤

- [ ] **Step 0.1：验证 v4 API**
  执行一个一次性 spike：
  ```bash
  python -c "from langfuse import Langfuse, get_client; c = get_client(); print(type(c).__name__)"
  python -c "from langfuse import Langfuse; l = Langfuse(public_key='x', secret_key='y'); print(hasattr(l, 'start_as_current_span'))"
  ```
  确认 `get_client()` / `start_as_current_span()` / `start_span()` 中至少一种可用，并选定 Phase 7 统一使用的入口。

- [ ] **Step 0.2：重写 `langfuse_client.py`**
  - 删除 `from langfuse.decorators import langfuse_context`
  - 暴露面调整为：`init_langfuse()`、`get_langfuse_client() -> Langfuse | None`、`is_langfuse_enabled() -> bool`
  - **保留** `init_langfuse()` 模块级调用，沿用现有 `try/except ImportError` 防御
  - 不暴露 `langfuse_context` 这一不存在的对象

- [ ] **Step 0.3：同步修正 `trace_wrapper.py`**
  - 把 `langfuse_context.span(name=..., input=...)` / `span.end(output=..., level=...)` 改写为 v4 等价调用：
    ```python
    client = get_langfuse_client()
    if client is None:
        return func(*args, **kwargs)
    with client.start_as_current_span(name=...) as span:
        span.update(input=...)
        result = func(*args, **kwargs)
        span.update(output=...)
        return result
    # 异常路径用 try/except 包，调用 span.update(level="ERROR", status_message=str(e)) 后 raise
    ```
  - **保持 `trace_llm` / `trace_rag` / `trace_tool` 的对外签名不变**，调用站点零修改

- [ ] **Step 0.4：新增 `tests/test_langfuse_v4_adapter.py`**
  - 用 `monkeypatch` 把 `get_langfuse_client` 返回一个 mock client
  - 验证 `trace_llm` 包装的函数被调用时，mock 上 `start_as_current_span` 被调用一次、`update(input=...)` 被调用、正常返回时 `update(output=...)` 被调用、异常时 `level="ERROR"`
  - 验证 `langfuse_enabled=False` 时直接透传，不创建 span

- [ ] **Step 0.5：基线回归**
  ```bash
  uv run pytest tests/test_langfuse_v4_adapter.py -v
  uv run pytest tests/ -q  # 确认全量失败基线（Phase 6 是 19 failed）未上升
  ```

---

## 任务 1：统一重试策略（Single Source of Truth）

**目标：** 把 `node_decorator.py` 的 `_VALID_RETRY_KEYS` 与 `graph_v2.py` 的硬编码字典都归口到 `retry_policy.py`。**`Literal` 手抄列表保留**——PEP 586 不允许从动态值派生 Literal——通过一致性测试守住同步。

**Files:**
- Modify: [app/agent/retry_policy.py](app/agent/retry_policy.py)
- Modify: [app/agent/node_decorator.py](app/agent/node_decorator.py)
- Modify: [app/agent/graph_v2.py](app/agent/graph_v2.py)
- Add: [tests/test_retry_policy_ssot.py](tests/test_retry_policy_ssot.py)

### 步骤

- [ ] **Step 1.1：修改 `app/agent/retry_policy.py`**
  在文件末尾添加：
  ```python
  RETRY_POLICIES_MAP: dict[str, RetryPolicy] = {
      "LLM_RETRY": LLM_RETRY,
      "RAG_RETRY": RAG_RETRY,
      "DB_RETRY": DB_RETRY,
  }
  ```

- [ ] **Step 1.2：修改 `app/agent/node_decorator.py`**
  - 移除 `_VALID_RETRY_KEYS = {"LLM_RETRY", "RAG_RETRY", "DB_RETRY"}`
  - 改为 `from app.agent.retry_policy import RETRY_POLICIES_MAP`，用 `RETRY_POLICIES_MAP.keys()` 作为运行时校验集合
  - **保留** `RetryKey = Literal["LLM_RETRY", "RAG_RETRY", "DB_RETRY"]` 并加注释 `# 与 RETRY_POLICIES_MAP 保持一致；改这里时同步 retry_policy.py`

- [ ] **Step 1.3：修改 `app/agent/graph_v2.py`**
  ```python
  # 旧
  from app.agent.retry_policy import LLM_RETRY, RAG_RETRY, DB_RETRY
  get_registry().add_to_graph(graph, retries={
      "LLM_RETRY": LLM_RETRY,
      "RAG_RETRY": RAG_RETRY,
      "DB_RETRY": DB_RETRY,
  })

  # 新
  from app.agent.retry_policy import RETRY_POLICIES_MAP
  get_registry().add_to_graph(graph, retries=RETRY_POLICIES_MAP)
  ```

- [ ] **Step 1.4：新增 `tests/test_retry_policy_ssot.py`**
  ```python
  from typing import get_args
  from app.agent.node_decorator import RetryKey
  from app.agent.retry_policy import RETRY_POLICIES_MAP

  def test_retry_key_literal_matches_map():
      """Literal 取值必须与 RETRY_POLICIES_MAP keys 一致。
      不一致时 mypy 会放过非法 retry 字符串，运行时也会拒绝合法值。"""
      assert set(get_args(RetryKey)) == set(RETRY_POLICIES_MAP.keys())

  def test_invalid_retry_key_rejected_at_decoration_time():
      from app.agent.node_decorator import node
      import pytest
      with pytest.raises(ValueError, match="retry"):
          @node(name="bad_retry", retry="UNKNOWN_RETRY")  # type: ignore[arg-type]
          def _bad(state):
              return state
  ```

- [ ] **Step 1.5：测试通过**
  ```bash
  uv run pytest tests/test_node_decorator.py tests/test_retry_policy_ssot.py -v
  ```

---

## 任务 2：节点级 Langfuse Span 真实接入（在 `add_to_graph` 包裹）

**目标：** 在 `NodeRegistry.add_to_graph` 添加节点到图时，对每个 fn 包一层 Span 装饰器。`@node` 装饰器本身**不变**，保持 Phase 5 的"纯元数据"契约。

**理由：** 在 `add_to_graph` 包裹的好处——
- 单测直接调用节点函数（如 `tests/test_node_decorator.py` 里的 `passthrough({...})`）走原路径，零破坏
- 包装只在 LangGraph 运行时存在
- 不需要改 24 处 `_append_trace` 调用站点
- 异常路径与重试路径都由 LangGraph 透出后再被 Span 捕获

**Files:**
- Modify: [app/agent/node_registry.py](app/agent/node_registry.py)
- Add: [tests/test_node_registry_span.py](tests/test_node_registry_span.py)

### 步骤

- [ ] **Step 2.1：在 `node_registry.py` 添加 Span 包装函数**
  在 `add_to_graph` 内对每个 `(meta, fn)` 包一层（伪代码）：
  ```python
  from app.monitoring.langfuse_client import get_langfuse_client, is_langfuse_enabled
  from app.monitoring.desensitize import sanitize_metadata, truncate_payload  # truncate_payload 由 Task 3 提供

  def _wrap_with_span(meta: NodeMeta, fn: Callable) -> Callable:
      def wrapped(state, *args, **kwargs):
          if not is_langfuse_enabled():
              return fn(state, *args, **kwargs)
          client = get_langfuse_client()
          span_name = meta.trace_label or meta.name
          with client.start_as_current_span(name=span_name) as span:
              try:
                  span_input = sanitize_metadata(state) if meta.sensitive else state
                  span.update(input=truncate_payload(span_input))
                  result = fn(state, *args, **kwargs)
                  span_output = sanitize_metadata(result) if meta.sensitive else result
                  span.update(output=truncate_payload(span_output))
                  return result
              except Exception as e:
                  span.update(level="ERROR", status_message=str(e))
                  raise
      wrapped.__wrapped__ = fn
      return wrapped
  ```
  在 `add_to_graph` 循环里：
  ```python
  fn_to_register = _wrap_with_span(meta, fn)
  if meta.retry_key is None:
      graph.add_node(name, fn_to_register)
  else:
      graph.add_node(name, fn_to_register, retry_policy=policy)
  ```

- [ ] **Step 2.2：保持 langfuse_enabled=False 时零侵入**
  - 验证：测试不需要 Mock Langfuse，因为 `is_langfuse_enabled()` 在 settings 默认 False 时直接走 `return fn(...)` 透传
  - 不需要修改 conftest.py

- [ ] **Step 2.3：新增 `tests/test_node_registry_span.py`**
  覆盖以下场景（用 `monkeypatch` 替换 `is_langfuse_enabled`/`get_langfuse_client` 为返回 mock）：
  1. `langfuse_enabled=False` 时 wrapper 不创建 span，直接透传
  2. 正常执行时 mock client 的 `start_as_current_span(name=trace_label)` 被调用一次
  3. 异常时 `span.update(level="ERROR")` 被调用，且原异常被 raise
  4. `meta.sensitive=True` 时 input/output 经过 `sanitize_metadata`
  5. 节点函数返回的 state 与未包装时一致（包装不改变业务结果）

- [ ] **Step 2.4：跑测试**
  ```bash
  uv run pytest tests/test_node_registry_span.py -v
  uv run pytest tests/ -q  # 确认全量基线未上升（Langfuse 默认禁用 → wrapper 透传）
  ```

---

## 任务 3：`truncate_payload` 递归工具与两处复用

**目标：** 在 `desensitize.py` 抽出递归截断工具 `truncate_payload(payload, max_length)`，再在两处复用：
- 新 Span wrapper（Task 2 已经引用）
- `_shared.py` 的 `_append_trace`（避免 branch_trace 也被超长字符串撑爆）

### 步骤

- [ ] **Step 3.1：在 `app/monitoring/desensitize.py` 添加 `truncate_payload`**
  ```python
  def truncate_payload(payload, max_length: int = 1500, _depth: int = 0):
      """递归截断 payload 中的字符串值。

      - dict / list 递归（限制深度 ≤ 3，超过深度的容器按 str 截断）
      - str → truncate_text(value, max_length)
      - 其他类型原样返回
      """
      if _depth > 3:
          return truncate_text(str(payload), max_length)
      if isinstance(payload, str):
          return truncate_text(payload, max_length)
      if isinstance(payload, dict):
          return {k: truncate_payload(v, max_length, _depth + 1) for k, v in payload.items()}
      if isinstance(payload, list):
          return [truncate_payload(v, max_length, _depth + 1) for v in payload]
      return payload
  ```

- [ ] **Step 3.2：在 `_shared.py` 的 `_append_trace` 内调用一次**
  在 `payload` 写入 traces 前：
  ```python
  from app.monitoring.desensitize import truncate_payload
  payload = truncate_payload(payload)
  ```
  位置：在 sanitize_metadata 之后、append 之前。

- [ ] **Step 3.3：在 Task 2 的 Span wrapper 内调用**（已在 Step 2.1 写入）

- [ ] **Step 3.4：新增 `tests/test_truncate_payload.py`**
  - 顶层 dict 含超长 str → 被截断
  - 嵌套 dict/list → 被递归截断
  - 深度 > 3 → 转 str 后截断
  - 非 str/dict/list（如 int, None）→ 原样返回

- [ ] **Step 3.5：跑测试**
  ```bash
  uv run pytest tests/test_truncate_payload.py tests/test_append_trace.py -v
  ```

---

## 任务 4：端到端验证、`.gitignore` 修复与交付

### 步骤

- [ ] **Step 4.1：更新 `.gitignore`**
  Phase 6 执行日志已发现 [.gitignore](.gitignore) 第 9 行 `tests/*` 默认忽略测试。在 `!tests/test_phase6_e2e.py` 之后追加：
  ```
  !tests/test_retry_policy_ssot.py
  !tests/test_langfuse_v4_adapter.py
  !tests/test_node_registry_span.py
  !tests/test_truncate_payload.py
  ```
  （或与团队商议后整体废弃 `tests/*` 这条 ignore——这是仓库治理债，已踩两次。）

- [ ] **Step 4.2：全量回归**
  ```bash
  $env:DEBUG='false'
  uv run pytest tests/ -q
  ```
  验收口径：**Phase 7 新增/修改触及的测试 100% 通过**；全量基线（Phase 6 时为 259 passed / 19 failed）**不允许上升**。

- [ ] **Step 4.3：手动冒烟（可选，建议做一次）**
  - 临时设置 `LANGFUSE_ENABLED=true` + 真实 keys（或 self-hosted 实例）
  - 触发一次 `/chat` 请求
  - 在 Langfuse UI 查看是否有 `intent_router` / `rag_first` / `rag_answer` 等 Span，且 `trace_label` 显示为人类可读名

- [ ] **Step 4.4：回滚开关**
  无需新增开关——`LANGFUSE_ENABLED=false`（默认值）即把所有 Span 包装短路，节点回退到原函数。在交付日志中明确写出该回滚路径。

- [ ] **Step 4.5：交付日志**
  新建 `docs/superpowers/plans/014-<执行日期>-phase7-execution-log.md`，参考 [012-phase6-execution-log.md](docs/superpowers/plans/012-2026-04-29-phase6-execution-log.md) 结构，记录：
  - 实际执行 SHA
  - 每个 Task 的测试结果
  - Langfuse v4 适配中遇到的实际 API 选择（`get_client` vs `Langfuse(...)`、`start_as_current_span` vs `start_span` 等）
  - 验收清单逐项打钩

---

## 验收清单

- [ ] **Task 0**：`langfuse_client.py` 不再依赖 `langfuse.decorators`；`get_langfuse_client()` 返回 v4 Langfuse 实例（或 None）；`trace_wrapper.py` 的 `trace_llm/trace_rag/trace_tool` 在启用时真实产出 Span
- [ ] **Task 1**：`RETRY_POLICIES_MAP` 是所有 retry 字典的唯一来源；`RetryKey` Literal 与 map keys 一致性测试通过
- [ ] **Task 2**：`add_to_graph` 包装的节点在启用 Langfuse 时产生 Span；`trace_label` 与 `sensitive` 在 Span 上生效；`@node` 装饰器签名/行为不变
- [ ] **Task 3**：`truncate_payload` 应用于 Span input/output 与 `branch_trace` payload；超长字符串与深嵌套均被处理
- [ ] **Task 4**：`.gitignore` 已加白名单；全量回归相对 Phase 6 基线（259 passed / 19 failed）不退化；交付日志已写
- [ ] **架构契约**：`@node 不改变函数签名或运行时行为` 仍成立（包装仅在 `add_to_graph` 路径生效）
- [ ] **回滚路径已说明**：`LANGFUSE_ENABLED=false` 即可禁用全部 Span 包装
