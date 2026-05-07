# Phase 4c: Multi-Agent 协作框架实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 引入 Multi-Agent 协作能力，实现教学+评估协作场景，覆盖端到端测试。

**Architecture:** 使用 LangGraph 原生 multi-agent 模式，基于现有 Graph V2 扩展。新增 Orchestrator Agent 负责任务分配，Teaching Agent 和 Eval Agent 负责具体任务执行。

**Tech Stack:** Python 3.12, LangGraph multi-agent, LangChain

---

## 前置条件

- Phase 4a 已完成（全量回归 0 failed）
- Phase 4b 已完成（框架升级到最新版本）
- 现有 Graph V2 单 Agent 模式稳定运行

---

## File Structure

```
app/
├── agent/
│   ├── multi_agent/                # 新增目录
│   │   ├── __init__.py
│   │   ├── state.py               # MultiAgentState 定义
│   │   ├── orchestrator.py        # Orchestrator Agent
│   │   ├── teaching_agent.py      # Teaching Agent
│   │   ├── eval_agent.py          # Eval Agent
│   │   ├── graph.py               # Multi-Agent 图构建
│   │   └── routers.py             # Multi-Agent 路由函数
│   └── ...
├── api/
│   └── chat_multi.py              # 新增：/chat/multi API
tests/
├── multi_agent/                    # 新增目录
│   ├── __init__.py
│   ├── conftest.py
│   ├── unit/
│   │   ├── test_orchestrator.py
│   │   ├── test_teaching_agent.py
│   │   └── test_eval_agent.py
│   └── integration/
│       └── test_multi_agent_flow.py
```

---

## Task 0: 创建 Multi-Agent 目录结构

**Files:**
- Create: `app/agent/multi_agent/__init__.py`
- Create: `tests/multi_agent/__init__.py`

- [ ] **Step 1: 创建目录和初始化文件**

```bash
mkdir -p app/agent/multi_agent tests/multi_agent/unit tests/multi_agent/integration
touch app/agent/multi_agent/__init__.py
touch tests/multi_agent/__init__.py
touch tests/multi_agent/unit/__init__.py
touch tests/multi_agent/integration/__init__.py
```

- [ ] **Step 2: 验证目录结构**

```bash
ls -la app/agent/multi_agent/ tests/multi_agent/
```

- [ ] **Step 3: 提交**

```bash
git add app/agent/multi_agent/ tests/multi_agent/
git commit -m "feat: 创建 multi-agent 目录结构"
```

---

## Task 1: 定义 Multi-Agent 状态

**Files:**
- Create: `app/agent/multi_agent/state.py`

- [ ] **Step 1: 编写 MultiAgentState**

```python
"""Multi-Agent 协作状态定义。"""
from typing import Annotated, TypedDict, Literal
from langgraph.graph import add_messages


class MultiAgentState(TypedDict):
    """Multi-Agent 协作状态。
    
    继承单 Agent 状态，增加协作相关字段。
    """
    # 基础字段（继承自 LearningState）
    session_id: str
    user_id: int | None
    user_input: str
    topic: str | None
    
    # 协作控制
    current_agent: Literal["orchestrator", "teaching", "eval", "retrieval"]
    task_queue: list[dict]  # 任务队列
    completed_tasks: list[dict]  # 已完成任务
    
    # Agent 输出
    teaching_output: str
    eval_output: str
    retrieval_output: str
    
    # 最终结果
    final_reply: str
    mastery_score: float | None
    
    # 追踪
    branch_trace: Annotated[list[dict], add_messages]
```

- [ ] **Step 2: 验证状态定义可导入**

```bash
PYTHONPATH=. uv run python -c "from app.agent.multi_agent.state import MultiAgentState; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: 提交**

```bash
git add app/agent/multi_agent/state.py
git commit -m "feat: 定义 MultiAgentState"
```

---

## Task 2: 实现 Orchestrator Agent

**Files:**
- Create: `app/agent/multi_agent/orchestrator.py`

- [ ] **Step 1: 编写 Orchestrator Agent**

```python
"""Orchestrator Agent：任务分配和结果汇总。"""
from app.agent.multi_agent.state import MultiAgentState


def orchestrator_node(state: MultiAgentState) -> dict:
    """Orchestrator 节点：分析意图，分配任务。
    
    职责：
    1. 分析用户输入意图
    2. 决定由哪个 Agent 处理
    3. 构建任务队列
    """
    user_input = state.get("user_input", "")
    topic = state.get("topic")
    
    # 简单意图识别（后续可替换为 LLM）
    if "评估" in user_input or "理解程度" in user_input:
        return {
            "current_agent": "eval",
            "task_queue": [{"type": "evaluate", "topic": topic}],
        }
    
    if "讲解" in user_input or "学" in user_input:
        return {
            "current_agent": "teaching",
            "task_queue": [{"type": "teach", "topic": topic}],
        }
    
    # 默认：教学 + 评估流水线
    return {
        "current_agent": "teaching",
        "task_queue": [
            {"type": "teach", "topic": topic},
            {"type": "evaluate", "topic": topic},
        ],
    }


def aggregator_node(state: MultiAgentState) -> dict:
    """汇总节点：整合各 Agent 输出，生成最终回复。"""
    teaching_output = state.get("teaching_output", "")
    eval_output = state.get("eval_output", "")
    
    # 构建最终回复
    final_reply = f"{teaching_output}\n\n--- 评估 ---\n{eval_output}" if eval_output else teaching_output
    
    return {
        "final_reply": final_reply,
        "branch_trace": [{"phase": "aggregator", "agents_used": ["teaching", "eval"]}],
    }
```

- [ ] **Step 2: 验证节点可导入**

```bash
PYTHONPATH=. uv run python -c "from app.agent.multi_agent.orchestrator import orchestrator_node; print('OK')"
```

- [ ] **Step 3: 提交**

```bash
git add app/agent/multi_agent/orchestrator.py
git commit -m "feat: 实现 Orchestrator Agent"
```

---

## Task 3: 实现 Teaching Agent

**Files:**
- Create: `app/agent/multi_agent/teaching_agent.py`

- [ ] **Step 1: 编写 Teaching Agent**

```python
"""Teaching Agent：知识讲解。"""
from app.agent.multi_agent.state import MultiAgentState
from app.services.llm import llm_service


def teaching_agent_node(state: MultiAgentState) -> dict:
    """Teaching Agent 节点：讲解知识点。
    
    职责：
    1. 根据主题和用户输入生成讲解
    2. 适合用户当前理解程度的解释
    """
    topic = state.get("topic") or "未指定主题"
    user_input = state.get("user_input", "")
    
    # 调用 LLM 生成讲解
    system_prompt = "你是一个专业的教学助手，擅长用通俗易懂的方式讲解概念。"
    user_prompt = f"主题：{topic}\n用户问题：{user_input}\n\n请给出清晰的讲解，并用例子说明。"
    
    teaching_output = llm_service.invoke(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
    )
    
    return {
        "teaching_output": teaching_output,
        "current_agent": "eval",  # 下一步进入评估
        "branch_trace": [{"phase": "teaching_agent", "topic": topic}],
    }
```

- [ ] **Step 2: 验证节点可导入**

```bash
PYTHONPATH=. uv run python -c "from app.agent.multi_agent.teaching_agent import teaching_agent_node; print('OK')"
```

- [ ] **Step 3: 提交**

```bash
git add app/agent/multi_agent/teaching_agent.py
git commit -m "feat: 实现 Teaching Agent"
```

---

## Task 4: 实现 Eval Agent

**Files:**
- Create: `app/agent/multi_agent/eval_agent.py`

- [ ] **Step 1: 编写 Eval Agent**

```python
"""Eval Agent：理解程度评估。"""
import json
from app.agent.multi_agent.state import MultiAgentState
from app.services.llm import llm_service


def eval_agent_node(state: MultiAgentState) -> dict:
    """Eval Agent 节点：评估用户理解程度。
    
    职责：
    1. 基于讲解内容评估用户理解程度
    2. 生成评估报告
    """
    topic = state.get("topic") or "未指定主题"
    teaching_output = state.get("teaching_output", "")
    user_input = state.get("user_input", "")
    
    # 调用 LLM 进行评估
    system_prompt = "你是一个学习评估专家，负责评估用户对知识的理解程度。"
    user_prompt = f"""
主题：{topic}
讲解内容：{teaching_output}
用户输入：{user_input}

请评估用户的理解程度，返回 JSON 格式：
{{"mastery_score": 0-100, "understanding_level": "low/medium/high", "feedback": "评估反馈"}}
"""
    
    result = llm_service.invoke(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
    )
    
    # 解析评估结果
    try:
        eval_data = json.loads(result)
        mastery_score = eval_data.get("mastery_score", 50)
    except json.JSONDecodeError:
        mastery_score = 50
    
    return {
        "eval_output": result,
        "mastery_score": mastery_score,
        "current_agent": "aggregator",  # 下一步进入汇总
        "branch_trace": [{"phase": "eval_agent", "mastery_score": mastery_score}],
    }
```

- [ ] **Step 2: 验证节点可导入**

```bash
PYTHONPATH=. uv run python -c "from app.agent.multi_agent.eval_agent import eval_agent_node; print('OK')"
```

- [ ] **Step 3: 提交**

```bash
git add app/agent/multi_agent/eval_agent.py
git commit -m "feat: 实现 Eval Agent"
```

---

## Task 5: 实现 Multi-Agent 路由

**Files:**
- Create: `app/agent/multi_agent/routers.py`

- [ ] **Step 1: 编写路由函数**

```python
"""Multi-Agent 路由函数。"""
from app.agent.multi_agent.state import MultiAgentState


def route_by_agent(state: MultiAgentState) -> str:
    """根据 current_agent 字段路由到对应 Agent。"""
    current_agent = state.get("current_agent", "orchestrator")
    
    agent_map = {
        "orchestrator": "orchestrator",
        "teaching": "teaching_agent",
        "eval": "eval_agent",
        "aggregator": "aggregator",
    }
    
    return agent_map.get(current_agent, "orchestrator")


def route_after_teaching(state: MultiAgentState) -> str:
    """教学后路由：检查是否有评估任务。"""
    task_queue = state.get("task_queue", [])
    
    # 检查是否有评估任务
    for task in task_queue:
        if task.get("type") == "evaluate":
            return "eval_agent"
    
    # 没有评估任务，直接汇总
    return "aggregator"
```

- [ ] **Step 2: 验证路由可导入**

```bash
PYTHONPATH=. uv run python -c "from app.agent.multi_agent.routers import route_by_agent; print('OK')"
```

- [ ] **Step 3: 提交**

```bash
git add app/agent/multi_agent/routers.py
git commit -m "feat: 实现 Multi-Agent 路由函数"
```

---

## Task 6: 构建 Multi-Agent 图

**Files:**
- Create: `app/agent/multi_agent/graph.py`

- [ ] **Step 1: 编写图构建函数**

```python
"""Multi-Agent 协作图构建。"""
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from app.agent.multi_agent.state import MultiAgentState
from app.agent.multi_agent.orchestrator import orchestrator_node, aggregator_node
from app.agent.multi_agent.teaching_agent import teaching_agent_node
from app.agent.multi_agent.eval_agent import eval_agent_node
from app.agent.multi_agent.routers import route_by_agent


def build_multi_agent_graph():
    """构建 Multi-Agent 协作图。"""
    graph = StateGraph(MultiAgentState)
    
    # 添加节点
    graph.add_node("orchestrator", orchestrator_node)
    graph.add_node("teaching_agent", teaching_agent_node)
    graph.add_node("eval_agent", eval_agent_node)
    graph.add_node("aggregator", aggregator_node)
    
    # 设置入口
    graph.set_entry_point("orchestrator")
    
    # 条件边：根据 current_agent 路由
    graph.add_conditional_edges(
        "orchestrator",
        route_by_agent,
        {
            "teaching_agent": "teaching_agent",
            "eval_agent": "eval_agent",
            "aggregator": "aggregator",
        }
    )
    
    # 教学后路由
    graph.add_conditional_edges(
        "teaching_agent",
        route_by_agent,
        {
            "eval_agent": "eval_agent",
            "aggregator": "aggregator",
        }
    )
    
    # 评估后进入汇总
    graph.add_edge("eval_agent", "aggregator")
    
    # 汇总后结束
    graph.add_edge("aggregator", END)
    
    return graph.compile(checkpointer=MemorySaver())


# 单例
_multi_agent_graph = None


def get_multi_agent_graph():
    """获取 Multi-Agent 图单例。"""
    global _multi_agent_graph
    if _multi_agent_graph is None:
        _multi_agent_graph = build_multi_agent_graph()
    return _multi_agent_graph
```

- [ ] **Step 2: 验证图可构建**

```bash
PYTHONPATH=. uv run python -c "from app.agent.multi_agent.graph import build_multi_agent_graph; g = build_multi_agent_graph(); print('Graph nodes:', list(g.nodes.keys()))"
```

Expected: 输出节点列表

- [ ] **Step 3: 提交**

```bash
git add app/agent/multi_agent/graph.py
git commit -m "feat: 构建 Multi-Agent 协作图"
```

---

## Task 7: 创建 /chat/multi API

**Files:**
- Create: `app/api/chat_multi.py`
- Modify: `app/main.py`（注册路由）

- [ ] **Step 1: 编写 API 路由**

```python
"""Multi-Agent Chat API。"""
from fastapi import APIRouter
from pydantic import BaseModel

from app.agent.multi_agent.graph import get_multi_agent_graph

router = APIRouter(prefix="/chat", tags=["multi-agent"])


class MultiChatRequest(BaseModel):
    session_id: str
    user_id: int | None = None
    topic: str | None = None
    user_input: str


class MultiChatResponse(BaseModel):
    session_id: str
    final_reply: str
    teaching_output: str | None = None
    eval_output: str | None = None
    mastery_score: float | None = None


@router.post("/multi", response_model=MultiChatResponse)
async def chat_multi(request: MultiChatRequest):
    """Multi-Agent 协作对话接口。"""
    graph = get_multi_agent_graph()
    
    config = {"configurable": {"thread_id": request.session_id}}
    
    state = {
        "session_id": request.session_id,
        "user_id": request.user_id,
        "user_input": request.user_input,
        "topic": request.topic,
        "task_queue": [],
        "completed_tasks": [],
        "teaching_output": "",
        "eval_output": "",
        "retrieval_output": "",
        "final_reply": "",
        "mastery_score": None,
        "branch_trace": [],
    }
    
    result = graph.invoke(state, config=config)
    
    return MultiChatResponse(
        session_id=request.session_id,
        final_reply=result.get("final_reply", ""),
        teaching_output=result.get("teaching_output"),
        eval_output=result.get("eval_output"),
        mastery_score=result.get("mastery_score"),
    )
```

- [ ] **Step 2: 注册路由到 main.py**

在 `app/main.py` 中添加：

```python
from app.api.chat_multi import router as multi_chat_router
app.include_router(multi_chat_router)
```

- [ ] **Step 3: 验证 API 可访问**

```bash
PYTHONPATH=. uv run uvicorn app.main:app --host 127.0.0.1 --port 1900 &
sleep 3
curl -X POST http://127.0.0.1:1900/chat/multi \
  -H "Content-Type: application/json" \
  -d '{"session_id":"test-1","topic":"二分查找","user_input":"我想学二分查找"}'
```

Expected: 返回 JSON 响应

- [ ] **Step 4: 提交**

```bash
git add app/api/chat_multi.py app/main.py
git commit -m "feat: 添加 /chat/multi API"
```

---

## Task 8: 编写单元测试

**Files:**
- Create: `tests/multi_agent/conftest.py`
- Create: `tests/multi_agent/unit/test_orchestrator.py`
- Create: `tests/multi_agent/unit/test_teaching_agent.py`
- Create: `tests/multi_agent/unit/test_eval_agent.py`

- [ ] **Step 1: 编写 conftest.py**

```python
"""Multi-Agent 测试 fixtures。"""
import pytest


@pytest.fixture
def multi_agent_state():
    """创建测试用的 Multi-Agent 状态。"""
    return {
        "session_id": "test-session",
        "user_id": 1,
        "user_input": "我想学二分查找",
        "topic": "二分查找",
        "current_agent": "orchestrator",
        "task_queue": [],
        "completed_tasks": [],
        "teaching_output": "",
        "eval_output": "",
        "retrieval_output": "",
        "final_reply": "",
        "mastery_score": None,
        "branch_trace": [],
    }
```

- [ ] **Step 2: 编写 Orchestrator 测试**

```python
"""Orchestrator Agent 单元测试。"""
from app.agent.multi_agent.orchestrator import orchestrator_node


def test_orchestrator_routes_to_teaching(multi_agent_state):
    """测试路由到教学 Agent。"""
    multi_agent_state["user_input"] = "我想学二分查找"
    
    result = orchestrator_node(multi_agent_state)
    
    assert result["current_agent"] == "teaching"
    assert len(result["task_queue"]) >= 1


def test_orchestrator_routes_to_eval(multi_agent_state):
    """测试路由到评估 Agent。"""
    multi_agent_state["user_input"] = "评估我的理解程度"
    
    result = orchestrator_node(multi_agent_state)
    
    assert result["current_agent"] == "eval"
```

- [ ] **Step 3: 编写 Teaching Agent 测试**

```python
"""Teaching Agent 单元测试。"""
from app.agent.multi_agent.teaching_agent import teaching_agent_node


def test_teaching_agent_generates_output(multi_agent_state, monkeypatch):
    """测试教学 Agent 生成输出。"""
    def fake_invoke(system_prompt, user_prompt, stream_output=False):
        return "这是讲解内容。"
    
    monkeypatch.setattr("app.services.llm.llm_service.invoke", fake_invoke)
    
    result = teaching_agent_node(multi_agent_state)
    
    assert "teaching_output" in result
    assert len(result["teaching_output"]) > 0
```

- [ ] **Step 4: 编写 Eval Agent 测试**

```python
"""Eval Agent 单元测试。"""
from app.agent.multi_agent.eval_agent import eval_agent_node


def test_eval_agent_returns_score(multi_agent_state, monkeypatch):
    """测试评估 Agent 返回分数。"""
    def fake_invoke(system_prompt, user_prompt, stream_output=False):
        return '{"mastery_score": 75, "understanding_level": "medium", "feedback": "理解一般"}'
    
    monkeypatch.setattr("app.services.llm.llm_service.invoke", fake_invoke)
    
    result = eval_agent_node(multi_agent_state)
    
    assert result["mastery_score"] == 75
```

- [ ] **Step 5: 运行测试**

```bash
PYTHONPATH=. uv run pytest tests/multi_agent/unit/ -v --tb=short
```

Expected: 全部 PASS

- [ ] **Step 6: 提交**

```bash
git add tests/multi_agent/
git commit -m "test: 添加 Multi-Agent 单元测试"
```

---

## Task 9: 编写集成测试

**Files:**
- Create: `tests/multi_agent/integration/test_multi_agent_flow.py`

- [ ] **Step 1: 编写端到端测试**

```python
"""Multi-Agent 协作流程集成测试。"""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_multi_agent_teach_and_eval_flow(monkeypatch):
    """测试教学+评估协作流程。"""
    def fake_invoke(system_prompt, user_prompt, stream_output=False):
        if "教学助手" in system_prompt:
            return "二分查找每次取中间值比较，缩小搜索范围。"
        if "评估专家" in system_prompt:
            return '{"mastery_score": 80, "understanding_level": "high", "feedback": "理解较好"}'
        return "默认"
    
    monkeypatch.setattr("app.services.llm.llm_service.invoke", fake_invoke)
    
    resp = client.post(
        "/chat/multi",
        json={
            "session_id": "multi-test-1",
            "topic": "二分查找",
            "user_input": "我想学二分查找",
        },
    )
    
    assert resp.status_code == 200
    body = resp.json()
    
    assert body["session_id"] == "multi-test-1"
    assert "final_reply" in body
    assert "讲解" in body["final_reply"] or "评估" in body["final_reply"]
    assert body["mastery_score"] is not None


def test_multi_agent_api_returns_teaching_output(monkeypatch):
    """测试 API 返回教学输出。"""
    def fake_invoke(system_prompt, user_prompt, stream_output=False):
        if "教学助手" in system_prompt:
            return "教学输出内容"
        return '{"mastery_score": 50}'
    
    monkeypatch.setattr("app.services.llm.llm_service.invoke", fake_invoke)
    
    resp = client.post(
        "/chat/multi",
        json={
            "session_id": "multi-test-2",
            "topic": "测试主题",
            "user_input": "学这个",
        },
    )
    
    assert resp.status_code == 200
    body = resp.json()
    assert body["teaching_output"] == "教学输出内容"
```

- [ ] **Step 2: 运行测试**

```bash
PYTHONPATH=. uv run pytest tests/multi_agent/integration/ -v --tb=short
```

Expected: 全部 PASS

- [ ] **Step 3: 提交**

```bash
git add tests/multi_agent/integration/
git commit -m "test: 添加 Multi-Agent 集成测试"
```

---

## Task 10: 更新文档

**Files:**
- Modify: `README.md`

- [ ] **Step 1: 更新 README**

```markdown
## Multi-Agent 协作

Phase 4c 引入 Multi-Agent 协作能力，支持教学+评估协作场景。

### 架构

```
Orchestrator Agent (任务分配)
    │
    ├── Teaching Agent (知识讲解)
    │
    └── Eval Agent (理解评估)
```

### API

\`\`\`bash
POST /chat/multi
{
  "session_id": "xxx",
  "topic": "二分查找",
  "user_input": "我想学二分查找"
}
\`\`\`

### 运行测试

\`\`\`bash
PYTHONPATH=. uv run pytest tests/multi_agent/ -v
\`\`\`
```

- [ ] **Step 2: 提交**

```bash
git add README.md
git commit -m "docs: 更新 README - Multi-Agent 协作框架"
```

---

## Task 11: 全量回归验证

**Files:**
- 无文件修改

- [ ] **Step 1: 运行全量测试**

```bash
PYTHONPATH=. uv run pytest tests/ -q --tb=no
```

Expected: 全部 PASS

- [ ] **Step 2: 运行 SLO 门禁**

```bash
PYTHONPATH=. uv run python -m slo.run_regression
```

Expected: 通过

---

## Summary

| Task | 描述 | 文件数 |
|------|------|--------|
| Task 0 | 创建目录结构 | 2 |
| Task 1 | 定义状态 | 1 |
| Task 2 | Orchestrator Agent | 1 |
| Task 3 | Teaching Agent | 1 |
| Task 4 | Eval Agent | 1 |
| Task 5 | 路由函数 | 1 |
| Task 6 | 图构建 | 1 |
| Task 7 | API 路由 | 2 |
| Task 8 | 单元测试 | 4 |
| Task 9 | 集成测试 | 1 |
| Task 10 | 文档更新 | 1 |
| Task 11 | 全量验证 | - |

**验收标准：**
- Multi-Agent 协作流程可运行
- 端到端测试覆盖协作场景
- 全量回归通过
- SLO 门禁通过
