# Phase 4c: Multi-Agent 协作框架设计

> **类型**：顶层设计（top-level spec）
> **日期**：2026-05-08
> **上游**：Phase 4a（测试修复）、Phase 4b（框架升级）

---

## 1. 目标

引入 Multi-Agent 协作能力，实现**职责分离**：
- **Orchestrator**：意图识别、任务分发、结果汇总
- **Teaching Agent**：负责诊断、讲解、复述检测、追问
- **Eval Agent**：负责理解程度评估、掌握度打分、反馈生成
- **Retrieval Agent**：负责知识检索、证据整理
- **System Eval Agent**：负责评估 Orchestrator 和 Teaching Agent 的效果

**协作模式**：条件分支 — Orchestrator 根据意图选择调用哪些 Agent

**数据传递**：混合模式 — 共享状态存持久数据，消息传递存 Agent 协作数据

**Orchestrator 智能**：混合路由 — 规则处理常见模式，LLM 处理边界情况

**系统评估**：异步自动 + 手动触发 — 会话结束后后台评估，支持重新评估

---

## 2. 整体架构

### 2.1 核心协作架构

```
┌─────────────────────────────────────────────────────────────┐
│                      Orchestrator                            │
│                                                              │
│  职责：                                                      │
│  1. 意图识别（规则 + LLM 混合）                              │
│  2. 构建任务队列                                             │
│  3. 分发到对应 Agent                                         │
│  4. 汇总结果生成最终回复                                     │
│                                                              │
│  输入：user_input, topic, history                           │
│  输出：task_queue, final_reply                              │
└─────────────────────────────────────────────────────────────┘
         │                    │                    │
         ▼                    ▼                    ▼
┌─────────────┐      ┌─────────────┐      ┌─────────────┐
│ Retrieval   │      │  Teaching   │      │    Eval     │
│   Agent     │      │   Agent     │      │   Agent     │
├─────────────┤      ├─────────────┤      ├─────────────┤
│ 职责：      │      │ 职责：      │      │ 职责：      │
│ 知识检索    │      │ 诊断+讲解   │      │ 理解评估    │
│ 证据整理    │      │ 复述检测    │      │ 掌握度打分  │
│             │      │ 追问生成    │      │ 反馈生成    │
├─────────────┤      ├─────────────┤      ├─────────────┤
│ 复用节点：  │      │ 复用节点：  │      │ 新建：      │
│ retrieval_  │      │ diagnose    │      │ eval_node   │
│ planner     │      │ explain     │      │             │
│ knowledge_  │      │ restate_    │      │ 输出：      │
│ retrieval   │      │ check       │      │ mastery_    │
│             │      │ followup    │      │ score       │
├─────────────┤      ├─────────────┤      │ eval_       │
│ 输出：      │      │ 输出：      │      │ feedback    │
│ citations   │      │ diagnosis   │      └─────────────┘
│ rag_context │      │ explanation │
│             │      │ followup_q  │
└─────────────┘      └─────────────┘
```

### 2.2 System Eval 架构

```
┌─────────────────────────────────────────────────────────────┐
│                   System Eval Agent                          │
│                   (异步评估，不阻塞主流程)                    │
│                                                              │
│  触发时机：会话结束后自动触发 / API 手动触发                  │
│  评估对象：Orchestrator + Teaching Agent                    │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
         ┌────────────────────┴────────────────────┐
         │                                         │
         ▼                                         ▼
┌─────────────────────┐              ┌─────────────────────┐
│  Teaching Eval      │              │  Orchestrator Eval   │
│  Subagent           │──── 依赖 ───→│  Subagent            │
├─────────────────────┤              ├─────────────────────┤
│ 输入：              │              │ 输入：              │
│ - teaching_output   │              │ - teaching_eval_    │
│ - user_input        │              │   result            │
│ - topic             │              │ - task_queue        │
│                     │              │ - intent_result     │
├─────────────────────┤              ├─────────────────────┤
│ 评估指标：          │              │ 评估指标：          │
│ - 讲解清晰度        │              │ - 意图识别准确率    │
│ - 知识覆盖率        │              │ - 任务队列合理性    │
│ - 交互有效性        │              │ - 路由响应时间      │
├─────────────────────┤              ├─────────────────────┤
│ 输出：              │              │ 输出：              │
│ - teaching_score    │              │ - orchestrator_     │
│ - clarity_score     │              │   score             │
│ - coverage_score    │              │ - intent_accuracy   │
│ - effectiveness_    │              │ - routing_score     │
│   score             │              │ - improvement_      │
│ - improvement_      │              │   suggestions       │
│   suggestions       │              │                     │
└─────────────────────┘              └─────────────────────┘
         │                                         │
         └────────────────────┬────────────────────┘
                              ▼
                    ┌─────────────────────┐
                    │  Eval Result Store  │
                    │  (SQLite / Redis)   │
                    ├─────────────────────┤
                    │ - session_id        │
                    │ - teaching_eval     │
                    │ - orchestrator_eval │
                    │ - created_at        │
                    └─────────────────────┘
```

**评估流程**：
1. 会话结束 → 异步触发 System Eval
2. Teaching Eval Subagent 先运行，评估教学效果
3. Orchestrator Eval Subagent 后运行，结合教学评估结果判断路由是否正确
4. 评估结果存入数据库，供可视化展示

---

## 3. 文件结构

```
app/agent/
├── graph_v2.py              # 现有单 Agent（保留不动）
├── multi_agent/             # 新建
│   ├── __init__.py
│   ├── state.py             # MultiAgentState + Agent 输入输出类型
│   ├── orchestrator.py      # Orchestrator 节点 + Aggregator
│   ├── teaching_agent.py    # Teaching Agent
│   ├── eval_agent.py        # Eval Agent
│   ├── retrieval_agent.py   # Retrieval Agent
│   ├── graph.py             # Multi-Agent 图构建
│   └── routers.py           # Agent 路由函数
├── system_eval/             # 新建：系统评估模块
│   ├── __init__.py
│   ├── teaching_eval.py     # Teaching Eval Subagent
│   ├── orchestrator_eval.py # Orchestrator Eval Subagent
│   ├── eval_store.py        # 评估结果存储
│   └── eval_graph.py        # 评估图构建
└── nodes/                   # 现有节点（被 Agent 调用）

app/api/
├── chat.py                  # 现有 /chat（保留）
├── chat_multi.py            # 新建 /chat/multi
└── eval.py                  # 新建 /eval API

app/services/
└── eval_queue.py            # 新建：异步评估队列

tests/multi_agent/
├── conftest.py
├── unit/
│   ├── test_orchestrator.py
│   ├── test_teaching_agent.py
│   ├── test_eval_agent.py
│   ├── test_teaching_eval.py
│   └── test_orchestrator_eval.py
└── integration/
    ├── test_multi_agent_flow.py
    └── test_system_eval_flow.py
```

---

## 4. 状态设计

### 4.1 共享状态（MultiAgentState）

会话级持久数据，所有 Agent 可读：

```python
class MultiAgentState(TypedDict, total=False):
    # 会话标识
    session_id: str
    user_id: int | None
    topic: str | None
    user_input: str
    
    # 会话历史
    history: list[str]
    branch_trace: list[dict]
    
    # Agent 协作控制
    current_agent: str              # 当前活跃 Agent
    task_queue: list[dict]          # 待执行任务队列
    completed_tasks: list[dict]     # 已完成任务
    
    # 最终输出
    final_reply: str
```

### 4.2 Agent 消息类型

Agent 间显式传递的数据：

```python
class RetrievalOutput(TypedDict, total=False):
    """Retrieval Agent 输出"""
    citations: list[dict]
    rag_context: str
    rag_found: bool
    rag_confidence_level: str


class TeachingOutput(TypedDict, total=False):
    """Teaching Agent 输出"""
    diagnosis: str
    explanation: str
    restatement_eval: str
    followup_question: str
    reply: str


class EvalOutput(TypedDict, total=False):
    """Eval Agent 输出"""
    mastery_score: float            # 0-100
    mastery_level: str              # low/medium/high
    eval_feedback: str              # 评估反馈
    error_labels: list[str]         # 错误标签
```

---

## 5. Orchestrator 设计

### 5.1 意图识别（混合路由）

```python
def orchestrator_node(state: MultiAgentState) -> dict:
    """分析意图，构建任务队列。"""
    user_input = state.get("user_input", "")
    topic = state.get("topic")
    
    # 规则路由（常见模式）
    if "评估" in user_input or "理解程度" in user_input:
        return {
            "current_agent": "eval",
            "task_queue": [{"type": "evaluate", "topic": topic}],
        }
    
    if "讲解" in user_input or "学" in user_input:
        return {
            "current_agent": "retrieval",
            "task_queue": [
                {"type": "retrieve", "topic": topic},
                {"type": "teach", "topic": topic},
                {"type": "evaluate", "topic": topic},
            ],
        }
    
    if "问答" in user_input or "直接回答" in user_input:
        return {
            "current_agent": "retrieval",
            "task_queue": [{"type": "retrieve", "topic": topic}],
        }
    
    # LLM 路由（边界情况）
    intent_result = llm_service.route_intent(user_input)
    intent = parse_intent(intent_result)
    
    return build_task_queue(intent, topic)
```

### 5.2 Aggregator

```python
def aggregator_node(state: MultiAgentState) -> dict:
    """汇总各 Agent 输出，生成最终回复。"""
    teaching_output = state.get("teaching_output", {})
    eval_output = state.get("eval_output", {})
    retrieval_output = state.get("retrieval_output", {})
    
    # 构建最终回复
    parts = []
    
    if retrieval_output.get("rag_context"):
        parts.append(retrieval_output["rag_context"])
    
    if teaching_output.get("explanation"):
        parts.append(teaching_output["explanation"])
    
    if eval_output.get("eval_feedback"):
        parts.append(f"\n--- 评估反馈 ---\n{eval_output['eval_feedback']}")
    
    return {
        "final_reply": "\n\n".join(parts),
        "mastery_score": eval_output.get("mastery_score"),
        "branch_trace": [{"phase": "aggregator", "agents_used": ["teaching", "eval"]}],
    }
```

---

## 6. Agent 实现

### 6.1 Teaching Agent

复用现有节点函数：

```python
def teaching_agent_node(state: MultiAgentState) -> dict:
    """Teaching Agent：诊断 + 讲解 + 复述检测 + 追问。"""
    from app.agent.nodes.teach import diagnose_node, explain_node, restate_check_node, followup_node
    
    # 获取检索结果（如果有）
    rag_context = state.get("retrieval_output", {}).get("rag_context", "")
    
    # 构建节点输入
    node_input = {
        **state,
        "topic_context": rag_context,
    }
    
    # 执行诊断
    diag_result = diagnose_node(node_input)
    # 执行讲解
    explain_result = explain_node(diag_result)
    # 执行复述检测
    restate_result = restate_check_node(explain_result)
    # 生成追问
    followup_result = followup_node(restate_result)
    
    return {
        "teaching_output": {
            "diagnosis": diag_result.get("diagnosis"),
            "explanation": explain_result.get("explanation"),
            "restatement_eval": restate_result.get("restatement_eval"),
            "followup_question": followup_result.get("followup_question"),
            "reply": followup_result.get("reply"),
        },
        "current_agent": "eval",  # 下一步进入评估
    }
```

### 6.2 Eval Agent

新建评估逻辑：

```python
def eval_agent_node(state: MultiAgentState) -> dict:
    """Eval Agent：评估用户理解程度。"""
    topic = state.get("topic", "未知主题")
    teaching_output = state.get("teaching_output", {})
    user_input = state.get("user_input", "")
    
    # 调用 LLM 进行评估
    system_prompt = """你是一个学习评估专家，负责评估用户对知识的理解程度。
请返回 JSON 格式：
{
  "mastery_score": 0-100,
  "mastery_level": "low/medium/high",
  "eval_feedback": "评估反馈",
  "error_labels": ["错误标签1", "错误标签2"]
}"""
    
    user_prompt = f"""主题：{topic}
讲解内容：{teaching_output.get("explanation", "")}
用户输入：{user_input}

请评估用户的理解程度。"""
    
    result = llm_service.invoke(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
    )
    
    # 解析结果
    eval_data = parse_eval_result(result)
    
    return {
        "eval_output": eval_data,
        "mastery_score": eval_data.get("mastery_score"),
        "current_agent": "aggregator",
    }
```

### 6.3 Retrieval Agent

复用现有 RAG 节点：

```python
def retrieval_agent_node(state: MultiAgentState) -> dict:
    """Retrieval Agent：知识检索。"""
    from app.agent.nodes.orchestration import retrieval_planner_node, knowledge_retrieval_node
    
    # 执行检索规划
    planner_result = retrieval_planner_node(state)
    # 执行知识检索
    retrieval_result = knowledge_retrieval_node(planner_result)
    
    return {
        "retrieval_output": {
            "citations": retrieval_result.get("citations", []),
            "rag_context": retrieval_result.get("rag_context", ""),
            "rag_found": retrieval_result.get("rag_found", False),
            "rag_confidence_level": retrieval_result.get("rag_confidence_level", ""),
        },
        "current_agent": get_next_agent(state),
    }
```

---

## 7. 路由设计

```python
def route_by_agent(state: MultiAgentState) -> str:
    """根据 current_agent 路由到对应 Agent。"""
    current_agent = state.get("current_agent", "orchestrator")
    
    agent_map = {
        "orchestrator": "orchestrator",
        "retrieval": "retrieval_agent",
        "teaching": "teaching_agent",
        "eval": "eval_agent",
        "aggregator": "aggregator",
    }
    
    return agent_map.get(current_agent, "orchestrator")
```

---

## 8. 图构建

```python
def build_multi_agent_graph():
    """构建 Multi-Agent 协作图。"""
    graph = StateGraph(MultiAgentState)
    
    # 添加节点
    graph.add_node("orchestrator", orchestrator_node)
    graph.add_node("retrieval_agent", retrieval_agent_node)
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
            "retrieval_agent": "retrieval_agent",
            "teaching_agent": "teaching_agent",
            "eval_agent": "eval_agent",
        }
    )
    
    graph.add_conditional_edges(
        "retrieval_agent",
        route_by_agent,
        {
            "teaching_agent": "teaching_agent",
            "aggregator": "aggregator",
        }
    )
    
    graph.add_conditional_edges(
        "teaching_agent",
        route_by_agent,
        {
            "eval_agent": "eval_agent",
        }
    )
    
    graph.add_edge("eval_agent", "aggregator")
    graph.add_edge("aggregator", END)
    
    return graph.compile(checkpointer=MemorySaver())
```

---

## 9. API 设计

```python
# app/api/chat_multi.py

class MultiChatRequest(BaseModel):
    session_id: str
    user_id: int | None = None
    topic: str | None = None
    user_input: str


class MultiChatResponse(BaseModel):
    session_id: str
    final_reply: str
    teaching_output: TeachingOutput | None = None
    eval_output: EvalOutput | None = None
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
        "history": [],
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

---

## 10. 测试策略

### 10.1 单元测试

- `test_orchestrator.py`：测试意图识别、任务队列构建
- `test_teaching_agent.py`：测试教学流程输出
- `test_eval_agent.py`：测试评估输出格式

### 10.2 集成测试

```python
def test_multi_agent_teach_and_eval_flow(monkeypatch):
    """测试教学+评估协作流程。"""
    monkeypatch.setattr("app.services.llm.llm_service.invoke", fake_invoke)
    
    resp = client.post("/chat/multi", json={
        "session_id": "test-1",
        "topic": "二分查找",
        "user_input": "我想学二分查找",
    })
    
    assert resp.status_code == 200
    body = resp.json()
    assert body["final_reply"] is not None
    assert body["mastery_score"] is not None
```

---

## 11. 风险与应对

| 风险 | 影响 | 应对 |
|------|------|------|
| 节点函数接口不兼容 | Agent 调用失败 | 封装适配层 |
| LLM 路由误判 | 错误的 Agent 流程 | 规则兜底 + 日志监控 |
| 状态字段冲突 | 数据覆盖 | 使用命名空间隔离 |
| 循环调用 | 无限循环 | 设置最大步数限制 |

---

## 12. 验收标准

| 指标 | 目标 |
|------|------|
| 功能 | `/chat/multi` API 可用 |
| 测试 | 单元测试 + 集成测试全部通过 |
| 性能 | 单次请求 < 30s |
| 文档 | README 更新 Multi-Agent 说明 |

---

## 13. 后续演进

| 阶段 | 内容 |
|------|------|
| Phase 4c.1（当前） | 基础框架 + 条件分支协作 |
| Phase 4c.2 | 并行协作（Retrieval 和 Teaching 并行） |
| Phase 4c.3 | 动态编排（Agent 间互相调用） |

---

## 14. System Eval Agent 设计

### 14.1 设计目标

**评估范围**：只针对 Orchestrator 和 Teaching Agent 进行评估

**评估方式**：
- 两个独立的 Eval Subagent
- 共享基础资源（LLM、数据库）
- 互不干扰上下文

**依赖关系**：串联依赖
```
会话完成 → Teaching Eval → Orchestrator Eval → 存储
```

### 14.2 评估时机

| 时机 | 说明 | 配置 |
|------|------|------|
| **异步自动** | 会话结束后后台自动运行 | `MULTI_AGENT_EVAL_ENABLED=true` |
| **手动触发** | 调用 `/eval/{session_id}` API | 支持重新评估 |

**异步评估流程**：

```python
# 会话结束时触发
async def trigger_eval(session_id: str, session_data: dict):
    """会话结束后异步触发评估。"""
    if not settings.MULTI_AGENT_EVAL_ENABLED:
        return
    
    # 写入队列，后台处理
    await eval_queue.enqueue({
        "session_id": session_id,
        "session_data": session_data,
        "created_at": datetime.now().isoformat(),
    })
```

### 14.3 Teaching Eval Subagent

**职责**：评估教学效果

**输入**：
```python
class TeachingEvalInput(TypedDict):
    session_id: str
    topic: str
    user_input: str
    teaching_output: TeachingOutput
    final_mastery_score: float
```

**评估指标**：

| 指标 | 说明 | 计算方式 |
|------|------|---------|
| **讲解清晰度** | 用户是否理解讲解 | LLM 评估讲解质量（0-100）|
| **知识覆盖率** | 是否覆盖主题核心知识点 | 对比知识图谱/关键词提取 |
| **交互有效性** | 追问是否促进学习 | 会话轮次 + 理解提升幅度 |

**输出**：
```python
class TeachingEvalOutput(TypedDict):
    session_id: str
    teaching_score: float          # 综合评分 0-100
    clarity_score: float           # 讲解清晰度
    coverage_score: float          # 知识覆盖率
    effectiveness_score: float     # 交互有效性
    improvement_suggestions: list[str]  # 改进建议
```

**实现**：
```python
def teaching_eval_node(input: TeachingEvalInput) -> TeachingEvalOutput:
    """评估教学效果。"""
    topic = input["topic"]
    teaching_output = input["teaching_output"]
    mastery_score = input["final_mastery_score"]
    
    # 1. 讲解清晰度评估
    clarity_prompt = f"""评估以下讲解的清晰度（0-100分）：
主题：{topic}
讲解：{teaching_output.get("explanation", "")}

评估标准：
- 逻辑清晰度
- 语言通俗性
- 例子恰当性

返回 JSON：{{"clarity_score": 0-100, "reason": "..."}}"""
    
    clarity_result = llm_service.invoke(
        system_prompt="你是一个教学评估专家",
        user_prompt=clarity_prompt,
    )
    clarity_score = parse_score(clarity_result)
    
    # 2. 知识覆盖率评估
    coverage_prompt = f"""评估讲解对主题核心知识点的覆盖程度：
主题：{topic}
讲解：{teaching_output.get("explanation", "")}

返回 JSON：{{"coverage_score": 0-100, "covered_points": [...], "missing_points": [...]}}"""
    
    coverage_result = llm_service.invoke(
        system_prompt="你是一个知识评估专家",
        user_prompt=coverage_prompt,
    )
    coverage_score = parse_score(coverage_result)
    
    # 3. 交互有效性评估（基于掌握度提升）
    effectiveness_score = min(100, mastery_score * 1.1)  # 简化计算
    
    # 4. 综合评分
    teaching_score = (clarity_score * 0.4 + coverage_score * 0.3 + effectiveness_score * 0.3)
    
    return {
        "session_id": input["session_id"],
        "teaching_score": teaching_score,
        "clarity_score": clarity_score,
        "coverage_score": coverage_score,
        "effectiveness_score": effectiveness_score,
        "improvement_suggestions": generate_suggestions(clarity_result, coverage_result),
    }
```

### 14.4 Orchestrator Eval Subagent

**职责**：评估路由决策质量

**输入**：
```python
class OrchestratorEvalInput(TypedDict):
    session_id: str
    user_input: str
    detected_intent: str
    task_queue: list[dict]
    teaching_eval_result: TeachingEvalOutput  # 依赖上游评估结果
    actual_flow: list[str]                    # 实际执行的 Agent 序列
```

**评估指标**：

| 指标 | 说明 | 计算方式 |
|------|------|---------|
| **意图识别准确率** | 用户意图是否被正确识别 | 规则验证 + LLM 二次判断 |
| **任务队列合理性** | 分配的 Agent 序列是否合理 | 对比最佳实践 + 教学评估结果 |
| **路由响应时间** | Orchestrator 决策耗时 | 直接计时 |

**输出**：
```python
class OrchestratorEvalOutput(TypedDict):
    session_id: str
    orchestrator_score: float      # 综合评分 0-100
    intent_accuracy: float         # 意图识别准确率
    routing_score: float           # 路由合理性
    response_time_ms: float        # 响应时间
    improvement_suggestions: list[str]  # 改进建议
```

**实现**：
```python
def orchestrator_eval_node(input: OrchestratorEvalInput) -> OrchestratorEvalOutput:
    """评估 Orchestrator 路由决策。"""
    user_input = input["user_input"]
    detected_intent = input["detected_intent"]
    teaching_eval = input["teaching_eval_result"]
    actual_flow = input["actual_flow"]
    
    # 1. 意图识别准确性（LLM 二次判断）
    intent_check_prompt = f"""判断以下意图识别是否正确：
用户输入：{user_input}
识别意图：{detected_intent}

返回 JSON：{{"is_correct": true/false, "should_be": "...", "reason": "..."}}"""
    
    intent_result = llm_service.invoke(
        system_prompt="你是一个意图识别评估专家",
        user_prompt=intent_check_prompt,
    )
    intent_accuracy = 100 if parse_bool(intent_result, "is_correct") else 50
    
    # 2. 路由合理性（结合教学评估结果）
    # 如果教学效果好，说明路由合理；反之需要分析
    teaching_score = teaching_eval.get("teaching_score", 50)
    
    if teaching_score >= 70:
        routing_score = 80  # 教学好，路由大概率合理
    elif teaching_score >= 50:
        routing_score = 60  # 教学一般，路由可能有问题
    else:
        # 教学效果差，分析是否是路由问题
        routing_score = analyze_routing_issue(input)
    
    # 3. 综合评分
    orchestrator_score = (intent_accuracy * 0.5 + routing_score * 0.5)
    
    return {
        "session_id": input["session_id"],
        "orchestrator_score": orchestrator_score,
        "intent_accuracy": intent_accuracy,
        "routing_score": routing_score,
        "response_time_ms": input.get("response_time_ms", 0),
        "improvement_suggestions": generate_orchestrator_suggestions(intent_result, routing_score),
    }
```

### 14.5 评估结果存储

```python
# app/agent/system_eval/eval_store.py

class EvalResultStore:
    """评估结果存储。"""
    
    def save(self, session_id: str, teaching_eval: dict, orchestrator_eval: dict):
        """保存评估结果。"""
        conn = sqlite3.connect(settings.EVAL_DB_PATH)
        conn.execute("""
            INSERT OR REPLACE INTO eval_results 
            (session_id, teaching_eval, orchestrator_eval, created_at)
            VALUES (?, ?, ?, ?)
        """, (
            session_id,
            json.dumps(teaching_eval),
            json.dumps(orchestrator_eval),
            datetime.now().isoformat(),
        ))
        conn.commit()
    
    def get(self, session_id: str) -> dict | None:
        """获取评估结果。"""
        conn = sqlite3.connect(settings.EVAL_DB_PATH)
        cursor = conn.execute(
            "SELECT * FROM eval_results WHERE session_id = ?",
            (session_id,),
        )
        row = cursor.fetchone()
        if row:
            return {
                "session_id": row[0],
                "teaching_eval": json.loads(row[1]),
                "orchestrator_eval": json.loads(row[2]),
                "created_at": row[3],
            }
        return None
```

### 14.6 评估 API

```python
# app/api/eval.py

@router.get("/eval/{session_id}")
async def get_eval(session_id: str):
    """获取会话评估结果。"""
    store = EvalResultStore()
    result = store.get(session_id)
    if not result:
        raise HTTPException(status_code=404, detail="评估结果不存在")
    return result


@router.post("/eval/{session_id}/rerun")
async def rerun_eval(session_id: str):
    """重新评估指定会话。"""
    # 获取会话数据
    session_data = get_session_data(session_id)
    if not session_data:
        raise HTTPException(status_code=404, detail="会话不存在")
    
    # 触发评估
    result = await run_system_eval(session_id, session_data)
    
    return {
        "session_id": session_id,
        "teaching_eval": result["teaching_eval"],
        "orchestrator_eval": result["orchestrator_eval"],
    }


@router.get("/eval/stats")
async def get_eval_stats():
    """获取评估统计（用于可视化）。"""
    conn = sqlite3.connect(settings.EVAL_DB_PATH)
    
    # 平均评分
    cursor = conn.execute("""
        SELECT 
            AVG(json_extract(teaching_eval, '$.teaching_score')),
            AVG(json_extract(orchestrator_eval, '$.orchestrator_score'))
        FROM eval_results
    """)
    row = cursor.fetchone()
    
    return {
        "avg_teaching_score": row[0] or 0,
        "avg_orchestrator_score": row[1] or 0,
        "total_evaluations": conn.execute("SELECT COUNT(*) FROM eval_results").fetchone()[0],
    }
```

### 14.7 配置项

```python
# app/core/config.py

class Settings(BaseSettings):
    # Multi-Agent 评估配置
    MULTI_AGENT_EVAL_ENABLED: bool = True
    EVAL_DB_PATH: str = "data/eval_results.db"
    EVAL_QUEUE_ENABLED: bool = True
```

---

## 15. 可视化支持

评估数据结构设计支持后续可视化：

```
评估结果数据 → API → 可视化大屏
```

**可视化指标**：
- Teaching Score 趋势图
- Orchestrator Score 分布
- 意图识别准确率统计
- 改进建议聚合展示
