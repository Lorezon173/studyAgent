# RAG-Agent Decision Orchestrator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Introduce a single Decision Orchestrator so each chat turn has one immutable decision contract that resolves RAG-vs-Agent conflicts.

**Architecture:** Add `DecisionOrchestrator` as the only decision entrypoint, returning a `DecisionContract` (`intent`, `need_rag`, `rag_scope`, `tool_plan`, `decision_id`, and fallback policy). `AgentService` consumes this contract to execute flow, while RAG/tool layers become pure executors that no longer re-decide retrieval. Keep migration low-risk by adapting existing `route_intent` and `route_tool` as internal strategy helpers.

**Tech Stack:** Python 3.12, FastAPI, LangGraph, pytest, monkeypatch-based tests

---

## File Structure (lock before coding)

- Create: `app/services/decision_orchestrator.py`
  - Single responsibility: produce `DecisionContract` from turn input and current stage.
- Modify: `app/agent/state.py`
  - Add optional decision fields used by runtime trace and downstream execution.
- Modify: `app/services/orchestration/context_builder.py`
  - Remove internal “should call RAG” decision; execute strictly from contract.
- Modify: `app/services/agent_service.py`
  - Build one contract per turn and pass it through the execution chain.
- Modify: `app/services/tool_executor.py`
  - Execute only provided `tool_plan`; do not infer retrieval decision.
- Modify: `tests/test_tool_executor.py`
  - Assert execution behavior is plan-driven.
- Modify: `tests/test_chat_flow.py`
  - Assert teach_loop default RAG and contract consistency in trace.
- Create: `tests/test_decision_orchestrator.py`
  - Unit tests for contract generation and key policy branches.

### Task 1: Add failing tests for decision contract policy

**Files:**
- Create: `tests/test_decision_orchestrator.py`
- Test: `tests/test_decision_orchestrator.py`

- [ ] **Step 1: Write the failing test (teach_loop defaults to RAG)**

```python
from app.services.decision_orchestrator import DecisionOrchestrator


def test_decision_orchestrator_teach_loop_defaults_need_rag(monkeypatch):
    monkeypatch.setattr(
        "app.services.decision_orchestrator.route_intent",
        lambda user_input: type("R", (), {"intent": "teach_loop", "confidence": 0.9, "reason": "test"})(),
    )
    monkeypatch.setattr(
        "app.services.decision_orchestrator.route_tool",
        lambda user_input, user_id=None: type(
            "T", (), {"tool": "search_local_textbook", "confidence": 0.8, "reason": "test", "candidates": ["search_local_textbook"]}
        )(),
    )

    contract = DecisionOrchestrator.decide(
        user_input="解释二分查找",
        topic="二分查找",
        user_id=1,
        current_stage="start",
    )

    assert contract["intent"] == "teach_loop"
    assert contract["need_rag"] is True
    assert contract["tool_plan"] == ["search_local_textbook"]
```

- [ ] **Step 2: Add failing test (qa_direct can disable RAG by policy)**

```python
def test_decision_orchestrator_qa_direct_can_skip_rag(monkeypatch):
    monkeypatch.setattr(
        "app.services.decision_orchestrator.route_intent",
        lambda user_input: type("R", (), {"intent": "qa_direct", "confidence": 0.9, "reason": "test"})(),
    )
    monkeypatch.setattr(
        "app.services.decision_orchestrator.route_tool",
        lambda user_input, user_id=None: type(
            "T", (), {"tool": "search_local_textbook", "confidence": 0.8, "reason": "test", "candidates": ["search_local_textbook"]}
        )(),
    )

    contract = DecisionOrchestrator.decide(
        user_input="直接回答一下",
        topic="二分查找",
        user_id=1,
        current_stage="explained",
    )

    assert contract["intent"] == "qa_direct"
    assert contract["need_rag"] is False
    assert contract["tool_plan"] == []
```

- [ ] **Step 3: Add failing test (decision_id exists and stable fields present)**

```python
def test_decision_orchestrator_contract_contains_required_fields():
    contract = DecisionOrchestrator.decide(
        user_input="解释这个概念",
        topic="算法",
        user_id=None,
        current_stage="start",
    )
    assert contract["decision_id"]
    assert set(["intent", "need_rag", "rag_scope", "tool_plan", "fallback_policy"]).issubset(contract.keys())
```

- [ ] **Step 4: Run test to verify it fails**

Run: `uv run pytest tests/test_decision_orchestrator.py -v`  
Expected: FAIL with `ModuleNotFoundError` or missing `DecisionOrchestrator`.

- [ ] **Step 5: Commit**

```bash
git add tests/test_decision_orchestrator.py
git commit -m "test: add decision orchestrator contract tests"
```

### Task 2: Implement DecisionOrchestrator and contract builder

**Files:**
- Create: `app/services/decision_orchestrator.py`
- Modify: `app/agent/state.py`
- Test: `tests/test_decision_orchestrator.py`

- [ ] **Step 1: Write minimal implementation for contract generation**

```python
# app/services/decision_orchestrator.py
from __future__ import annotations

from uuid import uuid4
from typing import TypedDict

from app.services.agent_runtime import route_intent, route_tool


class DecisionContract(TypedDict):
    decision_id: str
    intent: str
    intent_confidence: float
    need_rag: bool
    rag_scope: str
    tool_plan: list[str]
    fallback_policy: str
    reason: str


class DecisionOrchestrator:
    @staticmethod
    def decide(*, user_input: str, topic: str | None, user_id: int | None, current_stage: str) -> DecisionContract:
        intent = route_intent(user_input)
        tool = route_tool(user_input, user_id=user_id)

        need_rag = intent.intent == "teach_loop"
        if intent.intent in {"review", "replan"}:
            need_rag = False
        if intent.intent == "qa_direct":
            need_rag = False

        return {
            "decision_id": str(uuid4()),
            "intent": intent.intent,
            "intent_confidence": intent.confidence,
            "need_rag": need_rag,
            "rag_scope": "both" if need_rag and user_id is not None else ("global" if need_rag else "none"),
            "tool_plan": [tool.tool] if need_rag else [],
            "fallback_policy": "no_evidence_template",
            "reason": f"intent={intent.intent}; tool={tool.tool}",
        }
```

- [ ] **Step 2: Extend LearningState for decision fields**

```python
# app/agent/state.py (inside LearningState)
decision_id: str
decision_contract: dict
need_rag: bool
rag_scope: str
tool_plan: List[str]
fallback_policy: str
```

- [ ] **Step 3: Run tests to verify pass**

Run: `uv run pytest tests/test_decision_orchestrator.py -v`  
Expected: PASS for 3 tests.

- [ ] **Step 4: Commit**

```bash
git add app/services/decision_orchestrator.py app/agent/state.py tests/test_decision_orchestrator.py
git commit -m "feat: add decision orchestrator contract and state fields"
```

### Task 3: Make retrieval strictly contract-driven

**Files:**
- Modify: `app/services/orchestration/context_builder.py`
- Modify: `app/services/tool_executor.py`
- Modify: `tests/test_tool_executor.py`
- Test: `tests/test_tool_executor.py`

- [ ] **Step 1: Write failing test that tool executor obeys explicit tool_plan**

```python
def test_execute_retrieval_tools_obeys_explicit_tool_plan(monkeypatch):
    class DummySkill:
        def __init__(self, name):
            self.name = name

        def run(self, **kwargs):
            return {"items": [{"chunk_id": f"{self.name}-1", "score": 1.0, "text": "x"}]}

    monkeypatch.setattr("app.services.tool_executor.skill_registry.get", lambda name: DummySkill(name))

    rows, used = execute_retrieval_tools(
        query="测试",
        topic="算法",
        user_id=1,
        tool_route={"tool": "search_local_textbook"},
        tool_plan=["search_personal_memory"],
        top_k=2,
    )

    assert used == ["search_personal_memory"]
    assert rows and rows[0]["tool"] == "search_personal_memory"
```

- [ ] **Step 2: Update tool executor signature and behavior**

```python
def execute_retrieval_tools(
    *,
    query: str,
    topic: str | None,
    user_id: int | None,
    tool_route: dict[str, Any] | None,
    tool_plan: list[str] | None,
    top_k: int,
) -> tuple[list[dict[str, Any]], list[str]]:
    if tool_plan:
        tools_to_run = [x for x in tool_plan if x]
    else:
        primary = str((tool_route or {}).get("tool") or "search_local_textbook")
        tools_to_run = [primary]
```

- [ ] **Step 3: Update context builder to consume decision fields**

```python
# context_builder.py
def build_rag_context(
    topic: str | None,
    user_input: str,
    user_id: int | None = None,
    tool_route: dict | None = None,
    need_rag: bool = True,
    tool_plan: list[str] | None = None,
) -> tuple[str, list[dict], dict]:
    if not need_rag:
        return "", [], {
            "rag_attempted": False,
            "rag_skip_reason": "decision_orchestrator_skip",
            "rag_used_tools": [],
            "rag_hit_count": 0,
            "rag_fallback_used": False,
        }
```

- [ ] **Step 4: Run tests to verify pass**

Run: `uv run pytest tests/test_tool_executor.py -v`  
Expected: PASS including new explicit plan test.

- [ ] **Step 5: Commit**

```bash
git add app/services/tool_executor.py app/services/orchestration/context_builder.py tests/test_tool_executor.py
git commit -m "refactor: make retrieval execution contract-driven"
```

### Task 4: Integrate orchestrator into AgentService single-turn flow

**Files:**
- Modify: `app/services/agent_service.py`
- Modify: `tests/test_chat_flow.py`
- Test: `tests/test_chat_flow.py`

- [ ] **Step 1: Add failing chat-flow test for decision trace and teach_loop RAG default**

```python
def test_chat_turn_has_single_decision_contract_trace(monkeypatch):
    monkeypatch.setattr(
        "app.services.agent_service.DecisionOrchestrator.decide",
        lambda **kwargs: {
            "decision_id": "d-1",
            "intent": "teach_loop",
            "intent_confidence": 0.9,
            "need_rag": True,
            "rag_scope": "both",
            "tool_plan": ["search_local_textbook"],
            "fallback_policy": "no_evidence_template",
            "reason": "test",
        },
    )
    monkeypatch.setattr(
        "app.services.orchestration.context_builder.execute_rag",
        lambda **kwargs: ([], type("M", (), {"reason": "empty", "used_tools": [], "fallback_used": True})()),
    )
    monkeypatch.setattr("app.services.llm.llm_service.invoke", lambda system_prompt, user_prompt: "讲解内容")
    monkeypatch.setattr(
        "app.services.llm.llm_service.detect_topic",
        lambda user_input, current_topic: '{"topic":"二分查找","changed":false,"confidence":0.9,"reason":"稳定","comparison_mode":false}',
    )

    resp = client.post("/chat", json={"session_id": "decision-trace-1", "user_input": "解释二分查找", "user_id": 1})
    assert resp.status_code == 200
    body = resp.json()
    decision_events = [x for x in body["branch_trace"] if x.get("phase") == "decision_orchestrator"]
    assert len(decision_events) == 1
    assert decision_events[0]["decision_id"] == "d-1"
```

- [ ] **Step 2: Integrate DecisionOrchestrator in `AgentService.run`**

```python
from app.services.decision_orchestrator import DecisionOrchestrator

# inside run()
contract = DecisionOrchestrator.decide(
    user_input=user_input,
    topic=resolved_topic,
    user_id=user_id,
    current_stage="start" if existing is None else str(state.get("stage", "start")),
)
state["decision_id"] = contract["decision_id"]
state["decision_contract"] = contract
state["need_rag"] = contract["need_rag"]
state["rag_scope"] = contract["rag_scope"]
state["tool_plan"] = contract["tool_plan"]
state["fallback_policy"] = contract["fallback_policy"]
append_branch_trace(
    state,
    {
        "phase": "decision_orchestrator",
        "decision_id": contract["decision_id"],
        "intent": contract["intent"],
        "need_rag": contract["need_rag"],
        "rag_scope": contract["rag_scope"],
        "tool_plan": contract["tool_plan"],
        "reason": contract["reason"],
    },
)
```

- [ ] **Step 3: Pass contract fields into RAG context build**

```python
rag_context, citations, rag_meta = self._build_rag_context(
    state.get("topic"),
    user_input,
    state.get("user_id"),
    state.get("tool_route"),
    need_rag=state.get("need_rag", True),
    tool_plan=state.get("tool_plan", []),
)
```

- [ ] **Step 4: Ensure route intent comes from contract**

```python
state["intent"] = contract["intent"]
state["intent_confidence"] = float(contract["intent_confidence"])
```

- [ ] **Step 5: Run tests to verify pass**

Run: `uv run pytest tests/test_chat_flow.py::test_chat_turn_has_single_decision_contract_trace -v`  
Expected: PASS and trace includes exactly one `decision_orchestrator` event.

- [ ] **Step 6: Commit**

```bash
git add app/services/agent_service.py tests/test_chat_flow.py
git commit -m "refactor: route chat execution through decision orchestrator contract"
```

### Task 5: Enforce no secondary retrieval decision paths

**Files:**
- Modify: `app/services/rag_coordinator.py`
- Modify: `app/services/orchestration/context_builder.py`
- Test: `tests/test_chat_flow.py`

- [ ] **Step 1: Remove external dependency on `decide_rag_call` in context flow**

```python
# context_builder.py
# delete:
# decision = decide_rag_call(user_input=user_input)
# if not decision.should_call: return "", [], {"rag_attempted": False, "rag_skip_reason": decision.reason, "rag_used_tools": [], "rag_hit_count": 0, "rag_fallback_used": False}
# replace with contract-driven gate only (need_rag flag)
```

- [ ] **Step 2: Keep rag_coordinator as executor-only utility**

```python
# rag_coordinator.py
# retain execute_rag(query=query, topic=topic, user_id=user_id, tool_route=tool_route, top_k=top_k)
# keep decide_rag_call for backward compatibility only, mark deprecated and unused in primary path
def decide_rag_call(*, user_input: str) -> RAGCallDecision:
    return RAGCallDecision(should_call=True, reason="deprecated_use_decision_orchestrator")
```

- [ ] **Step 3: Add regression assertion in chat flow for immutable decision fields**

```python
def test_chat_decision_fields_remain_immutable_through_execution(monkeypatch):
    monkeypatch.setattr(
        "app.services.agent_service.DecisionOrchestrator.decide",
        lambda **kwargs: {
            "decision_id": "immutable-1",
            "intent": "teach_loop",
            "intent_confidence": 0.91,
            "need_rag": True,
            "rag_scope": "global",
            "tool_plan": ["search_local_textbook"],
            "fallback_policy": "no_evidence_template",
            "reason": "test",
        },
    )
    monkeypatch.setattr("app.services.llm.llm_service.invoke", lambda system_prompt, user_prompt: "讲解内容")
    monkeypatch.setattr(
        "app.services.llm.llm_service.detect_topic",
        lambda user_input, current_topic: '{"topic":"算法","changed":false,"confidence":0.9,"reason":"稳定","comparison_mode":false}',
    )
    response = client.post(
        "/chat",
        json={"session_id": "decision-immutable-1", "user_input": "解释一下二分查找", "user_id": 1},
    )
    body = response.json()
    assert body["decision_contract"]["need_rag"] == body["need_rag"]
    assert body["decision_contract"]["tool_plan"] == body["tool_plan"]
```

- [ ] **Step 4: Run focused tests**

Run: `uv run pytest tests/test_chat_flow.py -k decision -v`  
Expected: PASS for new decision immutability tests.

- [ ] **Step 5: Commit**

```bash
git add app/services/rag_coordinator.py app/services/orchestration/context_builder.py tests/test_chat_flow.py
git commit -m "refactor: remove secondary rag decision from execution path"
```

### Task 6: Full regression and docs sync

**Files:**
- Modify: `README.md` (if decision flow section exists; update only related parts)
- Test: `tests/test_decision_orchestrator.py`
- Test: `tests/test_tool_executor.py`
- Test: `tests/test_chat_flow.py`
- Test: `tests/test_agent_orchestration_refactor.py`

- [ ] **Step 1: Run target regression suite**

Run:
```bash
uv run pytest tests/test_decision_orchestrator.py tests/test_tool_executor.py tests/test_chat_flow.py tests/test_agent_orchestration_refactor.py -v
```

Expected: all PASS.

- [ ] **Step 2: Run full repository tests**

Run:
```bash
uv run pytest -q
```

Expected: full suite PASS with no new failures introduced by this refactor.

- [ ] **Step 3: Update README architecture paragraph (only if out of sync)**

```markdown
- 决策入口统一为 `DecisionOrchestrator`，单轮请求生成 `DecisionContract`，由 Agent 与 RAG 执行链路只读消费。
```

- [ ] **Step 4: Commit**

```bash
git add README.md app/services/decision_orchestrator.py app/services/agent_service.py app/services/orchestration/context_builder.py app/services/tool_executor.py app/agent/state.py tests/test_decision_orchestrator.py tests/test_tool_executor.py tests/test_chat_flow.py
git commit -m "feat: unify rag-agent decisions via decision orchestrator"
```

## Self-Review Results

1. **Spec coverage:**  
   - 单一决策入口 → Task 2/4  
   - teach_loop 默认 RAG → Task 1/4  
   - tool_route 仅执行 → Task 3/5  
   - 单轮不可变决策与 trace → Task 4/5  
   - 回归覆盖命中/未命中 → Task 1/6

2. **Placeholder scan:**  
   - No unresolved placeholder text remains in plan steps or code snippets.

3. **Type consistency:**  
   - `DecisionContract` field names are consistent across orchestrator, state, and tests (`decision_id`, `need_rag`, `tool_plan`, `fallback_policy`).
