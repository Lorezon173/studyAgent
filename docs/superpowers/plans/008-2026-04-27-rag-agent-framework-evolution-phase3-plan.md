# RAG Agent 框架演进 Phase 3：连线与硬化实施计划

> **给 Agentic Worker：** 必须使用 `superpowers:subagent-driven-development`（推荐）或 `superpowers:executing-plans` 按任务逐步执行。步骤使用复选框语法（`- [ ]`）跟踪。

**目标：** 把 Phase 2 已落地但"未接通"的三块能力接到主链路上：(1) 错误分类驱动细粒度路由；(2) Rerank 按策略触发；(3) RAG 执行元数据扩展为可复盘/可反馈的完整快照。

**架构：** 不引入新节点、不重构图。仅在已有节点/路由/服务内部连线，并扩展数据契约。所有改动可独立提交，互不阻塞。

**技术栈：** Python 3.12、FastAPI、LangGraph、pytest、uv

**前置依赖：** Phase 1 + Phase 2 已交付 ✅
- `app/services/error_classifier.py` — `classify_error()` / `ErrorType` 已存在
- `app/services/rerank_service.py` — `rerank_items()` 已存在
- `app/services/rag_coordinator.py` — `RAGExecutionMeta` 已存在
- `app/services/retrieval_strategy.py` — 三模式策略已存在
- `app/agent/routers.py` — `route_on_error()` 已存在但仅看布尔

**非目标（明确 OUT-of-SCOPE）：**
- 不重构 `LearningState`（留给 Phase 4）
- 不引入技能注册表/节点装饰器（留给 Phase 4）
- 不实现冲突检测、跨主题记忆、`/chat/plan` API（留给 Phase 5）
- 不更换 embedding 模型，不动 chunking 策略

---

## 文件结构

```text
app/
├── services/
│   ├── error_classifier.py        # 修改：补 from_state() 工具函数
│   ├── rerank_service.py          # 修改：补 should_rerank() 策略判定
│   ├── rag_coordinator.py         # 修改：RAGExecutionMeta → RAGExecutionDetail
│   └── tool_executor.py           # 修改：返回完整候选 + 分数
├── agent/
│   ├── nodes.py                   # 修改：retrieval_planner_node 触发 rerank
│   │                               #       knowledge_retrieval_node 写 error_code
│   │                               #       recovery_node 读 error_code
│   └── routers.py                 # 修改：route_on_error 按 error_type 分流
├── api/
│   └── chat.py                    # 修改：响应附带 rag_detail
└── models/
    └── schemas.py                 # 修改：新增 RagExecutionDetailModel

tests/
├── test_route_on_error_typed.py            # 新增：T1
├── test_rerank_strategy_gating.py          # 新增：T2
├── test_rag_execution_detail.py            # 新增：T3
├── test_knowledge_retrieval_error_code.py  # 新增：T4
└── test_phase3_e2e.py                      # 新增：T6 端到端回归
```

---

## 任务 1：错误分类驱动路由

**Files:**
- Modify: `app/services/error_classifier.py`（新增 `classify_from_code()`）
- Modify: `app/agent/routers.py:142-152`（重写 `route_on_error`）
- Create: `tests/test_route_on_error_typed.py`

- [ ] **步骤 1.1：先写失败测试（按错误类型分流）**

```python
# tests/test_route_on_error_typed.py
from app.agent.routers import route_on_error


def test_route_no_error_goes_to_answer_policy():
    state = {}
    assert route_on_error(state) == "answer_policy"


def test_route_rag_failure_goes_to_recovery():
    state = {"node_error": "rag failed", "error_code": "rag_failure"}
    assert route_on_error(state) == "recovery"


def test_route_llm_timeout_goes_to_retry_then_recovery():
    # timeout 在第一次进入应触发 retry（通过 retry_trace 长度判定）
    state = {"node_error": "timed out", "error_code": "llm_timeout", "retry_trace": []}
    assert route_on_error(state) == "retry_rag"


def test_route_llm_timeout_after_retry_goes_to_recovery():
    state = {
        "node_error": "timed out",
        "error_code": "llm_timeout",
        "retry_trace": [{"attempt": 1}],
    }
    assert route_on_error(state) == "recovery"


def test_route_unknown_error_falls_back_to_recovery():
    state = {"node_error": "boom", "error_code": "unknown"}
    assert route_on_error(state) == "recovery"
```

- [ ] **步骤 1.2：运行测试确认失败**

Run: `uv run pytest tests/test_route_on_error_typed.py -v`
Expected: 5 个测试 FAIL（路由仅返回 `recovery`/`answer_policy`，不识别 `retry_rag`）

- [ ] **步骤 1.3：在 `error_classifier.py` 末尾追加 `classify_from_code()`**

```python
# app/services/error_classifier.py 追加在文件末尾

def classify_from_code(error_code: str) -> ErrorClassification:
    """从已写入 state 的 error_code 字符串反查分类结果。

    供路由层使用：节点写 error_code，路由读 error_code。
    """
    try:
        return ERROR_STRATEGIES[ErrorType(error_code)]
    except (ValueError, KeyError):
        return ERROR_STRATEGIES[ErrorType.UNKNOWN]
```

- [ ] **步骤 1.4：重写 `routers.py` 的 `route_on_error`**

替换 `app/agent/routers.py:142-152` 整段：

```python
def route_on_error(state: LearningState) -> Literal["recovery", "answer_policy", "retry_rag"]:
    """错误时按 error_code 分流。

    规则：
    - 无 node_error -> answer_policy
    - retryable 且未重试过 -> retry_rag
    - 其他（包括重试已用尽、不可重试错误）-> recovery
    """
    if not state.get("node_error"):
        return "answer_policy"

    from app.services.error_classifier import classify_from_code

    code = state.get("error_code", "unknown")
    classification = classify_from_code(code)
    retry_trace = state.get("retry_trace") or []

    if classification.retryable and len(retry_trace) == 0:
        return "retry_rag"
    return "recovery"
```

- [ ] **步骤 1.5：在 `graph_v2.py` 添加 `retry_rag` 边**

打开 `app/agent/graph_v2.py`，定位 `route_on_error` 的 `add_conditional_edges` 调用，把目标映射改为：

```python
{
    "recovery": "recovery",
    "answer_policy": "answer_policy",
    "retry_rag": "knowledge_retrieval",  # 重试时回到检索节点
}
```

如果当前文件未显式列映射，则在 `add_conditional_edges(..., route_on_error, {...})` 处补全此 dict。

- [ ] **步骤 1.6：运行测试确认通过**

Run: `uv run pytest tests/test_route_on_error_typed.py -v`
Expected: 5 PASS

- [ ] **步骤 1.7：提交**

```bash
git add app/services/error_classifier.py app/agent/routers.py app/agent/graph_v2.py tests/test_route_on_error_typed.py
git commit -m "feat(agent): route_on_error dispatches by error_code with single retry"
```

---

## 任务 2：节点写入 error_code

**Files:**
- Modify: `app/agent/nodes.py`（`knowledge_retrieval_node` 与所有 except 块）
- Create: `tests/test_knowledge_retrieval_error_code.py`

- [ ] **步骤 2.1：先写失败测试**

```python
# tests/test_knowledge_retrieval_error_code.py
from unittest.mock import patch
from app.agent.nodes import knowledge_retrieval_node


def test_knowledge_retrieval_writes_error_code_on_timeout():
    state = {"user_input": "什么是B+树", "topic": "数据结构"}
    with patch("app.agent.nodes.execute_rag", side_effect=TimeoutError("timed out")):
        result = knowledge_retrieval_node(state)
    assert result.get("error_code") == "llm_timeout"
    assert result.get("node_error")


def test_knowledge_retrieval_writes_rag_failure_on_runtime():
    state = {"user_input": "什么是B+树", "topic": "数据结构"}
    with patch("app.agent.nodes.execute_rag", side_effect=RuntimeError("connection refused")):
        result = knowledge_retrieval_node(state)
    assert result.get("error_code") == "db_error"


def test_knowledge_retrieval_no_error_code_on_success():
    state = {"user_input": "什么是B+树", "topic": "数据结构"}
    with patch("app.agent.nodes.execute_rag", return_value=([], type("M", (), {
        "reason": "ok", "used_tools": [], "hit_count": 0,
        "fallback_used": False, "query_mode": "fact", "query_reason": "test",
    })())):
        result = knowledge_retrieval_node(state)
    assert not result.get("error_code")
```

- [ ] **步骤 2.2：运行测试确认失败**

Run: `uv run pytest tests/test_knowledge_retrieval_error_code.py -v`
Expected: 3 FAIL（`error_code` 字段不存在）

- [ ] **步骤 2.3：在 `knowledge_retrieval_node` 的异常处理处写入 error_code**

定位 `nodes.py` 中 `knowledge_retrieval_node`（约 350-450 行附近，按实际行号），在 except 块中改写：

```python
except Exception as exc:
    from app.services.error_classifier import classify_error
    classification = classify_error(exc)
    _append_trace(state, "knowledge_retrieval_error", {
        "error_type": classification.error_type.value,
        "message": str(exc),
    })
    return {
        "node_error": str(exc),
        "error_code": classification.error_type.value,
        "rag_found": False,
    }
```

如该节点没有 try/except 包裹，则把核心 `execute_rag(...)` 调用整体包入 try。

- [ ] **步骤 2.4：运行测试确认通过**

Run: `uv run pytest tests/test_knowledge_retrieval_error_code.py -v`
Expected: 3 PASS

- [ ] **步骤 2.5：提交**

```bash
git add app/agent/nodes.py tests/test_knowledge_retrieval_error_code.py
git commit -m "feat(agent): knowledge_retrieval_node writes typed error_code"
```

---

## 任务 3：Rerank 按策略触发

**Files:**
- Modify: `app/services/rerank_service.py`（新增 `should_rerank()`）
- Modify: `app/services/rag_coordinator.py`（在 `execute_rag` 中调用）
- Create: `tests/test_rerank_strategy_gating.py`

- [ ] **步骤 3.1：先写失败测试**

```python
# tests/test_rerank_strategy_gating.py
from app.services.rerank_service import should_rerank


def test_should_rerank_true_for_comparison_with_enough_candidates():
    strategy = {"bm25_weight": 0.5, "vector_weight": 0.5}
    assert should_rerank(strategy=strategy, candidate_count=5) is True


def test_should_rerank_false_for_fact_with_few_candidates():
    strategy = {"bm25_weight": 0.4, "vector_weight": 0.6}
    assert should_rerank(strategy=strategy, candidate_count=2) is False


def test_should_rerank_false_when_strategy_disables():
    strategy = {"bm25_weight": 0.4, "vector_weight": 0.6, "rerank_enabled": False}
    assert should_rerank(strategy=strategy, candidate_count=10) is False


def test_should_rerank_true_when_strategy_forces():
    strategy = {"rerank_enabled": True}
    assert should_rerank(strategy=strategy, candidate_count=2) is True
```

- [ ] **步骤 3.2：运行测试确认失败**

Run: `uv run pytest tests/test_rerank_strategy_gating.py -v`
Expected: ImportError，`should_rerank` 不存在

- [ ] **步骤 3.3：在 `rerank_service.py` 末尾新增 `should_rerank`**

```python
# 追加在 app/services/rerank_service.py 末尾

def should_rerank(*, strategy: dict, candidate_count: int) -> bool:
    """根据检索策略与候选数量决定是否触发 rerank。

    策略显式 rerank_enabled 字段优先；否则规则：
    - 候选 >=4 且策略为 comparison（bm25/vector 各 0.5）-> True
    - 否则 False
    """
    if "rerank_enabled" in strategy:
        return bool(strategy["rerank_enabled"])

    bm25 = float(strategy.get("bm25_weight", 0.0))
    vec = float(strategy.get("vector_weight", 0.0))
    is_comparison = abs(bm25 - 0.5) < 1e-6 and abs(vec - 0.5) < 1e-6
    return is_comparison and candidate_count >= 4
```

- [ ] **步骤 3.4：运行测试确认通过**

Run: `uv run pytest tests/test_rerank_strategy_gating.py -v`
Expected: 4 PASS

- [ ] **步骤 3.5：扩展 `execute_rag` 接受 strategy 并触发 rerank**

修改 `app/services/rag_coordinator.py:35-71` 的 `execute_rag`：

```python
def execute_rag(
    *,
    query: str,
    topic: str | None,
    user_id: int | None,
    tool_route: dict[str, Any] | None,
    top_k: int,
    strategy: dict | None = None,
) -> tuple[list[dict[str, Any]], RAGExecutionMeta]:
    plan = build_query_plan(query, topic)
    merged_route = dict(tool_route or {})
    if plan.enable_web and not merged_route.get("tool"):
        merged_route["tool"] = "search_web"

    rows, used_tools = execute_retrieval_tools(
        query=plan.rewritten_query,
        topic=topic,
        user_id=user_id,
        tool_route=merged_route,
        top_k=max(1, min(top_k, plan.top_k)),
    )

    reranked = False
    if rows and strategy:
        from app.services.rerank_service import should_rerank, rerank_items
        if should_rerank(strategy=strategy, candidate_count=len(rows)):
            rows = rerank_items(plan.rewritten_query, rows)
            reranked = True

    if rows:
        return rows, RAGExecutionMeta(
            reason="tool_retrieval_reranked" if reranked else "tool_retrieval",
            used_tools=used_tools,
            hit_count=len(rows),
            fallback_used=False,
            query_mode=plan.mode,
            query_reason=plan.reason,
        )
    return [], RAGExecutionMeta(
        reason="tool_retrieval_empty",
        used_tools=used_tools,
        hit_count=0,
        fallback_used=False,
        query_mode=plan.mode,
        query_reason=plan.reason,
    )
```

- [ ] **步骤 3.6：在 `knowledge_retrieval_node` 调用处传入 strategy**

定位 `nodes.py` 中调用 `execute_rag(...)` 的位置，把现有 `state.get("retrieval_strategy")` 透传：

```python
rows, meta = execute_rag(
    query=...,
    topic=...,
    user_id=...,
    tool_route=...,
    top_k=...,
    strategy=state.get("retrieval_strategy") or {},
)
```

- [ ] **步骤 3.7：跑全量回归**

Run: `uv run pytest tests/ -v -k "rag or retrieval or rerank"`
Expected: 全部 PASS（包括既有 RAG 测试不被破坏）

- [ ] **步骤 3.8：提交**

```bash
git add app/services/rerank_service.py app/services/rag_coordinator.py app/agent/nodes.py tests/test_rerank_strategy_gating.py
git commit -m "feat(rag): rerank gated by retrieval strategy and candidate count"
```

---

## 任务 4：RAG 元数据扩展为完整快照

**Files:**
- Modify: `app/services/tool_executor.py`（保留全部候选与分数）
- Modify: `app/services/rag_coordinator.py`（`RAGExecutionMeta` → `RAGExecutionDetail`）
- Create: `tests/test_rag_execution_detail.py`

- [ ] **步骤 4.1：先写失败测试**

```python
# tests/test_rag_execution_detail.py
from unittest.mock import patch
from app.services.rag_coordinator import execute_rag


def test_execution_detail_records_all_candidates():
    fake_rows = [
        {"chunk_id": "c1", "score": 0.9, "text": "A"},
        {"chunk_id": "c2", "score": 0.5, "text": "B"},
        {"chunk_id": "c3", "score": 0.3, "text": "C"},
    ]
    with patch("app.services.rag_coordinator.execute_retrieval_tools",
               return_value=(fake_rows, ["search_local_textbook"])):
        rows, meta = execute_rag(
            query="q", topic=None, user_id=None,
            tool_route=None, top_k=2, strategy={},
        )
    assert len(rows) == 3  # 不再被 top_k 截断（截断交给上层）
    assert hasattr(meta, "candidates")
    assert len(meta.candidates) == 3
    assert meta.candidates[0]["chunk_id"] == "c1"
    assert "score" in meta.candidates[0]
    assert meta.elapsed_ms >= 0
    assert meta.selected_chunk_ids == ["c1", "c2", "c3"]


def test_execution_detail_marks_reranked():
    fake_rows = [{"chunk_id": "c1", "score": 0.5, "text": "A"}] * 5
    with patch("app.services.rag_coordinator.execute_retrieval_tools",
               return_value=(fake_rows, ["search_local_textbook"])), \
         patch("app.services.rerank_service.rerank_items", return_value=fake_rows):
        _, meta = execute_rag(
            query="q", topic=None, user_id=None, tool_route=None, top_k=5,
            strategy={"rerank_enabled": True},
        )
    assert meta.reranked is True
```

- [ ] **步骤 4.2：运行测试确认失败**

Run: `uv run pytest tests/test_rag_execution_detail.py -v`
Expected: AttributeError，`candidates` / `elapsed_ms` 字段不存在

- [ ] **步骤 4.3：扩展 `RAGExecutionMeta` 为 `RAGExecutionDetail`**

修改 `app/services/rag_coordinator.py:18-24`：

```python
@dataclass
class RAGExecutionMeta:
    reason: str
    used_tools: list[str]
    hit_count: int
    fallback_used: bool
    query_mode: str
    query_reason: str
    # Phase 3 扩展字段（向后兼容：旧调用方不读这些字段不受影响）
    candidates: list[dict[str, Any]] = None  # type: ignore[assignment]
    selected_chunk_ids: list[str] = None  # type: ignore[assignment]
    elapsed_ms: int = 0
    reranked: bool = False

    def __post_init__(self) -> None:
        if self.candidates is None:
            self.candidates = []
        if self.selected_chunk_ids is None:
            self.selected_chunk_ids = []
```

> 不重命名类（保持向后兼容）。新字段全部带默认值。

- [ ] **步骤 4.4：更新 `execute_rag` 计时与候选填充**

在 `execute_rag` 顶部加 `import time`、`start = time.monotonic()`，并在两处 return 处填充新字段：

```python
elapsed = int((time.monotonic() - start) * 1000)
candidates = [
    {"chunk_id": str(r.get("chunk_id", "")),
     "score": float(r.get("score", 0.0)),
     "tool": r.get("tool", "")}
    for r in rows
]
selected_ids = [c["chunk_id"] for c in candidates if c["chunk_id"]]

return rows, RAGExecutionMeta(
    reason="tool_retrieval_reranked" if reranked else "tool_retrieval",
    used_tools=used_tools,
    hit_count=len(rows),
    fallback_used=False,
    query_mode=plan.mode,
    query_reason=plan.reason,
    candidates=candidates,
    selected_chunk_ids=selected_ids,
    elapsed_ms=elapsed,
    reranked=reranked,
)
```

空命中分支也填充（`candidates=[]`、`elapsed_ms=elapsed`）。

- [ ] **步骤 4.5：运行测试确认通过**

Run: `uv run pytest tests/test_rag_execution_detail.py -v`
Expected: 2 PASS

- [ ] **步骤 4.6：跑既有 RAG 测试确保未破坏向后兼容**

Run: `uv run pytest tests/ -v -k "rag or coordinator"`
Expected: 全部 PASS

- [ ] **步骤 4.7：提交**

```bash
git add app/services/rag_coordinator.py tests/test_rag_execution_detail.py
git commit -m "feat(rag): expand RAGExecutionMeta with candidates, elapsed_ms, reranked"
```

---

## 任务 5：API 暴露执行明细（只读）

**Files:**
- Modify: `app/models/schemas.py`（新增 Pydantic 模型）
- Modify: `app/api/chat.py`（响应附带 `rag_detail`）

- [ ] **步骤 5.1：在 schemas.py 新增模型**

```python
# 追加到 app/models/schemas.py
from pydantic import BaseModel
from typing import List, Optional


class RagCandidateModel(BaseModel):
    chunk_id: str
    score: float
    tool: str = ""


class RagExecutionDetailModel(BaseModel):
    query_mode: str
    used_tools: List[str]
    hit_count: int
    elapsed_ms: int
    reranked: bool
    candidates: List[RagCandidateModel] = []
    selected_chunk_ids: List[str] = []
```

如果 `ChatResponse` 已存在，给它加可选字段：

```python
class ChatResponse(BaseModel):
    # ... 既有字段保持不变
    rag_detail: Optional[RagExecutionDetailModel] = None
```

- [ ] **步骤 5.2：在 `chat.py` 响应组装处填充**

定位响应组装位置（`agent_service.run()` 返回后），从 `state` 取最后一次 RAG 元数据（约定字段：`rag_meta_last`，若不存在则跳过）：

```python
rag_meta = state.get("rag_meta_last")
rag_detail = None
if rag_meta is not None:
    rag_detail = RagExecutionDetailModel(
        query_mode=rag_meta.query_mode,
        used_tools=rag_meta.used_tools,
        hit_count=rag_meta.hit_count,
        elapsed_ms=getattr(rag_meta, "elapsed_ms", 0),
        reranked=getattr(rag_meta, "reranked", False),
        candidates=[RagCandidateModel(**c) for c in (getattr(rag_meta, "candidates", []) or [])],
        selected_chunk_ids=getattr(rag_meta, "selected_chunk_ids", []) or [],
    )
```

如果当前 state 没有 `rag_meta_last`，需要在 `knowledge_retrieval_node` 末尾把 meta 写入 state：

```python
# nodes.py knowledge_retrieval_node 返回前
return {
    # ...其他字段
    "rag_meta_last": meta,
}
```

并在 `state.py` 的 `LearningState` 加一行：

```python
rag_meta_last: object   # RAGExecutionMeta 实例，仅运行时存在
```

- [ ] **步骤 5.3：手动 smoke**

Run（启动服务后）：

```bash
curl -s -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"user_input":"什么是B+树","topic":"数据结构","session_id":"phase3-smoke"}' \
  | python -m json.tool
```

Expected: 响应 JSON 中包含 `rag_detail` 对象，且 `candidates` 非空、`elapsed_ms > 0`。

- [ ] **步骤 5.4：提交**

```bash
git add app/models/schemas.py app/api/chat.py app/agent/nodes.py app/agent/state.py
git commit -m "feat(api): expose RAG execution detail in chat response"
```

---

## 任务 6：端到端回归

**Files:**
- Create: `tests/test_phase3_e2e.py`

- [ ] **步骤 6.1：写端到端测试**

```python
# tests/test_phase3_e2e.py
"""Phase 3 端到端：错误分流 + Rerank + RAG 元数据 在主链路中协同工作。"""
from unittest.mock import patch
from app.agent.graph_v2 import build_learning_graph_v2


def _run(state: dict) -> dict:
    graph = build_learning_graph_v2()
    return graph.invoke(state)


def test_e2e_rag_success_emits_detail():
    fake_rows = [{"chunk_id": f"c{i}", "score": 0.9 - i * 0.1, "text": f"chunk {i}"} for i in range(5)]
    with patch("app.services.tool_executor.execute_retrieval_tools",
               return_value=(fake_rows, ["search_local_textbook"])):
        result = _run({
            "session_id": "e2e-1",
            "user_input": "比较 B 树和 B+ 树",
            "topic": "数据结构",
            "intent": "qa_direct",
        })
    assert result.get("rag_meta_last") is not None
    assert len(result["rag_meta_last"].candidates) == 5


def test_e2e_rag_timeout_routes_via_retry_then_recovery():
    call_count = {"n": 0}

    def flaky(*a, **kw):
        call_count["n"] += 1
        raise TimeoutError("timed out")

    with patch("app.services.rag_coordinator.execute_retrieval_tools", side_effect=flaky):
        result = _run({
            "session_id": "e2e-2",
            "user_input": "什么是红黑树",
            "topic": "数据结构",
            "intent": "qa_direct",
        })
    # 第一次失败 -> retry_rag -> 第二次失败 -> recovery
    assert call_count["n"] == 2
    assert result.get("fallback_triggered") is True
    assert result.get("error_code") == "llm_timeout"


def test_e2e_comparison_query_triggers_rerank():
    fake_rows = [{"chunk_id": f"c{i}", "score": 0.5, "text": f"x{i}"} for i in range(6)]
    with patch("app.services.tool_executor.execute_retrieval_tools",
               return_value=(fake_rows, ["search_local_textbook"])), \
         patch("app.services.rerank_service.rerank_items",
               side_effect=lambda q, items: list(reversed(items))) as rerank_spy:
        result = _run({
            "session_id": "e2e-3",
            "user_input": "对比快速排序和归并排序",
            "topic": "算法",
            "intent": "qa_direct",
        })
    assert rerank_spy.called
    assert result["rag_meta_last"].reranked is True
```

- [ ] **步骤 6.2：运行 E2E**

Run: `uv run pytest tests/test_phase3_e2e.py -v`
Expected: 3 PASS

> **若 mock 路径不匹配（实际函数在别处被引用）**：调整 `patch` 目标路径。这是 mock 常见问题，不是代码缺陷。

- [ ] **步骤 6.3：跑完整回归**

Run: `uv run pytest tests/ -v`
Expected: 全部 PASS。如有既有测试因新字段变化而 FAIL，定位并修正断言（不要回退新字段）。

- [ ] **步骤 6.4：提交**

```bash
git add tests/test_phase3_e2e.py
git commit -m "test(agent): phase3 E2E covers typed routing, rerank gating, rag detail"
```

---

## 任务 7：交付检查与文档更新

- [ ] **步骤 7.1：勾选验收清单**

```text
[ ] route_on_error 按 error_code 分流（任务 1）
[ ] knowledge_retrieval_node 写入 typed error_code（任务 2）
[ ] Rerank 按策略 + 候选数门控（任务 3）
[ ] RAGExecutionMeta 含 candidates / elapsed_ms / reranked / selected_chunk_ids（任务 4）
[ ] /chat 响应附带 rag_detail（任务 5）
[ ] E2E 三场景通过（任务 6）
[ ] 既有测试 0 回归
```

- [ ] **步骤 7.2：在本计划文件追加交付记录**

在文件最末追加：

```markdown
---

## 交付记录

- 完成日期：YYYY-MM-DD
- 提交 SHA 范围：<起>..<止>
- 已知遗留：（如有）
- 下一阶段触发条件：Phase 4 状态分层 + 节点装饰器
```

- [ ] **步骤 7.3：最终提交**

```bash
git add docs/superpowers/plans/008-2026-04-27-rag-agent-framework-evolution-phase3-plan.md
git commit -m "docs: mark phase-3 wire-up & hardening delivered"
```

---

## 风险与回滚

| 风险 | 缓解 |
|---|---|
| `RAGExecutionMeta` 新字段破坏既有调用方 | 全部新字段带默认值，向后兼容；任务 4 步骤 4.6 显式回归 |
| `route_on_error` 引入 `retry_rag` 边导致图无限循环 | 任务 1 步骤 1.4 用 `len(retry_trace) == 0` 限制单次重试；E2E 任务 6 验证 |
| Rerank 触发条件过宽导致延迟上升 | 默认仅 comparison + 候选≥4 才触发；策略可显式关闭 |
| Mock 路径与生产引用路径不一致致 E2E 不稳 | 任务 6 步骤 6.2 备注；必要时改 patch 目标 |

回滚策略：每任务独立提交；任意任务回滚不影响其他任务。

---

## 后续阶段（不在本计划范围）

- **Phase 4**：状态分层（`RagMeta`/`OrchestrationMeta`/`RecoveryMeta`）+ 节点装饰器（`@node(retry, trace, permission)`）+ 技能注册表
- **Phase 5**：证据冲突检测、跨主题概念记忆、`/chat/plan` & `/chat/execute` 端点拆分、Trace 权限分级、Embedding 注册表 + AB

---

## 交付记录

- **完成日期**：2026-04-27
- **分支**：`worktree-phase3-wireup`
- **提交 SHA 范围**：`26f90f1..15bbaef`（共 8 个提交）
- **测试结果**：165 PASS / 0 FAIL（基线 145 + 本期新增 20）

### 验收清单

```text
[x] route_on_error 按 error_code 分流（任务 1, 26f90f1）
[x] Phase 2 节点接入 qa_direct 主流程（任务 0, e30eb55，计划外发现）
[x] knowledge_retrieval_node 写入 typed error_code（任务 2, 23c4249）
[x] Rerank 按策略 + 候选数门控（任务 3, f77d033）
[x] RAGExecutionMeta 含 candidates / elapsed_ms / reranked / selected_chunk_ids（任务 4, 100ed61）
[x] /chat 响应附带 rag_detail（任务 5, c79583d）
[x] E2E 三场景通过（任务 6, aebc66d）
[x] 既有测试 0 回归（145 → 145）
[x] 评审遗留收紧（fix1+2, 15bbaef）
```

### 关键计划外发现

**Phase 2 节点未接入图**：Phase 2 commits（`311bd74`、`2b7b1a6`）将 `retrieval_planner_node`、`evidence_gate_node`、`answer_policy_node`、`recovery_node` 注册为 `add_node` 但未通过 `add_conditional_edges` 接入主流程。本期插入 Task 0 修复，仅在 qa_direct 路径接线，teach_loop 保持不变以缩小风险面。

### 已知遗留（Phase 4 待办）

- **`route_on_error` 未接入 `graph_v2.py`**：函数与单元测试已交付（`26f90f1`），`error_code` 写入也已交付（`23c4249`），但图中无 `add_conditional_edges` 引用该路由。原因：接入需将固定边 `knowledge_retrieval -> explain` 改为条件边，会影响 teach_loop。Phase 4 节点装饰器/状态分层任务中一并处理。Router 函数定义处已加注释说明。
- **E2E 测试 mock 较多**：`test_phase3_e2e.py` 三个用例均 mock 了 `llm_service.invoke` / `route_intent` / `execute_retrieval_tools`。验证图接线、节点路径、元数据传播；不验证真实 LLM/检索行为。无 mock 集成测试见 Phase 4 计划。
- **`nodes.py` 已 696 行**：Phase 4 计划拆分为 `nodes/teach.py` / `nodes/qa.py` / `nodes/orchestration.py`。
- **`rag_meta_last` 类型为 `object`**：是 `LearningState` 中唯一未严格类型化的字段。Phase 4 状态分层任务中改为 `Optional[RAGExecutionMeta]`（带 `TYPE_CHECKING` 导入）。

### 下一阶段触发条件

Phase 4 在 Phase 3 合并后启动；优先解决 `route_on_error` 接入与 `nodes.py` 拆分两件低争议项。
