# RAG Agent 框架演进 Phase 5：约定显式化（State 视图、节点装饰器、技能注册表）

> **给 Agentic Worker：** 必须使用 `superpowers:subagent-driven-development`（推荐）或 `superpowers:executing-plans` 按任务逐步执行。步骤使用复选框语法（`- [ ]`）跟踪。

**Goal:** 把当前散布在节点函数里的三类隐式约定显式化：(1) 状态字段分组与读写约束；(2) 节点重试/追踪/权限元数据；(3) 节点名到实现的绑定关系。

**Architecture:** **不**改变 LangGraph 的扁平 TypedDict 存储。新增三层薄封装：`StateView` 作为类型化读写门面、`@node` 装饰器收敛横切关注点、`NodeRegistry` 作为名称查找表。每层都对原有调用方向后兼容，旧 `state["xxx"]` 读写继续可用。**严禁一次性重写所有节点**。

**Tech Stack:** Python 3.12、FastAPI、LangGraph、pytest、uv

**前置依赖：** Phase 4 已合并到 master ✅
- `app/agent/nodes/` 包结构已存在（teach/qa/orchestration/_shared）
- `LearningState` 字段定义齐全（~35 字段，扁平 TypedDict）
- `route_on_error_or_evidence` / `route_on_error_or_explain` 已接入图

**非目标（OUT-of-SCOPE，留给 Phase 6）：**
- 不把 `LearningState` 改成嵌套 dict（嵌套会破坏 LangGraph reducer，已确认风险）
- 不实现 `/chat/plan` API、跨主题记忆、证据冲突检测
- 不改变现有节点的业务逻辑
- 不替换 LangGraph 的内置 retry（保留 `RetryPolicy`，装饰器只补充其外的 trace/permission）

**Scope 警告：** 如果 Task 1（StateView 引入）实施中暴露 LangGraph reducer 不兼容（例如 dataclass 写回时被序列化），**立即停止后续任务**，把 Tasks 2-3 拆为独立计划。Tasks 2、3 不依赖 Task 1 的字段嵌套，因此可独立交付。

---

## File Structure

```text
app/agent/
├── state.py                    # 修改：保留 TypedDict + 新增分组常量
├── state_view.py               # 新增：RagView 类型化访问门面（其他 View 留给 Phase 6）
├── node_decorator.py           # 新增：@node(name, retries, traces, permissions)
├── node_registry.py            # 新增：NodeRegistry 单例 + register_node()
├── nodes/
│   ├── _shared.py              # 修改：导出 StateView / @node 别名（避免每个节点重复 import）
│   ├── teach.py                # 修改：以 @node 标注；保留实现
│   ├── qa.py                   # 修改：以 @node 标注；rag_first / knowledge_retrieval 改用 RagView
│   └── orchestration.py        # 修改：以 @node 标注；evidence_gate 改用 OrchestrationView 验收点
├── graph_v2.py                 # 修改：从 NodeRegistry 解析节点而非硬编码 import
└── routers.py                  # 不变

tests/
├── test_state_view.py                  # 新增：T1
├── test_node_decorator.py              # 新增：T2
├── test_node_registry.py               # 新增：T3
├── test_phase5_e2e_compat.py           # 新增：T4 端到端验证旧调用未破坏
└── test_phase5_observability.py        # 新增：T5 验证 trace 元数据落地
```

---

## 范围分解概览

| 任务 | 引入物 | 风险 | 节点改动数 |
|---|---|---|---|
| Task 1 | `StateView` | 中（覆盖面广但纯封装） | 2 个节点（rag_first, knowledge_retrieval）试点 |
| Task 2 | `@node` 装饰器 | 低（薄装饰，可禁用） | 17 个节点全标注（不改实现） |
| Task 3 | `NodeRegistry` | 低（注册由装饰器自动完成） | 1 处图构建改造 |
| Task 4 | E2E 与文档 | 极低 | 0 |

每个任务**独立可合并**。Task 2、3 不依赖 Task 1。

---

## 任务 1：引入 StateView 类型化访问门面

**目标：** 为 RAG 相关字段族（最复杂的一组）提供一个类型化读写门面。**不替换** state dict，只新增一个面向开发者的便利层。先在 2 个节点试点验证可用性，再决定 Phase 6 是否扩展到全部分组。

**Files:**
- Create: `app/agent/state_view.py`
- Modify: `app/agent/nodes/qa.py`（仅 `rag_first_node`、`knowledge_retrieval_node` 改用 RagView）
- Create: `tests/test_state_view.py`

### 设计契约

`RagView` 是无状态的字段访问类。构造时接受一个 `LearningState`，所有 setter 直接写回原 dict（**不复制**）。所有 getter 带显式默认值。这样既向后兼容旧的 `state["rag_found"]` 读写，又给新代码一条类型清晰的路径。

```python
# app/agent/state_view.py 完整内容
"""LearningState 的类型化访问视图。

视图不持有独立状态；构造时接收一个 LearningState dict，
读写直接落到原 dict。这避免了 LangGraph reducer 的兼容性问题，
同时为开发者提供清晰的字段分组与默认值。

Phase 5 引入 RagView / OrchestrationView / RecoveryView 三个视图。
后续 phase 视情况扩展或不扩展。
"""
from __future__ import annotations

from typing import Any, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from app.agent.state import LearningState
    from app.services.rag_coordinator import RAGExecutionMeta


class RagView:
    """RAG 字段族的类型化访问门面。

    覆盖字段：rag_found, rag_context, rag_citations, rag_confidence_level,
    rag_low_evidence, rag_avg_score, rag_meta_last。
    """

    __slots__ = ("_state",)

    def __init__(self, state: "LearningState") -> None:
        self._state = state

    # ---- 读取 ----
    @property
    def found(self) -> bool:
        return bool(self._state.get("rag_found", False))

    @property
    def context(self) -> str:
        return str(self._state.get("rag_context", ""))

    @property
    def citations(self) -> List[dict]:
        return list(self._state.get("rag_citations", []) or [])

    @property
    def confidence_level(self) -> str:
        return str(self._state.get("rag_confidence_level", "low"))

    @property
    def low_evidence(self) -> bool:
        return bool(self._state.get("rag_low_evidence", True))

    @property
    def avg_score(self) -> float:
        return float(self._state.get("rag_avg_score", 0.0))

    @property
    def meta_last(self) -> "Optional[RAGExecutionMeta]":
        return self._state.get("rag_meta_last")

    # ---- 写入 ----
    def reset(self) -> None:
        """初始化所有 RAG 字段到默认值。"""
        self._state["rag_found"] = False
        self._state["rag_context"] = ""
        self._state["rag_citations"] = []
        self._state["rag_confidence_level"] = "low"
        self._state["rag_low_evidence"] = True
        self._state["rag_avg_score"] = 0.0

    def record_hit(
        self,
        *,
        context: str,
        citations: List[dict],
        avg_score: float,
        confidence_level: str,
        meta: "Optional[RAGExecutionMeta]" = None,
    ) -> None:
        """记录一次成功命中。"""
        self._state["rag_found"] = True
        self._state["rag_context"] = context
        self._state["rag_citations"] = citations
        self._state["rag_avg_score"] = avg_score
        self._state["rag_confidence_level"] = confidence_level
        self._state["rag_low_evidence"] = confidence_level == "low"
        if meta is not None:
            self._state["rag_meta_last"] = meta

    def record_meta(self, meta: "Optional[RAGExecutionMeta]") -> None:
        """单独记录 meta，用于在命中前先存元数据。"""
        if meta is not None:
            self._state["rag_meta_last"] = meta

    def to_return_dict(self) -> dict[str, Any]:
        """构造 LangGraph 节点应返回的 dict（仅包含 RAG 字段族）。"""
        return {
            "rag_found": self.found,
            "rag_context": self.context,
            "rag_citations": self.citations,
            "rag_confidence_level": self.confidence_level,
            "rag_low_evidence": self.low_evidence,
            "rag_avg_score": self.avg_score,
            "rag_meta_last": self.meta_last,
        }


__all__ = ["RagView"]
```

> **关于 OrchestrationView / RecoveryView**：本任务**不实现**它们。Task 1 验证 RagView 模式后再决定是否扩展。这避免一次性 commit 三套视图却没人用。

### 步骤

- [ ] **Step 1.1: 写失败测试**

```python
# tests/test_state_view.py
"""验证 RagView 读写直接落到原 state dict（无独立状态）。"""
from app.agent.state_view import RagView


def test_ragview_read_default_when_state_empty():
    state = {}
    view = RagView(state)
    assert view.found is False
    assert view.context == ""
    assert view.citations == []
    assert view.confidence_level == "low"
    assert view.low_evidence is True
    assert view.avg_score == 0.0
    assert view.meta_last is None


def test_ragview_read_existing_values():
    state = {
        "rag_found": True,
        "rag_context": "B+ tree definition",
        "rag_citations": [{"source": "textbook", "score": 0.9}],
        "rag_confidence_level": "high",
        "rag_low_evidence": False,
        "rag_avg_score": 0.85,
    }
    view = RagView(state)
    assert view.found is True
    assert view.context == "B+ tree definition"
    assert view.citations == [{"source": "textbook", "score": 0.9}]
    assert view.confidence_level == "high"
    assert view.low_evidence is False
    assert view.avg_score == 0.85


def test_ragview_reset_writes_defaults_into_state():
    state = {"rag_found": True, "rag_context": "stale", "rag_avg_score": 0.5}
    view = RagView(state)
    view.reset()
    assert state["rag_found"] is False
    assert state["rag_context"] == ""
    assert state["rag_avg_score"] == 0.0
    assert state["rag_low_evidence"] is True


def test_ragview_record_hit_sets_all_fields():
    state = {}
    view = RagView(state)
    view.record_hit(
        context="ctx",
        citations=[{"source": "a", "score": 0.7}],
        avg_score=0.7,
        confidence_level="medium",
    )
    assert state["rag_found"] is True
    assert state["rag_context"] == "ctx"
    assert state["rag_citations"] == [{"source": "a", "score": 0.7}]
    assert state["rag_avg_score"] == 0.7
    assert state["rag_confidence_level"] == "medium"
    assert state["rag_low_evidence"] is False  # medium → not low


def test_ragview_record_hit_low_confidence_marks_low_evidence():
    state = {}
    view = RagView(state)
    view.record_hit(
        context="ctx",
        citations=[],
        avg_score=0.2,
        confidence_level="low",
    )
    assert state["rag_low_evidence"] is True


def test_ragview_to_return_dict_matches_state_keys():
    state = {
        "rag_found": True,
        "rag_context": "x",
        "rag_citations": [{"s": 1}],
        "rag_confidence_level": "high",
        "rag_low_evidence": False,
        "rag_avg_score": 0.9,
        "rag_meta_last": None,
    }
    view = RagView(state)
    out = view.to_return_dict()
    assert set(out.keys()) == {
        "rag_found", "rag_context", "rag_citations",
        "rag_confidence_level", "rag_low_evidence", "rag_avg_score",
        "rag_meta_last",
    }
    assert out["rag_context"] == "x"


def test_ragview_record_meta_stores_meta_only():
    """记录 meta 不应触发命中状态。"""
    from app.services.rag_coordinator import RAGExecutionMeta
    state = {}
    view = RagView(state)
    meta = RAGExecutionMeta(
        reason="ok", used_tools=[], hit_count=0,
        fallback_used=False, query_mode="fact", query_reason="t",
    )
    view.record_meta(meta)
    assert state["rag_meta_last"] is meta
    assert state.get("rag_found") is None  # 未触碰 found
```

- [ ] **Step 1.2: 运行测试确认失败**

```
cd "<worktree>" && PYTHONPATH=. uv run pytest tests/test_state_view.py -v
```
Expected: `ModuleNotFoundError: app.agent.state_view`

- [ ] **Step 1.3: 创建 `app/agent/state_view.py`**

按上文"完整内容"段落写入文件。**不要新增 OrchestrationView / RecoveryView**。

- [ ] **Step 1.4: 运行测试确认通过**

```
cd "<worktree>" && PYTHONPATH=. uv run pytest tests/test_state_view.py -v
```
Expected: 7/7 PASS

- [ ] **Step 1.5: 在 `rag_first_node` 中试点替换字段访问**

打开 `app/agent/nodes/qa.py`，把 `rag_first_node` 中的 RAG 字段读写换成 `RagView`，但**保留所有非 RAG 字段读写、错误处理、retry_trace 逻辑、return dict 形状不变**。

具体替换（仅展示关键差异，原函数其他部分不动）：

替换原文 `qa.py:26-31`：

```python
state["rag_found"] = False
state["rag_context"] = ""
state["rag_citations"] = []
state["rag_confidence_level"] = "low"
state["rag_low_evidence"] = True
state["rag_avg_score"] = 0.0
```

为：

```python
from app.agent.state_view import RagView
rag = RagView(state)
rag.reset()
```

替换原文 `qa.py:64-86`（命中分支）：

```python
if rows:
    context_parts = []
    citations = []
    for row in rows:
        content = row.get("text", "")
        if content:
            context_parts.append(content)
        citations.append({
            "source": row.get("source", "unknown"),
            "score": row.get("score", 0),
        })
    state["rag_context"] = "\n\n".join(context_parts)
    state["rag_citations"] = citations
    state["rag_found"] = True
    scores = [float(row.get("score", 0.0)) for row in rows]
    avg_score = sum(scores) / len(scores) if scores else 0.0
    state["rag_avg_score"] = avg_score
    if len(rows) >= 2 and avg_score >= 0.7:
        state["rag_confidence_level"] = "high"
        state["rag_low_evidence"] = False
    elif len(rows) >= 1 and avg_score >= 0.45:
        state["rag_confidence_level"] = "medium"
        state["rag_low_evidence"] = False
```

为：

```python
if rows:
    context_parts: list[str] = []
    citations: list[dict] = []
    for row in rows:
        content = row.get("text", "")
        if content:
            context_parts.append(content)
        citations.append({
            "source": row.get("source", "unknown"),
            "score": row.get("score", 0),
        })
    scores = [float(row.get("score", 0.0)) for row in rows]
    avg_score = sum(scores) / len(scores) if scores else 0.0
    if len(rows) >= 2 and avg_score >= 0.7:
        confidence = "high"
    elif len(rows) >= 1 and avg_score >= 0.45:
        confidence = "medium"
    else:
        confidence = "low"
    rag.record_hit(
        context="\n\n".join(context_parts),
        citations=citations,
        avg_score=avg_score,
        confidence_level=confidence,
    )
```

`state["rag_meta_last"] = meta`（原 `qa.py:62`）替换为：

```python
rag.record_meta(meta)
```

**不要修改成功路径的 return dict**——原 `return {"rag_found": ..., "rag_context": ..., ...}` 字段及顺序保持不变。RagView 只是辅助写入，不替换 LangGraph 的 dict-based merge。

- [ ] **Step 1.6: 运行 qa 节点相关测试**

```
cd "<worktree>" && PYTHONPATH=. uv run pytest tests/ -v -k "rag or qa or knowledge" 2>&1 | tail -40
```
Expected: 全部 PASS（覆盖 rag_first / knowledge_retrieval 行为的既有测试）

- [ ] **Step 1.7: 在 `knowledge_retrieval_node` 中做同样替换**

按 Step 1.5 同样的方式处理 `knowledge_retrieval_node`：把 `state["retrieved_context"] = ""` 与 `state["citations"] = []` 保持原状（这两个字段不属于 RAG view 的范围；只有 `rag_meta_last` 用 `rag.record_meta(meta)` 替换）。

- [ ] **Step 1.8: 全量回归**

```
cd "<worktree>" && PYTHONPATH=. uv run pytest tests/ -q 2>&1 | tail -3
```
Expected: 174 PASS（基线）+ 7 新增 = **181 PASS**

- [ ] **Step 1.9: 提交**

```bash
git add app/agent/state_view.py app/agent/nodes/qa.py tests/test_state_view.py
git commit -m "feat(agent): introduce RagView typed access facade; pilot in qa nodes"
```

---

## 任务 2：节点装饰器 `@node`

**目标：** 把节点的元数据（名称、retry policy、trace 标签、是否敏感）从 `graph_v2.py` 的 `add_node(...)` 调用现场提取到节点定义点。装饰器**不改变运行时行为**——它只是把元数据贴到函数对象上，由 Task 3 的 NodeRegistry 消费。

**Files:**
- Create: `app/agent/node_decorator.py`
- Modify: `app/agent/nodes/teach.py`、`qa.py`、`orchestration.py`（仅添加装饰器，不改实现）
- Create: `tests/test_node_decorator.py`

### 设计契约

```python
# app/agent/node_decorator.py 完整内容
"""节点装饰器：把节点元数据贴到函数对象上，由 NodeRegistry 消费。

@node 不改变函数签名或运行时行为；它只是注入元数据。
LangGraph 的 retry_policy 仍由 graph_v2.py 通过 add_node 配置——
但 add_node 调用现在从 registry 解析 (name, fn, retry)，
而不是手写硬编码节点名。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional, Any


@dataclass(frozen=True)
class NodeMeta:
    """节点元数据。"""
    name: str
    retry_key: Optional[str] = None  # "LLM_RETRY" / "RAG_RETRY" / "DB_RETRY" / None
    trace_label: str = ""
    sensitive: bool = False  # True 表示 trace 时需要脱敏
    tags: tuple[str, ...] = field(default_factory=tuple)


_REGISTRY_KEY = "__node_meta__"


def node(
    *,
    name: str,
    retry: Optional[str] = None,
    trace_label: str = "",
    sensitive: bool = False,
    tags: tuple[str, ...] = (),
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """节点装饰器。

    Args:
        name: 节点在图中的名称（必须）
        retry: 重试策略键 — "LLM_RETRY" / "RAG_RETRY" / "DB_RETRY" 或 None
        trace_label: 用于可观测性的人类可读标签
        sensitive: 是否包含敏感数据，trace 时需脱敏
        tags: 自由分类标签
    """
    meta = NodeMeta(
        name=name,
        retry_key=retry,
        trace_label=trace_label or name,
        sensitive=sensitive,
        tags=tags,
    )

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        setattr(fn, _REGISTRY_KEY, meta)
        # 同时注册到全局 registry（Task 3 使用）
        from app.agent.node_registry import _registry_instance
        _registry_instance.register(meta, fn)
        return fn

    return decorator


def get_node_meta(fn: Callable[..., Any]) -> Optional[NodeMeta]:
    """读取已装饰函数的元数据。"""
    return getattr(fn, _REGISTRY_KEY, None)


__all__ = ["NodeMeta", "node", "get_node_meta"]
```

### 步骤

- [ ] **Step 2.1: 写失败测试**

```python
# tests/test_node_decorator.py
"""验证 @node 装饰器把元数据贴到函数对象上。"""
import pytest
from app.agent.node_decorator import node, get_node_meta, NodeMeta


def test_node_decorator_attaches_meta():
    @node(name="hello", retry="LLM_RETRY", trace_label="Hello")
    def my_node(state):
        return state

    meta = get_node_meta(my_node)
    assert isinstance(meta, NodeMeta)
    assert meta.name == "hello"
    assert meta.retry_key == "LLM_RETRY"
    assert meta.trace_label == "Hello"
    assert meta.sensitive is False
    assert meta.tags == ()


def test_node_decorator_defaults():
    @node(name="bare")
    def bare_node(state):
        return state

    meta = get_node_meta(bare_node)
    assert meta.name == "bare"
    assert meta.retry_key is None
    assert meta.trace_label == "bare"  # defaults to name
    assert meta.sensitive is False


def test_node_decorator_sensitive_flag():
    @node(name="auth", sensitive=True, tags=("user_data",))
    def auth_node(state):
        return state

    meta = get_node_meta(auth_node)
    assert meta.sensitive is True
    assert meta.tags == ("user_data",)


def test_node_decorator_does_not_change_runtime_behavior():
    """装饰器透传调用，不修改 state。"""
    @node(name="passthrough")
    def passthrough(state):
        return {"echo": state.get("input")}

    result = passthrough({"input": "hi"})
    assert result == {"echo": "hi"}


def test_undecorated_function_returns_none_meta():
    def plain(state):
        return state
    assert get_node_meta(plain) is None
```

- [ ] **Step 2.2: 运行测试确认失败**

```
cd "<worktree>" && PYTHONPATH=. uv run pytest tests/test_node_decorator.py -v
```
Expected: ModuleNotFoundError

- [ ] **Step 2.3: 创建装饰器**

按上文"完整内容"写 `app/agent/node_decorator.py`。**注意**：装饰器内部 `from app.agent.node_registry import _registry_instance` 是延迟导入——避免 Task 2 单独存在时（Task 3 还没建 registry）报错。但因为 Task 2、3 在同一计划中，我们建议**先建 registry stub**：

先创建 `app/agent/node_registry.py` 最小桩（Task 3 会扩充）：

```python
# app/agent/node_registry.py
"""节点名 → 实现的注册表。Task 3 扩充。"""
from __future__ import annotations

from typing import Callable, Dict, TYPE_CHECKING

if TYPE_CHECKING:
    from app.agent.node_decorator import NodeMeta


class NodeRegistry:
    """节点注册表单例。"""

    def __init__(self) -> None:
        self._nodes: Dict[str, tuple["NodeMeta", Callable]] = {}

    def register(self, meta: "NodeMeta", fn: Callable) -> None:
        if meta.name in self._nodes:
            existing_meta, _ = self._nodes[meta.name]
            if existing_meta is not meta:
                raise ValueError(
                    f"Node '{meta.name}' already registered with different metadata"
                )
        self._nodes[meta.name] = (meta, fn)

    def get(self, name: str) -> tuple["NodeMeta", Callable]:
        if name not in self._nodes:
            raise KeyError(f"Node '{name}' not registered")
        return self._nodes[name]

    def all(self) -> Dict[str, tuple["NodeMeta", Callable]]:
        return dict(self._nodes)

    def clear(self) -> None:
        """仅供测试使用。"""
        self._nodes.clear()


_registry_instance = NodeRegistry()


def get_registry() -> NodeRegistry:
    return _registry_instance


__all__ = ["NodeRegistry", "get_registry"]
```

- [ ] **Step 2.4: 运行测试确认通过**

```
cd "<worktree>" && PYTHONPATH=. uv run pytest tests/test_node_decorator.py -v
```
Expected: 5/5 PASS

- [ ] **Step 2.5: 给所有 17 个节点贴装饰器**

打开三个节点文件，在每个节点函数定义上方加装饰器（不改函数体）。**节点名必须与现有 `graph_v2.py` 的 `add_node` 调用名一致**——以下表格为权威映射。

| 文件 | 函数 | name | retry | trace_label |
|---|---|---|---|---|
| `nodes/orchestration.py` | `intent_router_node` | `intent_router` | `LLM_RETRY` | `Intent Router` |
| `nodes/orchestration.py` | `replan_node` | `replan` | `LLM_RETRY` | `Replan` |
| `nodes/orchestration.py` | `retrieval_planner_node` | `retrieval_planner` | None | `Retrieval Planner` |
| `nodes/orchestration.py` | `evidence_gate_node` | `evidence_gate` | None | `Evidence Gate` |
| `nodes/orchestration.py` | `answer_policy_node` | `answer_policy` | None | `Answer Policy` |
| `nodes/orchestration.py` | `recovery_node` | `recovery` | None | `Recovery` |
| `nodes/teach.py` | `history_check_node` | `history_check` | `DB_RETRY` | `History Check` |
| `nodes/teach.py` | `ask_review_or_continue_node` | `ask_review_or_continue` | None | `Ask Review or Continue` |
| `nodes/teach.py` | `diagnose_node` | `diagnose` | `LLM_RETRY` | `Diagnose` |
| `nodes/teach.py` | `explain_node` | `explain` | `LLM_RETRY` | `Explain` |
| `nodes/teach.py` | `restate_check_node` | `restate_check` | `LLM_RETRY` | `Restate Check` |
| `nodes/teach.py` | `followup_node` | `followup` | `LLM_RETRY` | `Followup` |
| `nodes/teach.py` | `summarize_node` | `summary` | `LLM_RETRY` | `Summary` |
| `nodes/qa.py` | `rag_first_node` | `rag_first` | `RAG_RETRY` | `RAG First` |
| `nodes/qa.py` | `rag_answer_node` | `rag_answer` | `LLM_RETRY` | `RAG Answer` |
| `nodes/qa.py` | `llm_answer_node` | `llm_answer` | `LLM_RETRY` | `LLM Answer` |
| `nodes/qa.py` | `knowledge_retrieval_node` | `knowledge_retrieval` | `RAG_RETRY` | `Knowledge Retrieval` |

> **注意**：`summarize_node` 函数名带 `summarize` 但图中节点名是 `summary`（验证 `graph_v2.py:79` 的 `add_node("summary", summarize_node, ...)`）。装饰器以图中节点名为准。

每个节点文件顶部添加：

```python
from app.agent.node_decorator import node
```

在每个被装饰的函数前面，例：

```python
@node(name="rag_first", retry="RAG_RETRY", trace_label="RAG First")
def rag_first_node(state: LearningState) -> LearningState:
    ...
```

`ask_review_or_continue_node`、`retrieval_planner_node`、`evidence_gate_node`、`answer_policy_node`、`recovery_node` 这 5 个无 retry 的节点用 `@node(name="...", trace_label="...")`（省略 `retry=None`）。

- [ ] **Step 2.6: 跑全量回归**

```
cd "<worktree>" && PYTHONPATH=. uv run pytest tests/ -q 2>&1 | tail -3
```
Expected: 181 + 5 新增 = **186 PASS**（装饰器不改变运行时行为，0 回归）

- [ ] **Step 2.7: 提交**

```bash
git add app/agent/node_decorator.py app/agent/node_registry.py app/agent/nodes/teach.py app/agent/nodes/qa.py app/agent/nodes/orchestration.py tests/test_node_decorator.py
git commit -m "feat(agent): introduce @node decorator and tag all 17 nodes with metadata"
```

---

## 任务 3：节点注册表与 graph_v2 解耦

**目标：** 让 `graph_v2.py` 不再直接 import 17 个节点函数，而是从 `NodeRegistry` 解析。这把"图中有哪些节点"的真相源从 `graph_v2.py` 的 import 块迁移到节点定义点（装饰器），消除一处重复。

**Files:**
- Modify: `app/agent/node_registry.py`（新增辅助方法 `add_to_graph()`）
- Modify: `app/agent/graph_v2.py`（用 registry 替换硬编码 add_node）
- Create: `tests/test_node_registry.py`

### 设计契约

注册表新增一个 `add_to_graph(graph, retries: dict)` 方法。它遍历所有已注册节点，按 `meta.retry_key` 从 `retries` dict 里取出 RetryPolicy，调用 `graph.add_node`。`graph_v2.py` 调用一次此方法即可注册全部节点，原本 `graph.add_node("intent_router", intent_router_node, retry=LLM_RETRY)` 等 17 行被一行替换。

注意：**`add_to_graph` 不接管条件边/固定边的注册**——这些仍由 `graph_v2.py` 显式编排。注册表只管节点本身。

### 步骤

- [ ] **Step 3.1: 写失败测试**

```python
# tests/test_node_registry.py
"""验证 NodeRegistry 单例与 add_to_graph 集成。"""
import pytest
from app.agent.node_registry import NodeRegistry, get_registry
from app.agent.node_decorator import node, NodeMeta


def test_registry_register_and_get():
    reg = NodeRegistry()

    @node(name="x_only_for_test")
    def x_node(state):
        return state

    # 装饰器自动注册到全局；这里手动注册到独立 reg 验证 API
    meta = NodeMeta(name="manual", retry_key=None, trace_label="manual")

    def manual(state):
        return state
    reg.register(meta, manual)

    got_meta, got_fn = reg.get("manual")
    assert got_meta is meta
    assert got_fn is manual


def test_registry_rejects_duplicate_with_different_meta():
    reg = NodeRegistry()
    m1 = NodeMeta(name="dup", retry_key="LLM_RETRY", trace_label="x")
    m2 = NodeMeta(name="dup", retry_key="DB_RETRY", trace_label="y")

    def f(state):
        return state
    reg.register(m1, f)
    with pytest.raises(ValueError, match="already registered"):
        reg.register(m2, f)


def test_registry_idempotent_for_same_meta():
    """同一 meta 重复注册不报错（模块重新导入场景）。"""
    reg = NodeRegistry()
    m = NodeMeta(name="ok", retry_key=None, trace_label="ok")

    def f(state):
        return state
    reg.register(m, f)
    reg.register(m, f)  # 不应抛异常
    assert reg.get("ok")[0] is m


def test_registry_get_unknown_raises():
    reg = NodeRegistry()
    with pytest.raises(KeyError):
        reg.get("missing")


def test_global_registry_contains_all_17_production_nodes():
    """导入节点包后，全局注册表必须包含 17 个生产节点（Task 2 已贴装饰器）。

    断言为子集而非相等：其他测试可能通过装饰器临时注入名称（"hello"、"bare" 等），
    这是装饰器使用全局 registry 的副作用，预期可控。
    """
    import app.agent.nodes  # 触发装饰器执行
    reg = get_registry()
    expected = {
        "intent_router", "history_check", "ask_review_or_continue",
        "diagnose", "knowledge_retrieval", "explain", "restate_check",
        "followup", "summary", "rag_first", "rag_answer", "llm_answer",
        "replan", "retrieval_planner", "evidence_gate", "answer_policy",
        "recovery",
    }
    actual = set(reg.all().keys())
    missing = expected - actual
    assert not missing, f"Missing production nodes in registry: {missing}"


def test_registry_add_to_graph_uses_meta_retry():
    """add_to_graph 把每个节点添加到图，按 meta.retry_key 解析 retry。"""
    from langgraph.graph import StateGraph, END
    from app.agent.state import LearningState
    from app.agent.retry_policy import LLM_RETRY, RAG_RETRY, DB_RETRY

    reg = NodeRegistry()

    # 自定义注册（隔离全局）
    m_llm = NodeMeta(name="llm_x", retry_key="LLM_RETRY", trace_label="t")
    m_rag = NodeMeta(name="rag_x", retry_key="RAG_RETRY", trace_label="t")
    m_db = NodeMeta(name="db_x", retry_key="DB_RETRY", trace_label="t")
    m_no = NodeMeta(name="no_x", retry_key=None, trace_label="t")

    def f(state):
        return state

    for m in [m_llm, m_rag, m_db, m_no]:
        reg.register(m, f)

    g = StateGraph(LearningState)
    reg.add_to_graph(g, retries={
        "LLM_RETRY": LLM_RETRY,
        "RAG_RETRY": RAG_RETRY,
        "DB_RETRY": DB_RETRY,
    })

    # 不直接断言 RetryPolicy 内部细节；改用 LangGraph 的 nodes 视图
    assert "llm_x" in g.nodes
    assert "rag_x" in g.nodes
    assert "db_x" in g.nodes
    assert "no_x" in g.nodes
```

- [ ] **Step 3.2: 运行测试确认部分失败**

```
cd "<worktree>" && PYTHONPATH=. uv run pytest tests/test_node_registry.py -v
```
Expected: `add_to_graph` 测试 FAIL（方法尚不存在）；其他 PASS。

- [ ] **Step 3.3: 在 `node_registry.py` 中扩充 `add_to_graph`**

修改 `app/agent/node_registry.py`，给 `NodeRegistry` 类追加方法：

```python
def add_to_graph(self, graph, *, retries: Dict[str, Any]) -> None:
    """把所有已注册节点添加到 LangGraph StateGraph。

    Args:
        graph: langgraph.graph.StateGraph 实例
        retries: retry_key → RetryPolicy 映射
                 例如 {"LLM_RETRY": LLM_RETRY, "RAG_RETRY": RAG_RETRY, ...}
    """
    for name, (meta, fn) in self._nodes.items():
        if meta.retry_key is None:
            graph.add_node(name, fn)
        else:
            policy = retries.get(meta.retry_key)
            if policy is None:
                raise ValueError(
                    f"Node '{name}' references retry_key='{meta.retry_key}' "
                    f"but it is not in the retries map: {list(retries.keys())}"
                )
            graph.add_node(name, fn, retry=policy)
```

- [ ] **Step 3.4: 运行测试全部通过**

```
cd "<worktree>" && PYTHONPATH=. uv run pytest tests/test_node_registry.py -v
```
Expected: 6/6 PASS

- [ ] **Step 3.5: 改造 `graph_v2.py` 使用 registry**

打开 `app/agent/graph_v2.py`。**保留全部条件边/固定边逻辑不变**，只替换 import 块和"添加节点"段。

**删除**第 15-34 行的整段 `from app.agent.nodes import (...)` import。

**添加**以下 import 至原 import 块附近：

```python
import app.agent.nodes  # 触发装饰器注册
from app.agent.node_registry import get_registry
```

**替换**第 64-93 行（"===== 添加节点 ====="到"# ===== Phase 2: 编排增强节点 ====="结束的那段，包括所有 `graph.add_node(...)` 调用）为：

```python
# ===== 添加节点 =====
# 节点通过 @node 装饰器在导入时自动注册；
# add_to_graph 按 meta.retry_key 解析重试策略。
get_registry().add_to_graph(graph, retries={
    "LLM_RETRY": LLM_RETRY,
    "RAG_RETRY": RAG_RETRY,
    "DB_RETRY": DB_RETRY,
})
```

注释行 `# ===== 添加节点 =====` 之外的内容（条件边、固定边、入口、END、checkpointer.compile）**保持不变**。

- [ ] **Step 3.6: 全量回归**

```
cd "<worktree>" && PYTHONPATH=. uv run pytest tests/ -q 2>&1 | tail -3
```
Expected: 186 + 6 = **192 PASS**

如果有节点名不匹配（图中条件边引用的节点名 `evidence_gate` 等）导致 LangGraph 报错，**逐一核对** Task 2 步骤 2.5 的映射表与 `graph_v2.py` 中条件边映射，修正装饰器中的 name。

- [ ] **Step 3.7: 删除已变得多余的 `nodes/__init__.py` 显式 re-export？**

**不删除**。`__init__.py` 保留 17 个 `from app.agent.nodes.* import ...` 是为了保留向后兼容（既有测试用 `from app.agent.nodes import xxx_node`）。但要在 `__init__.py` 顶部增加一行注释说明：

```python
# IMPORTANT: 这些显式 import 同时触发 @node 装饰器，
# 使节点在 NodeRegistry 中注册。不要删除。
```

- [ ] **Step 3.8: 提交**

```bash
git add app/agent/node_registry.py app/agent/graph_v2.py app/agent/nodes/__init__.py tests/test_node_registry.py
git commit -m "refactor(agent): graph_v2 resolves nodes via NodeRegistry instead of hardcoded imports"
```

---

## 任务 4：E2E 与可观测性收尾

**Files:**
- Create: `tests/test_phase5_e2e_compat.py`
- Create: `tests/test_phase5_observability.py`
- Modify: `docs/superpowers/plans/010-2026-04-28-rag-agent-framework-evolution-phase5-plan.md`（追加交付记录）

### 步骤

- [ ] **Step 4.1: 写端到端兼容性测试**

```python
# tests/test_phase5_e2e_compat.py
"""验证 Phase 5 改造后所有既有调用路径仍工作。"""
from unittest.mock import patch
from app.agent.graph_v2 import build_learning_graph_v2


def _stub_llm(monkeypatch=None):
    """共用 LLM stub。"""
    pass


def test_qa_direct_happy_path_after_phase5():
    """Phase 5 不应改变 qa_direct 成功路径行为。"""
    fake_rows = [
        {"chunk_id": f"c{i}", "score": 0.9 - i * 0.1,
         "text": f"数据库索引内容 {i}"}
        for i in range(3)
    ]
    with patch("app.services.rag_coordinator.execute_retrieval_tools",
               return_value=(fake_rows, ["search_local_textbook"])), \
         patch("app.services.llm.llm_service.route_intent",
               return_value='{"intent":"qa_direct"}'), \
         patch("app.services.llm.llm_service.invoke", return_value="answer"):
        graph = build_learning_graph_v2()
        result = graph.invoke(
            {"session_id": "p5-1", "user_input": "请介绍数据库索引",
             "topic": "数据结构", "intent": "qa_direct"},
            config={"configurable": {"thread_id": "p5-1"}},
        )
    # 由 RagView 写入的字段仍以原 key 存在
    assert "rag_found" in result
    assert "rag_context" in result
    assert "answer_template_id" in result  # answer_policy 跑过
    assert result.get("rag_found") is True


def test_qa_direct_retry_then_recover_after_phase5():
    """Phase 4 引入的单次重试语义不应被 Phase 5 改造破坏。"""
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
            {"session_id": "p5-2", "user_input": "什么是B+树",
             "topic": "数据结构", "intent": "qa_direct"},
            config={"configurable": {"thread_id": "p5-2"}},
        )
    assert call_count["n"] == 2
    assert result.get("error_code") == "llm_timeout"
    assert result.get("fallback_triggered") is True


def test_legacy_imports_still_work():
    """既有测试通过 `from app.agent.nodes import xxx_node` 必须仍可用。"""
    from app.agent.nodes import (
        intent_router_node,
        rag_first_node,
        knowledge_retrieval_node,
        evidence_gate_node,
        recovery_node,
    )
    assert callable(intent_router_node)
    assert callable(rag_first_node)
    assert callable(knowledge_retrieval_node)
    assert callable(evidence_gate_node)
    assert callable(recovery_node)


def test_decorator_metadata_accessible_at_runtime():
    """通过 NodeRegistry 可读取每个节点的 retry_key 与 trace_label。"""
    from app.agent.node_registry import get_registry
    import app.agent.nodes  # 触发注册

    reg = get_registry()
    rag_first_meta, _ = reg.get("rag_first")
    assert rag_first_meta.retry_key == "RAG_RETRY"
    assert rag_first_meta.trace_label == "RAG First"

    intent_meta, _ = reg.get("intent_router")
    assert intent_meta.retry_key == "LLM_RETRY"

    # 无 retry 的节点
    gate_meta, _ = reg.get("evidence_gate")
    assert gate_meta.retry_key is None
```

- [ ] **Step 4.2: 写可观测性钩子测试**

```python
# tests/test_phase5_observability.py
"""验证装饰器元数据可被外部观察工具消费。"""
from app.agent.node_registry import get_registry
import app.agent.nodes  # 触发注册


def test_all_nodes_have_trace_labels():
    """每个注册节点都有非空 trace_label。"""
    reg = get_registry()
    for name, (meta, _fn) in reg.all().items():
        assert meta.trace_label, f"node '{name}' missing trace_label"


def test_retry_keys_are_valid():
    """retry_key 取值在 {None, LLM_RETRY, RAG_RETRY, DB_RETRY} 内。"""
    reg = get_registry()
    valid = {None, "LLM_RETRY", "RAG_RETRY", "DB_RETRY"}
    for name, (meta, _fn) in reg.all().items():
        assert meta.retry_key in valid, \
            f"node '{name}' has invalid retry_key={meta.retry_key!r}"


def test_no_node_has_duplicate_name():
    """注册表保证名称唯一（registry.register 也会强制）。"""
    reg = get_registry()
    names = list(reg.all().keys())
    assert len(names) == len(set(names))


def test_all_production_nodes_registered():
    """17 个生产节点全部在注册表中（不强制 == 17，因测试装饰器会向全局 registry 注入临时节点）。"""
    reg = get_registry()
    expected = {
        "intent_router", "history_check", "ask_review_or_continue",
        "diagnose", "knowledge_retrieval", "explain", "restate_check",
        "followup", "summary", "rag_first", "rag_answer", "llm_answer",
        "replan", "retrieval_planner", "evidence_gate", "answer_policy",
        "recovery",
    }
    assert expected.issubset(set(reg.all().keys()))
```

- [ ] **Step 4.3: 跑新测试**

```
cd "<worktree>" && PYTHONPATH=. uv run pytest tests/test_phase5_e2e_compat.py tests/test_phase5_observability.py -v
```
Expected: 8/8 PASS

- [ ] **Step 4.4: 全量回归**

```
cd "<worktree>" && PYTHONPATH=. uv run pytest tests/ -q 2>&1 | tail -3
```
Expected: 192 + 8 = **200 PASS**

- [ ] **Step 4.5: 在计划文件追加交付记录**

打开 `docs/superpowers/plans/010-2026-04-28-rag-agent-framework-evolution-phase5-plan.md`，在文件末尾追加：

```markdown

---

## 交付记录

- **完成日期**：（填实际日期）
- **分支**：`worktree-phase5-conventions`
- **提交 SHA 范围**：（起..止）
- **测试结果**：200 PASS / 0 FAIL（master 基线 174 + 本期新增 26）

### 验收清单

- [x] RagView 引入并在 rag_first / knowledge_retrieval 试点（任务 1）
- [x] @node 装饰器贴到全部 17 个节点（任务 2）
- [x] graph_v2 通过 NodeRegistry 解析节点（任务 3）
- [x] 既有测试 0 回归（任务 4 E2E 验证）
- [x] retry_key/trace_label 全节点齐备（任务 4 可观测性验证）

### 关键设计决策

- **不嵌套 LearningState**：保持扁平 TypedDict，避免破坏 LangGraph reducer。RagView 是无状态门面，直接读写原 dict。
- **装饰器不替代 LangGraph retry**：`add_node` 仍传入 RetryPolicy；装饰器只标注 retry_key 让 registry 知道要传什么。
- **`__init__.py` 保留显式 re-export**：既向后兼容旧 import，也确保装饰器在导入时执行。

### 已知遗留（Phase 6 待办）

- OrchestrationView / RecoveryView 未实现：等使用模式稳定后再决定是否扩展。
- 装饰器尚未实现 `permission` / `sensitive` 字段的实际效果（trace 脱敏）：Phase 6 与 Langfuse 集成时再接入。
- 节点装饰器与 graph_v2 解耦了节点名，但条件边映射仍硬编码——边（route_after_*）的注册表化是 Phase 6 候选。
```

- [ ] **Step 4.6: 提交**

```bash
git add tests/test_phase5_e2e_compat.py tests/test_phase5_observability.py docs/superpowers/plans/010-2026-04-28-rag-agent-framework-evolution-phase5-plan.md
git commit -m "docs+test: phase-5 E2E compatibility, observability checks, delivery record"
```

---

## 风险与回滚

| 风险 | 缓解 |
|---|---|
| RagView 在 LangGraph reducer 下行为不一致 | Step 1.6 单独跑 qa 测试集，Step 1.8 全量回归。如果失败立刻回退 Step 1.5 替换、保留 state_view.py 文件待后续验证 |
| 装饰器在节点 import 时失败导致整个 nodes 包不可用 | `node_decorator.py` 导入 registry 用延迟 import；`node_registry.py` 不依赖 nodes 包；测试 Step 2.2 先验证装饰器孤立可用 |
| graph_v2 通过 registry 后节点名拼写错误导致条件边断裂 | Step 2.5 节点名映射表是权威；Step 3.6 全量回归会立刻发现 |
| `__init__.py` 删除导致装饰器没机会执行 | Step 3.7 显式不删除；`graph_v2.py` 顶部 `import app.agent.nodes` 也确保装饰器执行 |
| 节点重复注册（pytest 多次 import） | `NodeRegistry.register` 对同 meta 幂等；不同 meta 才报错（步骤 3.1 测试覆盖） |

回滚策略：每任务独立提交。任务 3 出问题可单独 revert（恢复硬编码 add_node）；任务 1/2 各自独立。

---

## 后续阶段（不在本计划范围）

- **Phase 6**：OrchestrationView / RecoveryView（视 Phase 5 用感扩展）；trace 脱敏（结合 Langfuse）；条件边注册表化；`/chat/plan` 端点；跨主题概念记忆；证据冲突检测。


---

## 交付记录

- **完成日期**：2026-04-28
- **分支**：`worktree-phase5-conventions`
- **基于**：master 合并 Phase 4（HEAD `351fffd` 之后）
- **测试结果**：201 PASS / 0 FAIL（master 基线 174 + 本期新增 27）

### 提交清单

| SHA | 内容 |
|---|---|
| `1282415` | feat(agent): introduce RagView typed access facade; pilot in qa nodes |
| `3f358ae` | fix(agent): RagView.record_meta is true drop-in for raw assignment |
| `6cf09dc` | feat(agent): introduce @node decorator and tag all 17 nodes with metadata |
| `23194d2` | refactor(agent): graph_v2 resolves nodes via NodeRegistry instead of hardcoded imports |
| `269b6c0` | refactor(agent): explicit register_all_nodes() instead of side-effect import; document patch limitations |
| `1ddcda1` | docs+test: phase-5 E2E compatibility, observability checks, delivery record |

### 验收清单

- [x] RagView 引入并在 rag_first / knowledge_retrieval 试点（任务 1）
- [x] @node 装饰器贴到全部 17 个节点（任务 2）
- [x] graph_v2 通过 NodeRegistry 解析节点（任务 3）
- [x] 既有测试 0 回归（任务 4 E2E 验证）
- [x] retry_key/trace_label 全节点齐备（任务 4 可观测性验证）

### 评审遗留修复

- **T1 review**：`record_meta` None 短路被 review 标为 Important；改为无条件赋值，使其与原始 `state["rag_meta_last"] = meta` 完全等价。新增 `test_ragview_record_meta_none_writes_none_into_state` 锁定语义。
- **T3 review I1**：side-effect import 易被 ruff/IDE 误删；引入 `register_all_nodes()` 显式入口。
- **T3 review M6**：在 `nodes/__init__.py` 加注释，记录"已编译图后 patch 节点函数无效"的限制并指引正确的 patch 路径。

### 关键设计决策

- **不嵌套 LearningState**：保持扁平 TypedDict，避免破坏 LangGraph reducer。RagView 是无状态门面，直接读写原 dict。
- **装饰器不替代 LangGraph retry**：`add_node` 仍传入 RetryPolicy；装饰器只标注 retry_key 让 registry 知道要传什么。
- **`__init__.py` 保留显式 re-export**：既向后兼容旧 import，也确保装饰器在导入时执行。
- **`register_all_nodes()` 是 no-op**：真正的注册由 import 副作用完成，但显式函数让依赖关系 grep 可见。

### 已知遗留（Phase 6 待办）

- OrchestrationView / RecoveryView 未实现：等使用模式稳定后再决定是否扩展。
- 装饰器尚未实现 `permission` / `sensitive` 字段的实际效果（trace 脱敏）：Phase 6 与 Langfuse 集成时再接入。
- `retries` map 仍用魔法字符串（"LLM_RETRY"/"RAG_RETRY"/"DB_RETRY"）：Phase 6 候选改为 Enum。
- 节点装饰器与 graph_v2 解耦了节点名，但条件边映射仍硬编码——边（route_after_*）的注册表化是 Phase 6 候选。
- 测试装饰器污染全局 registry：Phase 6 用 conftest.py autouse fixture 改善。
