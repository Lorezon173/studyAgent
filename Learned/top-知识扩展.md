# 知识扩展合集

> 详细知识补充，尤其是用户主动询问的主题
> 简要概括见 [QA.md](QA.md)

---

## Pydantic vs TypedDict 选型全景

> 来源：阶段 1.2 / 教学补充 + 用户主动询问

### 一句话

数据进出系统边界用 Pydantic（强校验）；系统内部传递用 TypedDict（轻量、合并友好）。

### 详细内容

#### Pydantic 三个核心能力

**能力 1：自动数据校验**

```python
from pydantic import BaseModel, Field

class ChatRequest(BaseModel):
    session_id: str
    user_input: str = Field(min_length=1)
    user_id: int | None = None

ChatRequest(session_id="abc", user_input="")
# ❌ ValidationError: user_input 不能为空

ChatRequest(session_id="abc", user_input="hi", user_id="123")
# ✅ user_id 自动从 "123" 转成 int 123
```

**能力 2：JSON 序列化/反序列化**

```python
req = ChatRequest(session_id="abc", user_input="hi")
req.model_dump_json()  # → '{"session_id":"abc","user_input":"hi","user_id":null}'
ChatRequest.model_validate_json('{"session_id":"abc","user_input":"hi"}')
```

**能力 3：与 FastAPI 深度整合**

```python
@app.post("/chat")
def chat(req: ChatRequest):  # FastAPI 自动调用 Pydantic 校验请求体
    ...
```

请求体不合法时自动返回 422 错误。

#### 选型对比表

| 工具 | 运行时校验 | 序列化 | 合并友好 | 性能 | 适用场景 |
|---|---|---|---|---|---|
| `BaseModel` | ✅ 强 | ✅ 内置 | ❌ 嵌套时复杂 | 中 | API 边界、配置、外部数据 |
| `TypedDict` | ❌ | dict 即可 | ✅ 天然 | 高 | LangGraph state、内部传递 |
| `@dataclass` | ❌ | 需手写 | ⚠️ 需 `replace()` | 高 | 不可变值对象、领域模型 |

#### 为什么 LangGraph 需要 TypedDict

Pydantic `BaseModel` 做 LangGraph state 时：
- 返回 `{"nested": {"a": 1}}` 会**覆盖**整个 `nested` 字段（不可变语义）
- TypedDict 返回的部分 dict 会**字段级 merge** 到全局 state

这是架构适配问题，不仅仅是性能。

### 与本项目的关联

| 文件 | 用途 | 选型 |
|---|---|---|
| [app/models/schemas.py](../app/models/schemas.py) | API 请求/响应 | Pydantic BaseModel |
| [app/core/config.py](../app/core/config.py) | 配置加载 | Pydantic BaseSettings |
| [app/agent/state.py](../app/agent/state.py) | Agent 状态 | TypedDict + total=False |
| [app/rag/schemas.py](../app/rag/schemas.py) | RAG 数据模型 | Pydantic BaseModel |

**铁律：数据进出系统边界用 Pydantic；系统内部传递用 TypedDict 或 dataclass。**

---

## Temporal 分布式工作流引擎深入

> 来源：阶段 1.2 / **用户主动询问**

### 一句话

Temporal 是分布式工作流编排引擎——你用普通 Python 函数写业务逻辑，它帮你搞定崩溃恢复、超时重试、状态持久化。

### 为什么说它"工业级"

| 能力 | 说明 | 对比 LangGraph |
|---|---|---|
| 崩溃不丢进度 | Workflow 状态持久化到数据库，进程挂了重启后自动从断点继续 | LangGraph checkpointer 粒度是"整个图执行"，Temporal 是"每一行代码" |
| Activity 自动重试 | 单个 Activity 失败后自动重试，可配退避策略 | LangGraph 需要自己写 retry_policy.py |
| 长等待不占资源 | Workflow 等待用户输入时（可能等一周），不占内存/CPU，Server 只存事件日志 | LangGraph checkpoint 需要手动 re-invoke，没有原生"挂起等信号"语义 |
| 分布式天然 | Workflow 和 Activity 可跑在不同机器上，由 Temporal Server 协调 | LangGraph 是单进程 |
| 可观测性 | 内置 Web UI 查看每个 Workflow 的执行历史、重试次数、耗时 | LangGraph 需要 LangSmith 或自己接 |

### 架构

```
┌─────────────────────────────────────────────┐
│                  你的代码                      │
│                                              │
│  ┌──────────────┐    ┌──────────────────┐   │
│  │  Workflow     │    │  Activity        │   │
│  │  (编排逻辑)    │    │  (具体干活)       │   │
│  │  纯函数，无IO  │    │  可以调API/DB/LM  │   │
│  └──────┬───────┘    └────────┬─────────┘   │
│         │                     │              │
└─────────┼─────────────────────┼──────────────┘
          │ gRPC                │ gRPC
          ▼                     ▼
┌─────────────────────────────────────────────┐
│           Temporal Server (独立服务)          │
│                                              │
│  ┌──────────┐ ┌──────────┐ ┌──────────────┐ │
│  │ History   │ │ Matching │ │ Task Queue   │ │
│  │ (事件日志) │ │ (分发任务)│ │ (等待队列)    │ │
│  └──────────┘ └──────────┘ └──────────────┘ │
│                    │                         │
│          ┌─────────┴─────────┐               │
│          │   数据库 (Cassandra│               │
│          │   / PostgreSQL)   │               │
│          └───────────────────┘               │
└─────────────────────────────────────────────┘
```

### 四个核心概念

| 概念 | 类比 | 说明 |
|---|---|---|
| **Workflow** | 手术总方案 | 纯函数，描述"先做A再做B，如果C失败就D"。**不能有 IO、不能调随机数**——因为要能重放 |
| **Activity** | 手术具体动作 | 实际干活的函数（调 LLM、写 DB、发通知）。可以失败，Temporal 会自动重试 |
| **Signal** | 外部打断 | 从外部向正在运行的 Workflow 发消息（比如"用户回复了"） |
| **Query** | 查看病历 | 从外部读取 Workflow 当前状态，不影响执行 |

### 如果用 Temporal 重写费曼教学链路

```python
from datetime import timedelta
from temporalio import workflow, activity

@activity.defn
async def diagnose(user_input: str) -> str:
    """调 LLM 做诊断"""
    return await call_llm(f"诊断用户认知: {user_input}")

@activity.defn
async def explain(diagnosis: str) -> str:
    """调 LLM 做讲解"""
    return await call_llm(f"根据诊断讲解: {diagnosis}")

@workflow.defn
class FeynmanTeachingWorkflow:
    def __init__(self):
        self.user_restate = ""
        self.restate_received = False

    @workflow.run
    async def run(self, user_input: str) -> str:
        # 第1步：诊断
        diagnosis = await workflow.execute_activity(
            diagnose, user_input,
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )

        # 第2步：讲解
        explanation = await workflow.execute_activity(
            explain, diagnosis,
            start_to_close_timeout=timedelta(seconds=60),
        )

        # 第3步：等用户复述 —— 可以等一周！不占任何资源！
        await workflow.wait_condition(
            lambda: self.restate_received,
            timeout=timedelta(days=30),
        )

        # 第4步：评估复述并路由
        if "混淆" in self.user_restate:
            return await workflow.execute_activity(followup, self.user_restate)
        else:
            return await workflow.execute_activity(summarize, self.user_restate)

    @workflow.signal
    async def submit_restate(self, text: str):
        """外部 Signal：用户提交复述"""
        self.user_restate = text
        self.restate_received = True
```

**关键区别**：

```python
# LangGraph：需要手动 re-invoke
result = graph.invoke({"user_input": "复述内容"}, config={"configurable": {"thread_id": session_id}})

# Temporal：Workflow 一直"活着"（但不占资源），Signal 直接推给它
await handle.signal(FeynmanTeachingWorkflow.submit_restate, "我的复述...")
```

### 为什么本项目当前不选 Temporal

| 原因 | 说明 |
|---|---|
| 太重 | 需要 Temporal Server + 数据库，部署复杂度从 `pip install` 跳到运维集群 |
| 单进程够了 | 当前教学链路是单次 HTTP 请求驱动 |
| LLM 流式输出 | Temporal Activity 返回值是一次性的，流式 token 需要额外 hack |
| 过早优化 | 当前阶段 checkpointer 够用 |

### 与本项目的关联

- 当前 LangGraph + SQLite checkpointer 满足会话级持久化
- 如果未来需要"跨周持续学习"（用户学一个月不中断），Temporal 值得引入
- README §9 提到「下一轮可能引入多 Agent 协作框架」，届时分布式编排需求会更明确

---

## ReAct vs LangGraph 流程可控性对比

> 来源：阶段 1.2 / 教学补充

### 一句话

ReAct 让 LLM 自己决定下一步（灵活但不可控）；LangGraph 用声明式图拓扑固定流程（强约束可预测）。

### 详细内容

#### ReAct 模式

```
LLM 自己决定下一步：
  Thought: 用户在问哲学问题，我应该先检索知识库
  Action: search_local_textbook("康德")
  Observation: ...
  Thought: 信息够了，直接回答
  Action: answer(...)
```

| 优点 | 缺点 |
|---|---|
| 最灵活，LLM 自己选工具 | 不可预测、调试痛苦 |
| 代码极少 | 易陷死循环、token 消耗大 |
| 适合开放任务 | 难做 SLO（路径不固定） |

#### LangGraph 模式

```python
graph = StateGraph(LearningState)
graph.add_node("diagnose", diagnose_node)
graph.add_node("explain", explain_node)
graph.add_conditional_edges("restate_check", route_after_restate, {
    "followup": "followup",
    "explain": "explain",
})
```

| 优点 | 缺点 |
|---|---|
| 流程强约束，可预测 | 灵活性降低 |
| 可视化图拓扑 | 新增节点需要改图定义 |
| 内置 checkpoint、retry | 学习曲线比 ReAct 高 |

#### 核心矛盾

| 维度 | ReAct | LangGraph |
|---|---|---|
| 路径决定者 | LLM（运行时） | 开发者（编译时） |
| 流程保证 | ❌ 无法保证走完 5 步 | ✅ 图拓扑强制 |
| 适合场景 | 开放式问答、研究助手 | 有固定 SOP 的业务流程 |

本项目费曼 5 步是**强约束流程**：diagnose → explain → restate → followup → summary 顺序由图拓扑保证，ReAct 给不了这种保证。

### 与本项目的关联

- [graph_v2.py:104](../app/agent/graph_v2.py#L104) 的条件路由是编译时定义的，不是 LLM 运行时选择的
- 这正是项目选 LangGraph 而不是 ReAct 的核心原因

---

## Agent 编排替代方案全景（6 大类）

> 来源：阶段 1.2 / 教学补充

### 一句话

6 种 Agent 编排方案按流程可控性从弱到强排列：ReAct → LangChain Agent → 多 Agent 消息 → 函数路由 → 手写状态机 → Temporal。

### 总览

```
1. 手写状态机（用户提到的方案）
2. ReAct 单循环（LLM 自决策）
3. LangChain AgentExecutor
4. 多 Agent 消息传递（AutoGen / CrewAI）
5. 工作流引擎（Temporal / Airflow / Prefect）
6. 函数调用 + 路由器（最朴素）
```

### 方案 1：手写状态机

```python
state = {...}
while state["stage"] != "done":
    if state["stage"] == "diagnose":
        state = diagnose(state)
    elif state["stage"] == "explain":
        state = explain(state)
    ...
```

| 优点 | 缺点 |
|---|---|
| 零依赖、绝对可控 | 路由逻辑硬编码、难可视化 |
| 调试简单（直接打断点） | 无 retry / checkpoint，要自己写 |
| 性能最高 | 节点多时 if-else 爆炸 |

**vs LangGraph 劣势**：没有 checkpoint、没有可视化图、没有 retry 框架、新增节点要改主循环。

**适用场景**：节点 < 5 个、单进程、不需要恢复中断。

---

### 方案 2：ReAct 单循环（LLM 自决策）

```
LLM 自己决定下一步：
  Thought: 用户在问哲学问题，我应该先检索知识库
  Action: search_local_textbook("康德")
  Observation: ...
  Thought: 信息够了，直接回答
  Action: answer(...)
```

代表实现：原始 ReAct 论文、LangChain 旧版 Agent。

| 优点 | 缺点 |
|---|---|
| 最灵活，LLM 自己选工具 | 不可预测、调试痛苦 |
| 代码极少 | 易陷死循环、token 消耗大 |
| 适合开放任务 | 难做 SLO（路径不固定） |

**vs LangGraph 劣势**：路径不固定 → 没法保证教学流程一定走完 5 步。

**适用场景**：开放式问答、研究助手（不要求固定流程）。

**本项目不选的原因**：费曼 5 步是**强约束流程**，必须保证 diagnose → explain → restate → followup → summary 顺序，ReAct 给不了这种保证。

---

### 方案 3：LangChain AgentExecutor

```python
agent = create_openai_tools_agent(llm, tools, prompt)
executor = AgentExecutor(agent=agent, tools=tools)
executor.invoke({"input": "..."})
```

| 优点 | 缺点 |
|---|---|
| 工具调用封装好 | 流程不可控（仍是 LLM 决策） |
| 生态成熟 | 难做条件分支 |
| 与 LangChain 生态贯通 | 黑盒程度高 |

**vs LangGraph 劣势**：本质是 ReAct 的封装，多 Agent 协作 / 复杂条件路由能力弱——这正是 LangGraph 在 LangChain 生态里诞生的原因（官方说法：「补充 AgentExecutor 在长流程上的不足」）。

**适用场景**：单 Agent + 工具调用为主、流程简单。

---

### 方案 4：多 Agent 消息传递（AutoGen / CrewAI）

**AutoGen**（Microsoft）：
```
UserProxyAgent ↔ AssistantAgent ↔ CriticAgent
              （通过 send_message 互相对话）
```

**CrewAI**：
```python
crew = Crew(agents=[researcher, writer, reviewer], tasks=[...])
```
按角色（Role）分工，按任务（Task）流转。

| 优点 | 缺点 |
|---|---|
| 多 Agent 协作天然 | 单 Agent 任务过度设计 |
| 角色清晰 | 状态在 message 历史里，难持久化 |
| 适合"辩论"、"评审"场景 | 控制流不如 LangGraph 精细 |

**vs LangGraph 劣势**：本项目当前是单 Agent 内多节点，不是多 Agent；用 AutoGen/CrewAI 就要把"节点"硬包成"Agent"，过度设计。

**适用场景**：明确多角色（研究员+作家+审稿人）、辩论式协作。

**本项目不选的原因**：README §9 提到「下一轮可能引入多 Agent 协作框架」，那时候才轮到这一类。当前单 Agent 阶段用多 Agent 框架是杀鸡用牛刀。

---

### 方案 5：工作流引擎（Temporal / Airflow / Prefect）

```python
@workflow.defn
class TeachingWorkflow:
    @workflow.run
    async def run(self, user_input: str):
        diag = await workflow.execute_activity(diagnose, user_input)
        expl = await workflow.execute_activity(explain, diag)
        ...
```

| 优点 | 缺点 |
|---|---|
| **持久化最强**（崩溃重启自动恢复） | 重，独立服务（Temporal Server） |
| 长任务（小时/天）天然支持 | LLM 流式 token 集成困难 |
| 重试 / 超时 / 补偿机制工业级 | 学习曲线陡 |

**vs LangGraph 劣势**：太重，启动一个 Temporal 集群只为跑教学链路不值。

**适用场景**：跨小时的长任务、强一致性、金融级容错。

**潜在适用时机**：如果本项目要支持「教学计划跨周持续」（用户连续学一个月），这种引擎就值得了。

---

### 方案 6：函数调用 + 路由器（最朴素）

```python
def chat(state):
    intent = classify_intent(state["user_input"])
    handler = ROUTES[intent]  # {"teach": teach_handler, "qa": qa_handler}
    return handler(state)
```

| 优点 | 缺点 |
|---|---|
| 0 依赖 | 流程深时不可维护 |
| 极简 | 没有任何框架支持 |

**vs LangGraph 劣势**：节点 > 5 就乱。

**适用场景**：MVP 阶段、节点 ≤ 3。

---

### 对比矩阵（面试可直接背）

| 方案 | 流程可控性 | 状态管理 | 持久化 | 多 Agent | 复杂度 | 适合本项目？ |
|---|---|---|---|---|---|---|
| 手写状态机 | ★★★★★ | 自己写 | 自己写 | ❌ | 低 | ⚠️ MVP 可，规模化不行 |
| ReAct | ★ | LLM 黑盒 | ❌ | ❌ | 极低 | ❌ 流程约束达不到 |
| LangChain Agent | ★★ | message 列表 | 弱 | ❌ | 中 | ❌ 同上 |
| AutoGen/CrewAI | ★★★ | message 历史 | 弱 | ✅ | 中高 | ❌ 当前是单 Agent |
| Temporal | ★★★★★ | 引擎管理 | ✅ 工业级 | ⚠️ | 高 | ❌ 太重 |
| 函数路由 | ★★★ | 自己写 | ❌ | ❌ | 极低 | ❌ 节点太多 |
| **LangGraph** | **★★★★★** | **TypedDict** | **checkpointer** | **✅ 可扩** | **中** | **✅ 当前最优** |

### LangGraph 胜出的 6 个理由

1. **声明式流程图**：`add_conditional_edges` 把路由逻辑从代码里抽出来
2. **Checkpoint 内置**：`langgraph-checkpoint-sqlite` 直接给会话恢复
3. **节点级 retry policy**：[retry_policy.py](../app/agent/retry_policy.py)
4. **流式天然支持**：`graph.stream()` / `astream()` 输出节点级事件
5. **可视化**：`graph.get_graph().draw_mermaid()` 直接画流程图
6. **演进路径**：未来加多 Agent 也能扩，不用重写

### 与本项目的关联

- 本项目 17 个节点 + 条件路由 + 会话持久化的需求，正好落在 LangGraph 的最佳区间
- 如果节点 < 5 个，手写状态机更简单；如果需要跨周，Temporal 更强
