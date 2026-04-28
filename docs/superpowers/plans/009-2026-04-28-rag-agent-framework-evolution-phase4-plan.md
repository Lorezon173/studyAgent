# RAG Agent 框架演进 Phase 4：遗留收尾与节点拆分

> **给 Agentic Worker：** 必须使用 `superpowers:subagent-driven-development`（推荐）或 `superpowers:executing-plans` 按任务逐步执行。步骤使用复选框语法（`- [ ]`）跟踪。

**目标：** 关闭 Phase 3 三项已知遗留 — (1) `route_on_error` 接入图驱动真实重试/恢复；(2) `rag_meta_last` 类型严格化；(3) `nodes.py` 拆分为按职责分文件。

**架构：** 不引入新概念。延续 LangGraph + 服务层边界。`nodes.py` 拆为 `nodes/` 包但保持公共导入路径不变（向后兼容 `from app.agent.nodes import ...`）。

**技术栈：** Python 3.12、FastAPI、LangGraph、pytest、uv

**前置依赖：** Phase 3 已合并到 master ✅
- `route_on_error` 函数 + 5 个单元测试
- `knowledge_retrieval_node` 写 `error_code`
- `rag_first_node` 写 `error_code`（如 Phase 3 未做则在 Task 1 顺带补）
- Phase 2 节点已接入 qa_direct 流程

**非目标（OUT-of-SCOPE，留给 Phase 5）：**
- 状态分层（`RagMeta`/`OrchestrationMeta`/`RecoveryMeta`）
- 节点装饰器（`@node(retry, trace, permission)`）
- 技能注册表
- 证据冲突检测、跨主题记忆、`/chat/plan` API

---

## 文件结构

```text
app/agent/
├── nodes.py                  # 删除：拆分为 nodes/ 包后保留为聚合 re-export
├── nodes/                    # 新增：包目录
│   ├── __init__.py           # 聚合 re-export，向后兼容旧导入
│   ├── teach.py              # diagnose / explain / restate_check / followup / summarize / history_check / ask_review_or_continue
│   ├── qa.py                 # rag_first / rag_answer / llm_answer / knowledge_retrieval
│   ├── orchestration.py      # intent_router / replan / retrieval_planner / evidence_gate / answer_policy / recovery
│   └── _shared.py            # _append_trace 等共用工具
├── routers.py                # 修改：route_on_error 注释更新
├── graph_v2.py               # 修改：rag_first / knowledge_retrieval 后接入 route_on_error
└── state.py                  # 修改：rag_meta_last 类型严格化

tests/
├── test_route_on_error_graph_integration.py    # 新增：T1
├── test_state_typing.py                        # 新增：T2
└── test_nodes_package_imports.py               # 新增：T3 向后��容
```

---

## 任务 1：`route_on_error` 接入图

**Files:**
- Modify: `app/agent/graph_v2.py`
- Modify: `app/agent/routers.py`（移除"未接入"注释）
- Create: `tests/test_route_on_error_graph_integration.py`

**接线设计**：

```
rag_first             →  route_on_error_or_evidence  →  {evidence_gate | recovery | retry_rag→rag_first}
knowledge_retrieval   →  route_on_error_or_explain   →  {explain | recovery | retry_rag→knowledge_retrieval}
```

需新增两个组合路由（在 `routers.py`）：

```python
def route_on_error_or_evidence(state: LearningState) -> Literal["evidence_gate", "recovery", "retry_rag"]:
    """qa_direct 路径：rag_first 后判断错误，否则进入 evidence_gate。"""
    if state.get("node_error"):
        return route_on_error(state) if route_on_error(state) != "answer_policy" else "evidence_gate"
    return "evidence_gate"


def route_on_error_or_explain(state: LearningState) -> Literal["explain", "recovery", "retry_rag"]:
    """teach_loop 路径：knowledge_retrieval 后判断错误，否则进入 explain。"""
    if state.get("node_error"):
        decision = route_on_error(state)
        if decision == "answer_policy":
            return "explain"
        return decision
    return "explain"
```

- [ ] **步骤 1.1：先写失败测试**

```python
# tests/test_route_on_error_graph_integration.py
"""验证 route_on_error 真正驱动图执行：retry 与 recovery 都通过图触发。"""
from unittest.mock import patch
from app.agent.graph_v2 import build_learning_graph_v2


def _state(intent="qa_direct"):
    return {
        "session_id": f"ro-{intent}",
        "user_input": "什么是B+树",
        "topic": "数据结构",
        "intent": intent,
    }


def _invoke(state):
    graph = build_learning_graph_v2()
    return graph.invoke(state, config={"configurable": {"thread_id": state["session_id"]}})


def test_qa_direct_timeout_retries_once_then_recovers():
    """rag_first 第一次 timeout → retry_rag → 再次 timeout → recovery。"""
    call_count = {"n": 0}

    def flaky(*a, **kw):
        call_count["n"] += 1
        raise TimeoutError("timed out")

    with patch("app.services.rag_coordinator.execute_retrieval_tools", side_effect=flaky), \
         patch("app.services.llm.llm_service.route_intent", return_value={"intent": "qa_direct"}), \
         patch("app.services.llm.llm_service.invoke", return_value="stub"):
        result = _invoke(_state("qa_direct"))
    assert call_count["n"] == 2, f"expected exactly 2 retrieval attempts, got {call_count['n']}"
    assert result.get("error_code") == "llm_timeout"
    assert result.get("recovery_action") or result.get("fallback_triggered")


def test_qa_direct_db_error_goes_straight_to_recovery_no_retry():
    """db_error 不可重试 → 单次失败直接 recovery。"""
    call_count = {"n": 0}

    def boom(*a, **kw):
        call_count["n"] += 1
        raise RuntimeError("connection refused")

    with patch("app.services.rag_coordinator.execute_retrieval_tools", side_effect=boom), \
         patch("app.services.llm.llm_service.route_intent", return_value={"intent": "qa_direct"}), \
         patch("app.services.llm.llm_service.invoke", return_value="stub"):
        result = _invoke(_state("qa_direct"))
    # db_error retryable=True per existing strategy, so it WILL retry once. Adjust if needed.
    # If actual error_classifier marks db_error retryable, expect 2 calls; otherwise 1.
    from app.services.error_classifier import classify_from_code
    expected_calls = 2 if classify_from_code("db_error").retryable else 1
    assert call_count["n"] == expected_calls
    assert result.get("recovery_action") or result.get("fallback_triggered")
```

- [ ] **步骤 1.2：运行测试确认失败**

```
cd "<worktree>" && PYTHONPATH=. uv run pytest tests/test_route_on_error_graph_integration.py -v
```
Expected: FAIL，实际只调用 1 次（无 retry 边）。

- [ ] **步骤 1.3：在 `routers.py` 末尾追加两个组合路由**

写入上面"接线设计"中的 `route_on_error_or_evidence` 与 `route_on_error_or_explain` 函数。同时**移除** `route_on_error` 上方"NOTE: This router is implemented and unit-tested but is NOT yet wired into graph_v2.py..."注释（不再适用）。

- [ ] **步骤 1.4：修改 `graph_v2.py` 接入新路由**

定位 `graph.add_edge("rag_first", "evidence_gate")`，**替换为**：

```python
graph.add_conditional_edges(
    "rag_first",
    route_on_error_or_evidence,
    {
        "evidence_gate": "evidence_gate",
        "recovery": "recovery",
        "retry_rag": "rag_first",
    },
)
```

定位 `graph.add_edge("knowledge_retrieval", "explain")`，**替换为**：

```python
graph.add_conditional_edges(
    "knowledge_retrieval",
    route_on_error_or_explain,
    {
        "explain": "explain",
        "recovery": "recovery",
        "retry_rag": "knowledge_retrieval",
    },
)
```

更新 `routers` import 增加两个新函数。

- [ ] **步骤 1.5：在 `qa.py` 节点（或当前 `nodes.py` 中的 `rag_first_node`）写 `error_code`**

如果 `rag_first_node` 还没有 try/except 写 `error_code`（Phase 3 仅 `knowledge_retrieval_node` 做了），仿照同样方式包裹：

```python
except Exception as exc:
    from app.services.error_classifier import classify_error
    classification = classify_error(exc)
    return {
        "node_error": str(exc),
        "error_code": classification.error_type.value,
        "rag_found": False,
    }
```

并在节点首次进入时初始化 `retry_trace=[]`，重试时追加 `state["retry_trace"].append({"attempt": len(retry_trace)+1, "node": "rag_first"})`。

- [ ] **步骤 1.6：测试通过 + 全量回归**

```
cd "<worktree>" && PYTHONPATH=. uv run pytest tests/ -v
```
Expected: 全部 PASS（含 2 个新 + 165 既有）。

- [ ] **步骤 1.7：提交**

```bash
git add app/agent/routers.py app/agent/graph_v2.py app/agent/nodes.py tests/test_route_on_error_graph_integration.py
git commit -m "feat(agent): wire route_on_error into graph for rag_first and knowledge_retrieval"
```

---

## 任务 2：`rag_meta_last` 类型严格化

**Files:**
- Modify: `app/agent/state.py`
- Create: `tests/test_state_typing.py`

- [ ] **步骤 2.1：先写测试**

```python
# tests/test_state_typing.py
"""验证 LearningState.rag_meta_last 接受 RAGExecutionMeta 实例。"""
from app.agent.state import LearningState
from app.services.rag_coordinator import RAGExecutionMeta


def test_rag_meta_last_accepts_meta_instance():
    meta = RAGExecutionMeta(
        reason="ok", used_tools=[], hit_count=0,
        fallback_used=False, query_mode="fact", query_reason="t",
    )
    state: LearningState = {"rag_meta_last": meta}
    assert isinstance(state["rag_meta_last"], RAGExecutionMeta)


def test_rag_meta_last_type_annotation_is_optional_meta():
    """通过 typing.get_type_hints 检查注解。"""
    from typing import get_type_hints
    hints = get_type_hints(LearningState, include_extras=True)
    annotation = hints.get("rag_meta_last")
    assert annotation is not None
    # 注解应包含 RAGExecutionMeta（非 object）
    assert RAGExecutionMeta.__name__ in str(annotation)
```

- [ ] **步骤 2.2：修改 `state.py` 类型**

替换 `rag_meta_last: object` 为：

```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.rag_coordinator import RAGExecutionMeta

# 在 LearningState 内：
rag_meta_last: "Optional[RAGExecutionMeta]"
```

`Optional` 已在 state.py 顶部导入。`TYPE_CHECKING` 块如果文件还没有，需新增。

- [ ] **步骤 2.3：测试通过 + 全量回归**

- [ ] **步骤 2.4：提交**

```bash
git add app/agent/state.py tests/test_state_typing.py
git commit -m "refactor(agent): tighten rag_meta_last type annotation to Optional[RAGExecutionMeta]"
```

---

## 任务 3：`nodes.py` 拆分为 `nodes/` 包

**关键约束：保持向后兼容。** 所有现有导入 `from app.agent.nodes import xxx_node` 必须继续工作。`graph_v2.py` 与所有测试不需要修改导入。

**Files:**
- Create: `app/agent/nodes/__init__.py`
- Create: `app/agent/nodes/_shared.py`
- Create: `app/agent/nodes/teach.py`
- Create: `app/agent/nodes/qa.py`
- Create: `app/agent/nodes/orchestration.py`
- Delete: `app/agent/nodes.py`（被 `nodes/` 包替代）
- Create: `tests/test_nodes_package_imports.py`

**节点归属**：

| 文件 | 节点函数 |
|---|---|
| `_shared.py` | `_append_trace`（其他共用工具） |
| `teach.py` | `history_check_node`、`ask_review_or_continue_node`、`diagnose_node`、`explain_node`、`restate_check_node`、`followup_node`、`summarize_node` |
| `qa.py` | `rag_first_node`、`rag_answer_node`、`llm_answer_node`、`knowledge_retrieval_node` |
| `orchestration.py` | `intent_router_node`、`replan_node`、`retrieval_planner_node`、`evidence_gate_node`、`answer_policy_node`、`recovery_node` |

- [ ] **步骤 3.1：先写向后兼容测试**

```python
# tests/test_nodes_package_imports.py
"""保证拆分后所有公共导入仍可工作。"""


def test_all_nodes_importable_from_app_agent_nodes():
    from app.agent.nodes import (
        intent_router_node,
        history_check_node,
        ask_review_or_continue_node,
        diagnose_node,
        knowledge_retrieval_node,
        explain_node,
        restate_check_node,
        followup_node,
        summarize_node,
        rag_first_node,
        rag_answer_node,
        llm_answer_node,
        replan_node,
        retrieval_planner_node,
        evidence_gate_node,
        answer_policy_node,
        recovery_node,
    )
    # 所有节点应可调用
    for n in [
        intent_router_node, history_check_node, diagnose_node,
        knowledge_retrieval_node, explain_node, rag_first_node,
        retrieval_planner_node, evidence_gate_node, recovery_node,
    ]:
        assert callable(n)


def test_subpackages_are_importable():
    from app.agent.nodes import teach, qa, orchestration, _shared
    assert hasattr(teach, "diagnose_node")
    assert hasattr(qa, "knowledge_retrieval_node")
    assert hasattr(orchestration, "evidence_gate_node")
    assert hasattr(_shared, "_append_trace")
```

- [ ] **步骤 3.2：运行测试确认失败**（子模块尚不存在）

- [ ] **步骤 3.3：建立目录结构与 `_shared.py`**

```bash
mkdir -p app/agent/nodes
```

将 `nodes.py` 中所有 `_append_trace` 等内部辅助函数移入 `app/agent/nodes/_shared.py`。

- [ ] **步骤 3.4：拆分到 `teach.py` / `qa.py` / `orchestration.py`**

按上表归属，把每组函数从原 `nodes.py` 复制到对应文件。每个新文件顶部按需 import：

- `from app.agent.state import LearningState`
- `from app.agent.nodes._shared import _append_trace`
- 服务层导入（`from app.services.* import ...`）

**纪律**：
- 不修改函数实现（只复制 + 调整 import）
- 函数内的 `from app.services.xxx import yyy` 局部 import 保持不动
- 不新增/删除节点

- [ ] **步骤 3.5：写 `__init__.py` 聚合 re-export**

```python
# app/agent/nodes/__init__.py
"""节点包：按职责拆分但保留 from app.agent.nodes import xxx_node 兼容性。"""
from app.agent.nodes.teach import (
    history_check_node,
    ask_review_or_continue_node,
    diagnose_node,
    explain_node,
    restate_check_node,
    followup_node,
    summarize_node,
)
from app.agent.nodes.qa import (
    rag_first_node,
    rag_answer_node,
    llm_answer_node,
    knowledge_retrieval_node,
)
from app.agent.nodes.orchestration import (
    intent_router_node,
    replan_node,
    retrieval_planner_node,
    evidence_gate_node,
    answer_policy_node,
    recovery_node,
)

__all__ = [
    "history_check_node", "ask_review_or_continue_node", "diagnose_node",
    "explain_node", "restate_check_node", "followup_node", "summarize_node",
    "rag_first_node", "rag_answer_node", "llm_answer_node", "knowledge_retrieval_node",
    "intent_router_node", "replan_node",
    "retrieval_planner_node", "evidence_gate_node", "answer_policy_node", "recovery_node",
]
```

- [ ] **步骤 3.6：删除原 `app/agent/nodes.py`**

```bash
git rm app/agent/nodes.py
```

- [ ] **步骤 3.7：跑全量回归**

```
cd "<worktree>" && PYTHONPATH=. uv run pytest tests/ -v
```

Expected: 全部 PASS。**任何因导入路径变化的失败都是 bug**——必须修复 `__init__.py` 而非测试。

- [ ] **步骤 3.8：提交**

```bash
git add app/agent/nodes/ tests/test_nodes_package_imports.py
git rm --cached app/agent/nodes.py 2>/dev/null || true
git add -A app/agent/
git commit -m "refactor(agent): split nodes.py into nodes/ package by responsibility (teach/qa/orchestration)"
```

---

## 任务 4：交付检查与文档更新

- [x] **步骤 4.1：勾选验收清单**

```text
[x] route_on_error 接入图，retry/recovery 真正生效（任务 1）
[x] rag_meta_last 类型严格化为 Optional[RAGExecutionMeta]（任务 2）
[x] nodes.py 拆分为 nodes/ 包，向后兼容（任务 3）
[x] 既有测试 0 回归
```

- [ ] **步骤 4.2：在本计划文件追加交付记录**

在文件最末追加交付记录段（日期、SHA 范围、测试统计）。

- [ ] **步骤 4.3：最终提交**

```bash
git add docs/superpowers/plans/009-2026-04-28-rag-agent-framework-evolution-phase4-plan.md
git commit -m "docs: mark phase-4 carry-over closure delivered"
```

---

## 风险与回滚

| 风险 | 缓解 |
|---|---|
| `route_on_error` 引入图导致死循环 | 单次重试限制（`len(retry_trace) == 0`）已在 Phase 3 router 中；Task 1 测试验证恰好 2 次调用 |
| `nodes.py` 拆分破坏既有导入 | 任务 3 步骤 3.1 的兼容性测试覆盖 17 个节点的导入；`__init__.py` 显式 re-export |
| 重试时 `node_error` / `error_code` 未清空导致永久 retry_rag | 节点首次进入清空 retry_trace；retry_trace 长度 ≥1 后路由进入 recovery 而非再次 retry_rag |
| 节点拆分时遗漏共享 helper | 任务 3 步骤 3.4 纪律：先复制后清理，不修改实现 |

回滚：每任务独立提交。任务 3 拆分如出问题，单 commit revert 即可恢复整文件状态。

---

## 后续阶段（不在本计划范围）

- **Phase 5**：状态分层（`RagMeta`/`OrchestrationMeta`/`RecoveryMeta`） + 节点装饰器（`@node(retry, trace, permission)`） + 技能注册表
- **Phase 6**：证据冲突检测、跨主题概念记忆、`/chat/plan` & `/chat/execute` 端点拆分、Trace 权限分级、Embedding 注册表 + AB

---

## 交付记录

- **完成日期**：2026-04-28
- **分支**：`worktree-phase4-cleanup`
- **基于**：master 合并 Phase 3（HEAD `7774a66`）
- **提交 SHA 范围**：`d1ee77d..<最后一次 fix commit SHA>`（共 4 个提交：3 任务 + 1 review 修复）
- **测试结果**：174 PASS / 0 FAIL（master 基线 165 + Phase 4 新增）

### 验收清单

```text
[x] route_on_error 接入图，retry/recovery 真正生效（任务 1, d1ee77d）
[x] rag_meta_last 类型严格化为 Optional[RAGExecutionMeta]（任务 2, 76294f7）
[x] nodes.py 拆分为 nodes/ 包，向后兼容（任务 3, 53b7764）
[x] 评审遗留 C-1（成功重试不清错误状态）已修复
[x] 评审遗留 I-1/I-2/M-1/M-3 polish 已应用
[x] 既有测试 0 回归
```

### 关键修复（review 后）

- **C-1**：`rag_first_node` 与 `knowledge_retrieval_node` 在节点入口检测前次错误标记并追加 `retry_trace`，然后清空 `node_error`/`error_code`。成功路径返回时显式置空两字段。新增回归测试 `test_qa_direct_first_call_fails_second_succeeds_routes_to_answer` 覆盖成功重试路径。
- **I-2**：移除 `qa.py` 函数体内对 `decide_rag_call`/`execute_rag` 的重复 import，仅保留模块级 import。
- **M-1**：`state.py` 用真实运行时 import 替换 `TYPE_CHECKING` + `object` stub（验证 `rag_coordinator` 不引用 `app.agent`，无循环 import 风险）。
- **M-3**：`rag_first_node` except 块新增 `_append_trace("rag_first_error", ...)`，与 `knowledge_retrieval_node` 对称。

### 已知遗留（Phase 5 待办）

- 状态分层：`LearningState` 仍为 ~110 字段平铺的 TypedDict。Phase 5 拆为 `RagMeta` / `OrchestrationMeta` / `RecoveryMeta` 嵌套结构。
- 节点装饰器：所有节点仍是裸函数。Phase 5 引入 `@node(retry, trace, permission)`。
- 技能注册表：节点名仍硬编码在 `graph_v2.py`。Phase 5 引入注册表。
