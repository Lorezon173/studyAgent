# RAG-Agent Decision Orchestrator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用统一 Decision Orchestrator 消除 RAG 与 Agent 决策冲突，并让执行链路严格按合同运行。

**Architecture:** 在 `AgentService` 前置统一决策入口，输出 `DecisionContract`（intent、need_rag、rag_scope、tool_plan、fallback_policy、decision_id）。下游组件只消费合同，不再二次改判。通过 trace 与回归测试保证行为一致与可追溯。

**Tech Stack:** Python 3.12, FastAPI, LangGraph, pytest

---

## File Structure

- Create: `app/services/decision_orchestrator.py`
- Modify: `app/agent/state.py`
- Modify: `app/services/agent_service.py`
- Modify: `app/services/orchestration/context_builder.py`
- Modify: `app/services/tool_executor.py`
- Modify: `app/services/rag_coordinator.py`
- Test: `tests/test_decision_orchestrator.py`
- Test: `tests/test_tool_executor.py`
- Test: `tests/test_chat_flow.py`

### Task 1: DecisionContract 测试先行

**Files:**
- Create: `tests/test_decision_orchestrator.py`

- [ ] **Step 1: 写失败测试（teach_loop 默认检索）**

```python
def test_decision_orchestrator_teach_loop_defaults_need_rag(...):
    ...
```

- [ ] **Step 2: 写失败测试（qa_direct 默认不检索）**

```python
def test_decision_orchestrator_qa_direct_can_skip_rag(...):
    ...
```

- [ ] **Step 3: 写失败测试（合同字段完整）**

```python
def test_decision_orchestrator_contract_contains_required_fields(...):
    ...
```

- [ ] **Step 4: 运行红测**

Run: `uv run pytest tests/test_decision_orchestrator.py -v`

- [ ] **Step 5: 提交**

```bash
git add -f tests/test_decision_orchestrator.py
git commit -m "test: add decision orchestrator contract tests"
```

### Task 2: 实现 DecisionOrchestrator 与状态字段

**Files:**
- Create: `app/services/decision_orchestrator.py`
- Modify: `app/agent/state.py`
- Test: `tests/test_decision_orchestrator.py`

- [ ] **Step 1: 实现 DecisionContract 与 decide()**

```python
class DecisionOrchestrator:
    @staticmethod
    def decide(...):
        ...
```

- [ ] **Step 2: 扩展 LearningState**

```python
decision_id: str
decision_contract: dict
decision_contract_fingerprint: str
need_rag: bool
rag_scope: str
tool_plan: list[str]
fallback_policy: str
```

- [ ] **Step 3: 运行测试**

Run: `uv run pytest tests/test_decision_orchestrator.py -v`

- [ ] **Step 4: 提交**

```bash
git add app/services/decision_orchestrator.py app/agent/state.py tests/test_decision_orchestrator.py
git commit -m "feat: add decision orchestrator and state contract fields"
```

### Task 3: 检索执行改为合同驱动

**Files:**
- Modify: `app/services/tool_executor.py`
- Modify: `app/services/orchestration/context_builder.py`
- Modify: `tests/test_tool_executor.py`

- [ ] **Step 1: 增加 tool_plan 优先级测试**
- [ ] **Step 2: executor 严格执行 tool_plan（含空计划语义）**
- [ ] **Step 3: context_builder 使用 need_rag/tool_plan 控制检索**
- [ ] **Step 4: 运行测试**

Run: `uv run pytest tests/test_tool_executor.py -v`

- [ ] **Step 5: 提交**

```bash
git add app/services/tool_executor.py app/services/orchestration/context_builder.py tests/test_tool_executor.py
git commit -m "refactor: make retrieval strictly contract-driven"
```

### Task 4: AgentService 接入统一决策

**Files:**
- Modify: `app/services/agent_service.py`
- Modify: `tests/test_chat_flow.py`

- [ ] **Step 1: 接入 orchestrator（每轮一次）**
- [ ] **Step 2: 写入 decision trace 与合同字段**
- [ ] **Step 3: 将 need_rag/tool_plan 传给 context builder**
- [ ] **Step 4: intent/intent_confidence 由合同提供**
- [ ] **Step 5: 增加单轮与多轮决策一致性测试**
- [ ] **Step 6: 提交**

### Task 5: 去除二次决策路径

**Files:**
- Modify: `app/services/orchestration/context_builder.py`
- Modify: `app/services/rag_coordinator.py`
- Modify: `tests/test_chat_flow.py`

- [ ] **Step 1: 主链路移除 decide_rag_call 依赖**
- [ ] **Step 2: decide_rag_call 降级为兼容+弃用提示**
- [ ] **Step 3: 增加 decision_contract 不可变断言测试**
- [ ] **Step 4: 提交**

### Task 6: 回归与文档同步

**Files:**
- Modify: `README.md`（仅在内容不一致时）

- [ ] **Step 1: 目标回归**

Run:
```bash
uv run pytest tests/test_decision_orchestrator.py tests/test_tool_executor.py tests/test_chat_flow.py -v
```

- [ ] **Step 2: 全量回归**

Run:
```bash
uv run pytest -q
```

- [ ] **Step 3: 同步 README（如需）**
- [ ] **Step 4: 提交（如有变更）**

## Self-Review Checklist

1. **Spec coverage**：每条设计目标都有对应任务。
2. **No placeholders**：无 TBD/TODO/省略实现说明。
3. **Consistency**：合同字段名在实现与测试中一致。
