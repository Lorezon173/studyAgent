# RAG Agent 框架演进 Phase 6：约定治理收口（retry 类型化、trace 元数据消费）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 Phase 5 留下的两块"已建管道但无消费方"补上消费侧——`NodeMeta.retry_key` 用 `Literal` 锁定取值；`NodeMeta.sensitive` 与 `NodeMeta.trace_label` 通过 `_append_trace` 进入 trace 流水。

**Architecture:** 不引入新模块。修改 `node_decorator.py` 用 `Literal` 收紧 retry_key；修改 `_shared.py` 的 `_append_trace` 在写 trace 前查询 `NodeRegistry` 取出对应 `NodeMeta`，按 `sensitive` 应用 `sanitize_metadata`、用 `trace_label` 替换 `phase` 字段。所有节点函数体不动，所有调用点不动。

**Tech Stack:** Python 3.12、FastAPI、LangGraph、pytest、uv

**前置依赖：** Phase 5 已合并到 master ✅
- `app/agent/node_decorator.py` 含 `NodeMeta(name, retry_key, trace_label, sensitive, tags)`
- `app/agent/node_registry.py` 含 `get_registry()` 单例
- `app/agent/nodes/_shared.py` 含 `_append_trace(state, phase, data)`，被 24 个站点调用
- `app/monitoring/desensitize.py` 含 `sanitize_metadata(dict) -> dict` 与 `truncate_text(str, max_length) -> str`
- `tests/conftest.py` 已为 `NodeRegistry` 提供 autouse 快照恢复 fixture

**非目标（OUT-of-SCOPE，留给 Phase 7+）：**
- 不引入 OrchestrationView / RecoveryView（等使用模式真正稳定）
- 不做条件边注册表化（无具体需求触发）
- 不实现跨主题概念记忆（产品性，独立 spec）
- 不实现证据冲突检测（产品性，独立 spec）
- 不拆分 `/chat/plan` & `/chat/execute` 端点（API 协议性，需前端协调）
- 不替换 LangGraph 内置 retry 机制
- 不接入 Langfuse 实际上报（trace 写入仍是 `state["branch_trace"]`；本期只让 trace 数据本身正确，集成上报留给 Phase 7）

---

## File Structure

```text
app/agent/
├── node_decorator.py            # 修改：retry_key 改为 Literal 类型
├── node_registry.py             # 不变
└── nodes/
    └── _shared.py                # 修改：_append_trace 消费 NodeMeta（sensitive + trace_label）

app/monitoring/
└── desensitize.py                # 不变（复用 sanitize_metadata + truncate_text）

tests/
├── test_node_decorator.py        # 修改：补一个静态类型断言用例（可选）
├── test_append_trace.py          # 新增：T2
├── test_phase6_e2e.py            # 新增：T3 端到端
└── conftest.py                   # 不变
```

---

## 范围分解概览

| 任务 | 引入物 | 风险 | 改动文件数 |
|---|---|---|---|
| Task 1 | `retry_key: Literal[...]` | 极低（仅类型注解） | 1 |
| Task 2 | `_append_trace` 消费 `NodeMeta` | 中（24 个调用站点都受影响，需保证不破坏既有断言） | 2 |
| Task 3 | E2E + 交付记录 | 极低 | 2 |

每个任务独立可合并。Task 2 最有意思——它让 Phase 5 的 `sensitive`/`trace_label` 字段从死代码变成活代码。

---

## 任务 1：retry_key 用 `Literal` 锁定取值

**目标：** 把 `NodeMeta.retry_key: Optional[str]` 改为 `Optional[Literal["LLM_RETRY","RAG_RETRY","DB_RETRY"]]`，让 IDE/mypy 能在写错字符串时立刻报错（而不是要等 graph build 时 `add_to_graph` 抛 `ValueError`）。

**Files:**
- Modify: `app/agent/node_decorator.py`
- Modify: `tests/test_node_decorator.py`（新增一个用例）

### 步骤

- [ ] **Step 1.1：写新测试**

打开 `tests/test_node_decorator.py`，在文件末尾追加：

```python
def test_retry_key_only_accepts_known_values_at_runtime():
    """retry_key 取值由 Literal 锁定。Literal 仅在类型检查阶段强制；
    运行时需要在 `node()` 内部显式校验，否则用户在写错时仅依赖 mypy。
    本用例验证装饰器拒绝未知 retry 字符串。"""
    import pytest
    from app.agent.node_decorator import node

    with pytest.raises(ValueError, match="retry"):
        @node(name="bad_retry_node", retry="UNKNOWN_RETRY")
        def _bad(state):
            return state


def test_retry_key_none_is_accepted():
    """retry=None（无重试）必须仍可用。"""
    from app.agent.node_decorator import node, get_node_meta

    @node(name="no_retry_node")
    def n(state):
        return state

    assert get_node_meta(n).retry_key is None
```

- [ ] **Step 1.2：运行测试，确认失败**

```
cd "<worktree>" && PYTHONPATH=. uv run pytest tests/test_node_decorator.py::test_retry_key_only_accepts_known_values_at_runtime -v
```
Expected: FAIL（无 `ValueError` 抛出，因为当前 `retry_key: Optional[str]` 接受任意字符串）。

- [ ] **Step 1.3：修改 `node_decorator.py` 收紧类型 + 加运行时校验**

读 `app/agent/node_decorator.py`，找到 `NodeMeta` 与 `node` 工厂。

**(a)** 在文件顶部 import 块加入：

```python
from typing import Literal
```

**(b)** 把 `NodeMeta.retry_key` 字段类型从 `Optional[str]` 改为：

```python
retry_key: Optional[Literal["LLM_RETRY", "RAG_RETRY", "DB_RETRY"]] = None
```

**(c)** 把 `node(...)` 工厂的 `retry` 参数类型也改：

```python
def node(
    *,
    name: str,
    retry: Optional[Literal["LLM_RETRY", "RAG_RETRY", "DB_RETRY"]] = None,
    trace_label: str = "",
    sensitive: bool = False,
    tags: tuple[str, ...] = (),
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
```

**(d)** 在 `node()` 工厂函数体的第一行加入运行时校验（紧跟 docstring 之后、`meta = NodeMeta(...)` 之前）：

```python
_VALID_RETRY_KEYS = {"LLM_RETRY", "RAG_RETRY", "DB_RETRY"}
if retry is not None and retry not in _VALID_RETRY_KEYS:
    raise ValueError(
        f"@node(retry={retry!r}) is not a valid retry key. "
        f"Allowed: {sorted(_VALID_RETRY_KEYS)} or None."
    )
```

`_VALID_RETRY_KEYS` 可以放为模块级常量，紧接 import 之后。这样 `add_to_graph` 也可以复用，但本任务不动 `node_registry.py`。

- [ ] **Step 1.4：运行新测试，确认通过**

```
cd "<worktree>" && PYTHONPATH=. uv run pytest tests/test_node_decorator.py -v
```
Expected: 7/7 PASS（5 既有 + 2 新）。

- [ ] **Step 1.5：跑全量回归**

```
cd "<worktree>" && PYTHONPATH=. uv run pytest tests/ -q 2>&1 | tail -3
```
Expected: 201 + 2 = 203 PASS（运行时校验不影响生产节点，因生产节点全部使用合法 retry_key）。

- [ ] **Step 1.6：提交**

```bash
git add app/agent/node_decorator.py tests/test_node_decorator.py
git commit -m "refactor(agent): tighten NodeMeta.retry_key with Literal and runtime validation"
```

---

## 任务 2：`_append_trace` 消费 `NodeMeta`（trace_label + sensitive）

**目标：** 让 `_append_trace(state, phase, data)` 在写入 trace 前查询 `NodeRegistry`：
- 若 `phase` 是已注册节点名：用 `meta.trace_label` 替换写入的 `phase` 字段（更可读），并按 `meta.sensitive=True` 走 `sanitize_metadata` 过滤敏感键。
- 若 `phase` 非节点名（如 `"rag_first_error"`、`"knowledge_retrieval_error"`）：保持原行为。

这样 Phase 5 引入的 `sensitive` 与 `trace_label` 字段从死代码变成 trace 流水的真实驱动。**不改任何节点的 `_append_trace(...)` 调用站点**——24 个站点的 `phase` 字符串恰好就是节点名（已验证）或 `"<name>_error"` 后缀（自动 fallback 处理）。

**Files:**
- Modify: `app/agent/nodes/_shared.py`
- Create: `tests/test_append_trace.py`

### 设计契约

```python
# 伪代码（实际见 Step 2.3）
def _append_trace(state, phase, data):
    label = phase
    payload = data
    try:
        meta, _fn = get_registry().get(phase)
        # 已注册节点：用 trace_label，按需脱敏
        label = meta.trace_label or phase
        if meta.sensitive:
            payload = sanitize_metadata(data)
    except KeyError:
        # 未注册的 phase（错误事件等）：保持原行为
        pass
    traces = state.get("branch_trace", [])
    traces.append({
        "phase": label,         # 注意：这里仍叫 phase；只是值变成 trace_label
        "timestamp": _get_timestamp(),
        **payload,
    })
    state["branch_trace"] = traces
```

**关键约束**：
- 仍写入 `phase` 这个 key，**不改**字段名。这样既有读取 `branch_trace[i]["phase"]` 的代码（如有）继续工作。
- `label` 取 `meta.trace_label`，回退到 `phase` 原值（防御性）。
- `sanitize_metadata` 已在 `app/monitoring/desensitize.py` 实现，仅过滤 `password/token/api_key/secret/credential/authorization/private_key/access_token` 8 个键，不会误伤业务字段（已 grep 24 个调用站点的 data dict 字段名，无一冲突）。

### 步骤

- [ ] **Step 2.1：写失败测试**

创建 `tests/test_append_trace.py`：

```python
"""验证 _append_trace 消费 NodeMeta 的 trace_label 与 sensitive 字段。"""
from app.agent.nodes._shared import _append_trace


def test_unknown_phase_preserves_legacy_behavior():
    """未注册节点名（如错误事件）保持原 phase 字段值。"""
    state = {}
    _append_trace(state, "rag_first_error", {"error_type": "timeout"})
    assert len(state["branch_trace"]) == 1
    entry = state["branch_trace"][0]
    assert entry["phase"] == "rag_first_error"
    assert entry["error_type"] == "timeout"
    assert "timestamp" in entry


def test_known_phase_uses_trace_label():
    """注册节点名：phase 字段被 trace_label 替换。"""
    state = {}
    _append_trace(state, "rag_first", {"rag_found": True})
    entry = state["branch_trace"][0]
    # rag_first 的 trace_label 是 "RAG First"
    assert entry["phase"] == "RAG First"
    # 业务数据原样传递
    assert entry["rag_found"] is True


def test_known_phase_without_label_falls_back_to_name():
    """如果某节点的 trace_label 为空（不存在的边界），回退到原 phase。"""
    from app.agent.node_decorator import node, get_node_meta

    @node(name="phase_no_label", trace_label="")  # trace_label 为空时，装饰器会回退为 name
    def n(state):
        return state

    # 装饰器内部 trace_label = trace_label or name，所以这里 label == "phase_no_label"
    state = {}
    _append_trace(state, "phase_no_label", {"foo": 1})
    entry = state["branch_trace"][0]
    assert entry["phase"] == "phase_no_label"
    assert entry["foo"] == 1


def test_sensitive_phase_redacts_known_secret_keys():
    """sensitive=True 的节点 trace 自动过滤敏感字段。"""
    from app.agent.node_decorator import node

    @node(name="auth_x", sensitive=True, trace_label="Auth X")
    def auth_node(state):
        return state

    state = {}
    _append_trace(state, "auth_x", {
        "user_id": 42,
        "api_key": "sk-leak",
        "password": "p@ss",
        "ok": True,
    })
    entry = state["branch_trace"][0]
    assert entry["phase"] == "Auth X"
    assert entry["user_id"] == 42
    assert entry["ok"] is True
    assert "api_key" not in entry
    assert "password" not in entry


def test_non_sensitive_phase_passes_payload_through():
    """sensitive=False 的节点，所有 data 字段都保留。"""
    state = {}
    _append_trace(state, "rag_first", {
        "rag_found": True,
        "api_key": "sk-NOT-actually-secret",  # 这里 sensitive=False，故不过滤
    })
    entry = state["branch_trace"][0]
    # rag_first 默认 sensitive=False，因此 api_key 保留
    assert entry["api_key"] == "sk-NOT-actually-secret"


def test_multiple_calls_accumulate_in_branch_trace():
    """连续调用累积。"""
    state = {}
    _append_trace(state, "rag_first", {"step": 1})
    _append_trace(state, "evidence_gate", {"step": 2})
    assert [e["phase"] for e in state["branch_trace"]] == ["RAG First", "Evidence Gate"]
```

- [ ] **Step 2.2：运行测试，确认失败**

```
cd "<worktree>" && PYTHONPATH=. uv run pytest tests/test_append_trace.py -v
```
Expected: 多数 FAIL（`test_known_phase_uses_trace_label` 等会失败，因为现在 `_append_trace` 写入的 `phase` 字段还是原始 `"rag_first"` 字符串）。

- [ ] **Step 2.3：修改 `_shared.py`**

读 `app/agent/nodes/_shared.py` 当前内容。把 `_append_trace` 函数替换为：

```python
def _append_trace(state: LearningState, phase: str, data: dict) -> None:
    """追加执行追踪。

    若 phase 是已注册的节点名：
      - 用 NodeMeta.trace_label 替换写入的 phase 字段值
      - 若 NodeMeta.sensitive=True，对 data 应用 sanitize_metadata 过滤敏感键
    若 phase 未注册（如 "<name>_error" 错误事件）：保持原行为。
    """
    label = phase
    payload = data
    try:
        from app.agent.node_registry import get_registry
        from app.monitoring.desensitize import sanitize_metadata
        meta, _fn = get_registry().get(phase)
        label = meta.trace_label or phase
        if meta.sensitive:
            payload = sanitize_metadata(data)
    except KeyError:
        # 未注册的 phase（如错误事件）：保持原 phase 与原 data
        pass

    traces = state.get("branch_trace", [])
    traces.append({
        "phase": label,
        "timestamp": _get_timestamp(),
        **payload,
    })
    state["branch_trace"] = traces
```

**纪律**：
- import 放在 try 内部（延迟 import），避免 `_shared.py` 与 `node_registry.py`/`monitoring` 之间形成意外的 import 环。
- 不改函数签名（仍是 `(state, phase, data)`），不改返回类型。
- 不动 `_get_timestamp` 与 `_rule_based_route`。

- [ ] **Step 2.4：运行新测试，确认通过**

```
cd "<worktree>" && PYTHONPATH=. uv run pytest tests/test_append_trace.py -v
```
Expected: 6/6 PASS。

- [ ] **Step 2.5：跑全量回归**

```
cd "<worktree>" && PYTHONPATH=. uv run pytest tests/ -q 2>&1 | tail -3
```
Expected: 203 + 6 = 209 PASS。

**预期可能的回归点**：如果某个既有测试断言 `state["branch_trace"][i]["phase"] == "rag_first"`（原始名），现在会拿到 `"RAG First"`（label）。先 grep：

```
grep -rn 'branch_trace.*phase' tests/ 2>&1 | head
```

若有命中，这是真实的语义回归——按现在的设计，需要决定：
- (a) 修改测试断言为 `trace_label` 值（推荐，保持 trace 表面一致性）
- (b) 把 trace 写入的字段名从 `phase` 改为 `trace_label`，新增字段而非替换（更保守但破坏字段简洁性）

**默认采用 (a)**——查到的测试一并 fix。如果触及测试很多（>5 个），停下来回报，可能要改成 (b)。

- [ ] **Step 2.6：提交**

```bash
git add app/agent/nodes/_shared.py tests/test_append_trace.py
# 若 step 2.5 修改了既有测试，一并 add 它们
git commit -m "feat(agent): _append_trace consumes NodeMeta.trace_label and sensitive flag"
```

---

## 任务 3：端到端验证 + 交付记录

**Files:**
- Create: `tests/test_phase6_e2e.py`
- Modify: `docs/superpowers/plans/011-2026-04-28-rag-agent-framework-evolution-phase6-plan.md`（追加交付记录）

### 步骤

- [ ] **Step 3.1：写 E2E**

创建 `tests/test_phase6_e2e.py`：

```python
"""Phase 6 端到端：图运行后 branch_trace 包含可读的 trace_label。"""
from unittest.mock import patch
from app.agent.graph_v2 import build_learning_graph_v2


def test_qa_direct_run_emits_human_readable_trace_labels():
    """成功路径下 branch_trace 中的 phase 字段是 trace_label（人类可读）。"""
    fake_rows = [
        {"chunk_id": f"c{i}", "score": 0.9 - i * 0.1,
         "text": f"什么是数据库索引：数据库索引内容 {i}"}
        for i in range(3)
    ]
    with patch("app.services.rag_coordinator.execute_retrieval_tools",
               return_value=(fake_rows, ["search_local_textbook"])), \
         patch("app.services.llm.llm_service.route_intent",
               return_value='{"intent":"qa_direct"}'), \
         patch("app.services.llm.llm_service.invoke", return_value="answer"):
        graph = build_learning_graph_v2()
        result = graph.invoke(
            {"session_id": "p6-1", "user_input": "请介绍数据库索引",
             "topic": "数据结构", "intent": "qa_direct"},
            config={"configurable": {"thread_id": "p6-1"}},
        )
    labels = [e["phase"] for e in result.get("branch_trace", [])]
    # 至少包含已注册节点的 trace_label
    assert "RAG First" in labels
    # 不应再出现原始 snake_case 节点名
    assert "rag_first" not in labels


def test_error_phase_preserves_legacy_string():
    """rag_first_error 这种非节点名的 phase 保持原值，不被改写。"""
    call_count = {"n": 0}

    def flaky(*a, **kw):
        call_count["n"] += 1
        raise TimeoutError("timed out")

    with patch("app.services.rag_coordinator.execute_retrieval_tools",
               side_effect=flaky), \
         patch("app.services.llm.llm_service.route_intent",
               return_value='{"intent":"qa_direct"}'), \
         patch("app.services.llm.llm_service.invoke", return_value="stub"):
        graph = build_learning_graph_v2()
        result = graph.invoke(
            {"session_id": "p6-2", "user_input": "什么是B+树",
             "topic": "数据结构", "intent": "qa_direct"},
            config={"configurable": {"thread_id": "p6-2"}},
        )
    labels = [e["phase"] for e in result.get("branch_trace", [])]
    # 至少有一次 rag_first_error 出现，且保留原字符串
    assert "rag_first_error" in labels


def test_invalid_retry_key_at_decoration_time():
    """运行时校验：未知 retry 字符串在装饰器调用时立刻抛错。"""
    import pytest
    from app.agent.node_decorator import node

    with pytest.raises(ValueError, match="retry"):
        @node(name="phase6_bad_node", retry="NONEXISTENT")
        def _x(state):
            return state
```

- [ ] **Step 3.2：跑 E2E**

```
cd "<worktree>" && PYTHONPATH=. uv run pytest tests/test_phase6_e2e.py -v
```
Expected: 3/3 PASS。

- [ ] **Step 3.3：跑全量回归**

```
cd "<worktree>" && PYTHONPATH=. uv run pytest tests/ -q 2>&1 | tail -3
```
Expected: **209 + 3 = 212 PASS**（基线 201 + Task 1 新增 2 + Task 2 新增 6 + Task 3 新增 3）。

- [ ] **Step 3.4：在计划文件追加交付记录**

打开 `docs/superpowers/plans/011-2026-04-28-rag-agent-framework-evolution-phase6-plan.md`，在文件末尾追加：

```markdown

---

## 交付记录

- **完成日期**：2026-04-28
- **分支**：`worktree-phase6-conventions-closure`
- **基于**：master 合并 Phase 5（HEAD `d73647a` 之后）
- **测试结果**：212 PASS / 0 FAIL（master 基线 201 + 本期新增 11）

### 提交清单

| SHA | 内容 |
|---|---|
| `<task1-sha>` | refactor(agent): tighten NodeMeta.retry_key with Literal and runtime validation |
| `<task2-sha>` | feat(agent): _append_trace consumes NodeMeta.trace_label and sensitive flag |
| `<task3-sha>` | test+docs: phase-6 E2E and delivery record |

### 验收清单

- [x] retry_key 类型收紧为 Literal，未知字符串运行时报错（任务 1）
- [x] `_append_trace` 通过 NodeRegistry 解析 trace_label 与 sensitive（任务 2）
- [x] 错误事件（`*_error` phase）保持向后兼容行为
- [x] 既有测试 0 回归（含必要的断言迁移）

### 关键设计决策

- **运行时校验冗余于 Literal**：Literal 仅在静态检查阶段生效；运行时未知字符串若不显式 raise，错误会延迟到 `add_to_graph` 才暴露。Phase 6 在装饰器内部加 `if retry not in _VALID_RETRY_KEYS: raise`，让错误立即可见。
- **`_append_trace` 的 try/except KeyError**：未注册 phase（如 `rag_first_error`）走原路径，保持向后兼容。这避免要求 24 个调用点都迁移。
- **延迟 import 避免循环**：`_shared.py` 在函数内部 import `node_registry` 与 `desensitize`，防止 `nodes/_shared.py` 与上层包形成 import 环。
- **trace 写入字段名仍叫 `phase`**：仅其 *value* 从 snake_case 节点名变成 `trace_label`。下游消费者代码无需感知字段重命名。

### 已知遗留（Phase 7+ 待办）

- `branch_trace` 仍是 state 内 list；未对接 Langfuse 实际上报（Langfuse `trace.span()` 需要在节点入/出口配对调用）
- `truncate_text` 已存在但未启用——Phase 6 不强制 trace 数据截断。Phase 7 开启 Langfuse 上报时一并接入。
- OrchestrationView / RecoveryView 仍未引入：等 RagView 真实使用扩展到第三个节点后再启动。
- 跨主题概念记忆 / 证据冲突检测 / `/chat/plan` 端点拆分：产品/协议性变更，各自独立 spec。
```

提交时把 `<task1-sha>`/`<task2-sha>`/`<task3-sha>` 用实际值替换。可在最后一次提交前用 `git rev-parse <commit>` 取出。

- [ ] **Step 3.5：分两次提交**

第一次（测试）：
```bash
git add tests/test_phase6_e2e.py
git commit -m "test(agent): phase-6 E2E for trace label propagation"
```

记录此 SHA，替换到交付记录中的 `<task3-sha>`。然后填入前两次的 SHA（用 `git log --oneline master..HEAD` 列出）。

第二次（文档）：
```bash
git add docs/superpowers/plans/011-2026-04-28-rag-agent-framework-evolution-phase6-plan.md
git commit -m "docs: phase-6 delivery record"
```

---

## 风险与回滚

| 风险 | 缓解 |
|---|---|
| `_append_trace` 增加 registry 查找开销 | registry 是 in-memory dict 查找，O(1)；24 个调用站点每会话最多触发一次/次，可忽略 |
| 既有测试断言 `branch_trace[i]["phase"] == "rag_first"` | Step 2.5 显式 grep 排查；命中 ≤5 时同 commit 修；>5 时回报、考虑改用新字段名 |
| `_VALID_RETRY_KEYS` 与 `retry_policy.py` 不同步漂移 | Phase 6 不引入 Enum；Phase 7 候选改为单一 source of truth（`retry_policy.RETRY_KEYS`） |
| Sensitive 节点目前没有（生产 17 节点全 `sensitive=False`） | 测试通过临时装饰节点（`auth_x`）覆盖；conftest 的 registry fixture 保证不污染其他测试 |

每任务独立提交，任意 revert 不影响其他任务。

---

## 后续阶段（不在本计划范围）

- **Phase 7（约定收尾末段）**：把 retry_policy.py 与 NodeMeta 的 retry_key 合并为单一 source；Langfuse trace 上报真接入；可选：truncate_text 启用。
- **Phase 8（产品能力）**：跨主题概念记忆、证据冲突检测——各需独立 spec（含 prompt 设计与离线评测）。
- **Phase 9（API 协议）**：`/chat/plan` & `/chat/execute` 端点拆分——需前端协调。

---

## 执行记录（2026-04-29）

- **执行人**：Copilot CLI
- **范围完成**：Task 1 / Task 2 / Task 3 全部完成
- **代码变更**：
  - `app/agent/node_decorator.py`
  - `app/agent/nodes/_shared.py`
  - `tests/test_node_decorator.py`
  - `tests/test_append_trace.py`（新增）
  - `tests/test_phase6_e2e.py`（新增）

### 测试结果

- **Phase 6 相关回归**：20 passed / 0 failed
  - `tests/test_phase6_e2e.py`
  - `tests/test_phase5_e2e_compat.py`
  - `tests/test_append_trace.py`
  - `tests/test_node_decorator.py`
- **全量测试套件**：259 passed / 19 failed（存在既有失败，主要集中在 `test_agent_replan_branch.py`、`test_chat_flow.py`、`test_sessions_api.py` 等；典型错误为测试 mock `fake_invoke()` 不接受 `stream_output` 参数）

### 验收状态

- [x] retry_key 类型收紧为 Literal，未知字符串在装饰阶段抛 `ValueError`
- [x] `_append_trace` 消费 `NodeMeta.trace_label` 与 `NodeMeta.sensitive`
- [x] `*_error` 事件 phase 保持原字符串（向后兼容）
- [x] 增加 Phase 6 E2E 验证 trace label 传播与错误路径兼容
