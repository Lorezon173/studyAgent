# RAG 质量底座（Phase 1）实施计划

> **给 Agentic Worker：** 必须使用 `superpowers:subagent-driven-development`（推荐）或 `superpowers:executing-plans` 按任务逐步执行。步骤使用复选框语法（`- [ ]`）跟踪。

**目标：** 在不替换现有技术栈的前提下，交付已批准 12 周方案的前 4 周内容，重点提升 RAG 查询规划、证据置信度评估、低证据场景响应边界。

**架构：** 保持现有 LangGraph + FastAPI + 服务层边界不变。在检索前新增查询规划单元，在检索后新增证据策略单元，再把元数据串入 ContextBuilder 与 Graph V2 回答节点。确保改动局部化、可测试、可回滚。

**技术栈：** Python 3.12、FastAPI、LangGraph、pytest、uv

---

## 范围校验（基于已批准 Spec）

当前 Spec 包含三个相对独立子系统：  
1. RAG 质量改进  
2. 编排路由升级  
3. SLO/运维治理

本计划覆盖：**子系统 1（RAG 质量）+ 为暴露置信度与边界声明所需的最小编排触点**。  
子系统 2 和 3 请在本计划落地后另起后续实施计划。

---

## 文件结构

```text
app/
├── services/
│   ├── query_planner.py                 # 新增：查询理解 + 检索预算
│   ├── evidence_policy.py               # 新增：证据置信度策略
│   ├── rag_coordinator.py               # 修改：接入查询计划并输出增强元数据
│   └── orchestration/context_builder.py # 修改：将 query/evidence 元数据注入上下文
├── agent/
│   ├── state.py                         # 修改：新增证据与置信度字段
│   ├── nodes.py                         # 修改：追加低证据边界声明
│   ├── routers.py                       # 修改：新增置信度感知路由
│   └── graph_v2.py                      # 修改：接入新的置信度路由
├── api/
│   └── chat.py                          # 修改：返回证据元数据
└── models/
    └── schemas.py                       # 修改：ChatResponse 增加证据字段

tests/
├── test_query_planner.py                # 新增
├── test_evidence_policy.py              # 新增
├── test_agent_conditional_edges.py      # 修改：置信度路由测试
├── test_agent_graph_v2.py               # 修改：低证据响应测试
└── test_chat_flow.py                    # 修改：响应包含证据元数据
```

---

### 任务 1：新增查询规划单元（检索前）

**文件：**
- 新建：`app/services/query_planner.py`
- 新建：`tests/test_query_planner.py`

- [ ] **步骤 1：先写失败测试（查询模式与预算）**

```python
# tests/test_query_planner.py
from app.services.query_planner import build_query_plan


def test_build_query_plan_for_fact_question():
    plan = build_query_plan("二分查找是什么？", topic="算法")
    assert plan.mode == "fact"
    assert plan.top_k >= 3
    assert plan.enable_web is False


def test_build_query_plan_for_freshness_question():
    plan = build_query_plan("LangGraph 最新版本是什么", topic="框架")
    assert plan.mode == "freshness"
    assert plan.enable_web is True
    assert plan.top_k >= 4
```

- [ ] **步骤 2：运行测试并确认失败**

运行：`$env:PYTHONPATH='.'; uv run pytest -q tests/test_query_planner.py`  
期望：`FAIL`，提示 `ModuleNotFoundError: No module named 'app.services.query_planner'`

- [ ] **步骤 3：实现 `build_query_plan()` 最小代码**

```python
# app/services/query_planner.py
from dataclasses import dataclass


@dataclass(frozen=True)
class QueryPlan:
    mode: str
    rewritten_query: str
    top_k: int
    enable_web: bool
    reason: str


def build_query_plan(user_input: str, topic: str | None) -> QueryPlan:
    text = (user_input or "").strip()
    lowered = text.lower()
    if any(k in lowered for k in ["最新", "最近", "release", "版本", "today", "this week"]):
        return QueryPlan(
            mode="freshness",
            rewritten_query=f"{text} {topic or ''}".strip(),
            top_k=5,
            enable_web=True,
            reason="freshness_signal_detected",
        )
    if any(k in text for k in ["对比", "区别", "优缺点"]):
        return QueryPlan(
            mode="comparison",
            rewritten_query=text,
            top_k=5,
            enable_web=False,
            reason="comparison_signal_detected",
        )
    return QueryPlan(
        mode="fact",
        rewritten_query=text,
        top_k=3,
        enable_web=False,
        reason="default_fact_mode",
    )
```

- [ ] **步骤 4：再次运行测试并确认通过**

运行：`$env:PYTHONPATH='.'; uv run pytest -q tests/test_query_planner.py`  
期望：`2 passed`

- [ ] **步骤 5：提交**

```bash
git add app/services/query_planner.py tests/test_query_planner.py
git commit -m "feat(rag): add query planning unit with mode and budget"
```

---

### 任务 2：将 Query Plan 接入 RAG Coordinator

**文件：**
- 修改：`app/services/rag_coordinator.py`
- 修改：`tests/test_rag_solution_p0.py`

- [ ] **步骤 1：新增失败测试（验证 `execute_rag()` 使用查询计划）**

```python
# 追加到 tests/test_rag_solution_p0.py
def test_execute_rag_uses_query_plan(monkeypatch):
    from app.services.rag_coordinator import execute_rag

    monkeypatch.setattr(
        "app.services.rag_coordinator.build_query_plan",
        lambda user_input, topic: type("P", (), {
            "mode": "freshness",
            "rewritten_query": "LangGraph 最新版本",
            "top_k": 5,
            "enable_web": True,
            "reason": "test",
        })(),
    )
    monkeypatch.setattr(
        "app.services.rag_coordinator.execute_retrieval_tools",
        lambda **kwargs: ([{"chunk_id": "c1", "text": "x", "score": 1.0}], ["search_web"]),
    )

    rows, meta = execute_rag(query="LangGraph 最新版本", topic="框架", user_id=1, tool_route=None, top_k=2)
    assert rows
    assert meta.hit_count == 1
    assert meta.reason == "tool_retrieval"
    assert meta.used_tools == ["search_web"]
    assert meta.query_mode == "freshness"
```

- [ ] **步骤 2：运行单测并确认失败**

运行：`$env:PYTHONPATH='.'; uv run pytest -q tests/test_rag_solution_p0.py -k query_plan`  
期望：`FAIL`，提示 `RAGExecutionMeta` 缺少 `query_mode`

- [ ] **步骤 3：实现 planner 集成与增强元数据**

```python
# app/services/rag_coordinator.py 关键改动
from app.services.query_planner import build_query_plan

@dataclass
class RAGExecutionMeta:
    reason: str
    used_tools: list[str]
    hit_count: int
    fallback_used: bool
    query_mode: str
    query_reason: str

def execute_rag(...):
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
    if rows:
        return rows, RAGExecutionMeta(
            reason="tool_retrieval",
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

- [ ] **步骤 4：回归相关测试**

运行：`$env:PYTHONPATH='.'; uv run pytest -q tests/test_rag_solution_p0.py -k "query_plan or rag_decision"`  
期望：`PASS`

- [ ] **步骤 5：提交**

```bash
git add app/services/rag_coordinator.py tests/test_rag_solution_p0.py
git commit -m "feat(rag): wire query planner into rag coordinator metadata"
```

---

### 任务 3：新增证据置信度策略（检索后）

**文件：**
- 新建：`app/services/evidence_policy.py`
- 新建：`tests/test_evidence_policy.py`
- 修改：`app/services/orchestration/context_builder.py`

- [ ] **步骤 1：先写失败测试（置信度分级）**

```python
# tests/test_evidence_policy.py
from app.services.evidence_policy import evaluate_evidence


def test_evidence_high_confidence():
    result = evaluate_evidence([{"score": 0.91}, {"score": 0.83}], min_hits=2)
    assert result.level == "high"
    assert result.low_evidence is False


def test_evidence_low_confidence_when_insufficient_hits():
    result = evaluate_evidence([{"score": 0.42}], min_hits=2)
    assert result.level == "low"
    assert result.low_evidence is True
```

- [ ] **步骤 2：运行测试并确认失败**

运行：`$env:PYTHONPATH='.'; uv run pytest -q tests/test_evidence_policy.py`  
期望：`FAIL`，提示无法导入 `app.services.evidence_policy`

- [ ] **步骤 3：实现策略并接入 ContextBuilder**

```python
# app/services/evidence_policy.py
from dataclasses import dataclass


@dataclass(frozen=True)
class EvidenceAssessment:
    level: str
    low_evidence: bool
    hit_count: int
    avg_score: float


def evaluate_evidence(rows: list[dict], min_hits: int = 2) -> EvidenceAssessment:
    scores = [float(x.get("score", 0.0)) for x in rows if isinstance(x, dict)]
    hit_count = len(scores)
    avg_score = sum(scores) / hit_count if hit_count else 0.0
    if hit_count >= min_hits and avg_score >= 0.7:
        return EvidenceAssessment(level="high", low_evidence=False, hit_count=hit_count, avg_score=avg_score)
    if hit_count >= 1 and avg_score >= 0.45:
        return EvidenceAssessment(level="medium", low_evidence=False, hit_count=hit_count, avg_score=avg_score)
    return EvidenceAssessment(level="low", low_evidence=True, hit_count=hit_count, avg_score=avg_score)
```

```python
# app/services/orchestration/context_builder.py 中 build_rag_context 的关键增量
from app.services.evidence_policy import evaluate_evidence

assessment = evaluate_evidence(rows)
rag_meta = {
    "rag_attempted": True,
    "rag_skip_reason": "",
    "rag_used_tools": meta.used_tools,
    "rag_hit_count": len(rows),
    "rag_fallback_used": meta.fallback_used,
    "rag_query_mode": meta.query_mode,
    "rag_query_reason": meta.query_reason,
    "rag_confidence_level": assessment.level,
    "rag_low_evidence": assessment.low_evidence,
    "rag_avg_score": assessment.avg_score,
}
return source_tag + "\n" + "\n".join(lines), citations, rag_meta
```

- [ ] **步骤 4：运行相关测试**

运行：`$env:PYTHONPATH='.'; uv run pytest -q tests/test_evidence_policy.py tests/test_rag_solution_p0.py -k "confidence or rag_decision"`  
期望：`PASS`

- [ ] **步骤 5：提交**

```bash
git add app/services/evidence_policy.py app/services/orchestration/context_builder.py tests/test_evidence_policy.py
git commit -m "feat(rag): add evidence confidence policy and context metadata"
```

---

### 任务 4：在 Graph V2 路由与回答中透出置信度

**文件：**
- 修改：`app/agent/state.py`
- 修改：`app/agent/routers.py`
- 修改：`app/agent/graph_v2.py`
- 修改：`app/agent/nodes.py`
- 修改：`tests/test_agent_conditional_edges.py`
- 修改：`tests/test_agent_graph_v2.py`

- [ ] **步骤 1：新增失败测试（低置信证据走 LLM 回退）**

```python
# 追加到 tests/test_agent_conditional_edges.py
def test_route_after_rag_low_confidence_falls_back_to_llm():
    state = {"rag_found": True, "rag_confidence_level": "low"}
    assert route_after_rag(state) == "llm_answer"
```

- [ ] **步骤 2：运行测试并确认失败**

运行：`$env:PYTHONPATH='.'; uv run pytest -q tests/test_agent_conditional_edges.py -k low_confidence`  
期望：`FAIL`，因为当前 `route_after_rag` 尚未考虑置信度

- [ ] **步骤 3：实现置信度路由与低证据边界声明**

```python
# app/agent/state.py 增量字段
class LearningState(TypedDict, total=False):
    ...
    rag_confidence_level: str
    rag_low_evidence: bool
    rag_avg_score: float
```

```python
# app/agent/routers.py
def route_after_rag(state: LearningState) -> Literal["rag_answer", "llm_answer"]:
    if not state.get("rag_found", False):
        return "llm_answer"
    if state.get("rag_confidence_level") == "low":
        return "llm_answer"
    return "rag_answer"
```

```python
# app/agent/nodes.py 在 llm_answer_node 与 rag_answer_node 结果拼接时加入
if state.get("rag_low_evidence"):
    state["reply"] = (
        f"{state['reply']}\n\n"
        "【证据边界声明】当前可用证据较弱，以下内容包含推断，请优先结合教材或权威资料核验。"
    )
```

- [ ] **步骤 4：运行图与路由测试**

运行：`$env:PYTHONPATH='.'; uv run pytest -q tests/test_agent_conditional_edges.py tests/test_agent_graph_v2.py -k "rag or confidence"`  
期望：`PASS`

- [ ] **步骤 5：提交**

```bash
git add app/agent/state.py app/agent/routers.py app/agent/nodes.py app/agent/graph_v2.py tests/test_agent_conditional_edges.py tests/test_agent_graph_v2.py
git commit -m "feat(agent): make rag routing confidence-aware with low-evidence boundary notice"
```

---

### 任务 5：在 Chat API 响应中输出证据元数据

**文件：**
- 修改：`app/models/schemas.py`
- 修改：`app/api/chat.py`
- 修改：`tests/test_chat_flow.py`

- [ ] **步骤 1：新增失败测试（响应包含证据字段）**

```python
# 追加到 tests/test_chat_flow.py
def test_chat_response_contains_evidence_meta(monkeypatch):
    monkeypatch.setattr(
        "app.services.agent_service.agent_service.run",
        lambda **kwargs: {
            "session_id": "s-evidence",
            "stage": "rag_answered",
            "reply": "回答",
            "summary": None,
            "citations": [],
            "rag_confidence_level": "medium",
            "rag_low_evidence": False,
        },
    )
    resp = client.post("/chat", json={"session_id": "s-evidence", "user_input": "二分查找是什么"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["rag_confidence_level"] == "medium"
    assert data["rag_low_evidence"] is False
```

- [ ] **步骤 2：运行测试并确认失败**

运行：`$env:PYTHONPATH='.'; uv run pytest -q tests/test_chat_flow.py -k evidence_meta`  
期望：`FAIL`，响应缺少新增字段

- [ ] **步骤 3：在 Schema 与 API 中补齐字段映射**

```python
# app/models/schemas.py
class ChatResponse(BaseModel):
    session_id: str
    stage: str
    reply: str
    summary: str | None = None
    citations: list[dict] = Field(default_factory=list)
    rag_confidence_level: str | None = None
    rag_low_evidence: bool | None = None
```

```python
# app/api/chat.py
return ChatResponse(
    session_id=result["session_id"],
    stage=result.get("stage", "unknown"),
    reply=result.get("reply", ""),
    summary=result.get("summary"),
    citations=result.get("citations", []),
    rag_confidence_level=result.get("rag_confidence_level"),
    rag_low_evidence=result.get("rag_low_evidence"),
)
```

- [ ] **步骤 4：运行 API 相关测试**

运行：`$env:PYTHONPATH='.'; uv run pytest -q tests/test_chat_flow.py tests/test_chat_stream_api.py -k "chat"`  
期望：`PASS`

- [ ] **步骤 5：提交**

```bash
git add app/models/schemas.py app/api/chat.py tests/test_chat_flow.py
git commit -m "feat(api): expose rag confidence metadata in chat response"
```

---

### 任务 6：Phase 1 回归验证与文档同步

**文件：**
- 修改：`docs/superpowers/specs/004-2026-04-20-rag-agent-framework-evolution-design.md`

- [ ] **步骤 1：运行聚焦回归集**

运行：  
`$env:PYTHONPATH='.'; uv run pytest -q tests/test_query_planner.py tests/test_evidence_policy.py tests/test_rag_solution_p0.py tests/test_agent_conditional_edges.py tests/test_agent_graph_v2.py tests/test_chat_flow.py tests/test_chat_stream_api.py`  
期望：`PASS`

- [ ] **步骤 2：运行全量测试**

运行：`$env:PYTHONPATH='.'; uv run pytest -q`  
期望：`PASS`

- [ ] **步骤 3：更新 Spec 进度备注**

```markdown
## Progress Note (Phase 1 Delivered)

- Query planning integrated before retrieval.
- Evidence confidence and low-evidence signaling integrated.
- Graph V2 and Chat API now surface confidence metadata.
```

- [ ] **步骤 4：提交**

```bash
git add docs/superpowers/specs/004-2026-04-20-rag-agent-framework-evolution-design.md
git commit -m "docs: mark phase-1 rag quality foundation delivered"
```

---

## Spec 覆盖性检查

本计划已覆盖：
1. 查询理解与检索预算（Spec §5.1）  
2. 检索后证据分级与边界声明（Spec §5.3、§7）  
3. 在编排与 API 中透出置信度元数据（Spec §6、§9）

本计划未覆盖（需后续独立计划）：
1. 编排节点全面扩展（`retrieval_planner_node`、`recovery_node` 全量落地）  
2. SLO 守门自动化、灰度发布流水线、容量治理看板

