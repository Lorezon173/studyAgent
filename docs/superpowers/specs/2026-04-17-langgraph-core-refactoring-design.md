# LangGraph核心重构设计

**设计日期**: 2026-04-17
**设计目标**: 充分利用LangGraph的条件边、检查点、重试策略特性，重构Agent编排设计

---

## 目录

1. [设计目标](#一设计目标)
2. [整体架构](#二整体架构)
3. [条件边设计](#三条件边设计)
4. [检查点设计](#四检查点设计)
5. [重试策略设计](#五重试策略设计)
6. [文件结构](#六文件结构)
7. [迁移策略](#七迁移策略)

---

## 一、设计目标

### 1.1 核心目标

| 目标 | 描述 | 关键指标 |
|------|------|----------|
| 动态路由 | 使用条件边实现决策节点化 | 4种路由场景覆盖 |
| 状态持久化 | 使用检查点支持会话恢复 | 中断恢复率 > 95% |
| 容错能力 | 节点级重试策略 | 故障恢复率 > 90% |
| 用户历史 | 支持历史学习记录检查 | 个性化学习体验 |
| RAG优先 | 问答时优先使用知识库 | 减少幻觉，提高准确性 |

### 1.2 新增功能

1. **历史记录检查**: 用户提出主题时，检查SQLite中的学习历史，询问是否复习或继续
2. **RAG优先检索**: 问答时优先检索本地知识库，基于现有知识回答，减少幻觉

---

## 二、整体架构

### 2.1 新图结构

```
                        ┌─────────────────┐
                        │  intent_router  │
                        └────────┬────────┘
                                 │
       ┌─────────────────────────┼─────────────────────────┐
       │                         │                         │
       ▼                         ▼                         ▼
┌──────────────┐          ┌──────────────┐          ┌──────────────┐
│history_check │          │   rag_first  │          │    replan    │
└──────┬───────┘          └──────┬───────┘          └──────┬───────┘
       │                         │                         │
   ┌───┴───┐               ┌─────┴─────┐                   │
   │       │               │           │                   │
   ▼       ▼               ▼           ▼                   │
┌────┐ ┌────────┐     ┌────────┐ ┌────────┐               │
│diag│ │ask_rev │     │rag_ans │ │llm_ans │               │
└──┬─┘ └───┬────┘     └────┬───┘ └────┬───┘               │
   │       │               │         │                    │
   │   ┌───┴───┐           └────┬────┘                   │
   │   │       │                │                        │
   │   ▼       ▼               END                      END
   │ 复习    继续
   │         ↓
   │    diagnose → explain → restate_check → followup → summary
   │                    ↑              │
   │                    └──────────────┘ (循环，最多3次)
   │
   └──→ diagnose → ... (同上流程)
```

### 2.2 节点清单

| 节点名称 | 功能 | 重试策略 |
|----------|------|----------|
| `intent_router` | 意图识别入口 | LLM_RETRY |
| `history_check` | 用户历史学习记录检查 | DB_RETRY |
| `ask_review_or_continue` | 询问复习或继续学习 | 无 |
| `diagnose` | 诊断用户知识水平 | LLM_RETRY |
| `explain` | 费曼法讲解 | LLM_RETRY |
| `restate_check` | 复述检测 | LLM_RETRY |
| `followup` | 针对性追问 | LLM_RETRY |
| `summary` | 学习总结 | LLM_RETRY |
| `rag_first` | RAG优先检索 | RAG_RETRY |
| `rag_answer` | 基于RAG知识回答 | LLM_RETRY |
| `llm_answer` | 基于LLM回答 | LLM_RETRY |
| `replan` | 重规划 | LLM_RETRY |

---

## 三、条件边设计

### 3.1 路由函数定义

#### 3.1.1 意图入口路由

```python
def route_by_intent(state: LearningState) -> Literal["history_check", "rag_first", "replan", "summary"]:
    """根据意图路由到不同分支"""
    intent = state.get("intent", "teach_loop")

    route_map = {
        "qa_direct": "rag_first",     # 问答走RAG优先
        "replan": "replan",
        "review": "summary",
        "teach_loop": "history_check", # 教学走历史检查
    }

    return route_map.get(intent, "history_check")
```

#### 3.1.2 历史检查后路由

```python
def route_after_history_check(state: LearningState) -> Literal["ask_review_or_continue", "diagnose"]:
    """历史检查后路由"""
    if state.get("has_history", False):
        return "ask_review_or_continue"  # 有历史，询问用户
    else:
        return "diagnose"                 # 无历史，直接诊断
```

#### 3.1.3 用户选择后路由

```python
def route_after_choice(state: LearningState) -> Literal["diagnose", "explain"]:
    """用户选择后路由"""
    choice = state.get("user_choice", "continue")

    if choice == "review":
        return "diagnose"  # 复习模式，重新诊断
    else:
        return "explain"   # 继续学习，直接讲解新内容
```

#### 3.1.4 诊断后路由

```python
def route_after_diagnosis(state: LearningState) -> Literal["explain", "knowledge_retrieval", "summary"]:
    """诊断后路由"""
    diagnosis = state.get("diagnosis", "")

    # 已掌握，跳过讲解
    if any(k in diagnosis for k in ["已掌握", "熟悉", "理解充分"]):
        return "summary"

    # 需要外部知识
    if any(k in diagnosis for k in ["需要补充", "缺少资料", "建议参考"]):
        return "knowledge_retrieval"

    return "explain"
```

#### 3.1.5 复述后路由

```python
def route_after_restate(state: LearningState) -> Literal["followup", "explain", "summary"]:
    """复述评估后路由"""
    eval_text = state.get("restatement_eval", "")
    loop_count = state.get("explain_loop_count", 0)

    # 理解程度高，直接总结
    if any(k in eval_text for k in ["已理解", "准确", "完整", "正确"]):
        return "summary"

    # 有重大误解，重新讲解（最多3次）
    if any(k in eval_text for k in ["错误", "混淆", "误解", "不清楚"]):
        if loop_count < 3:
            state["explain_loop_count"] = loop_count + 1
            return "explain"

    return "followup"
```

#### 3.1.6 RAG检索后路由

```python
def route_after_rag(state: LearningState) -> Literal["rag_answer", "llm_answer"]:
    """RAG检索后路由"""
    if state.get("rag_found", False):
        return "rag_answer"  # 有知识库结果
    else:
        return "llm_answer"  # 无结果，用LLM回答
```

### 3.2 条件边配置

```python
# 在graph_v2.py中配置条件边
graph.add_conditional_edges("intent_router", route_by_intent, {
    "history_check": "history_check",
    "rag_first": "rag_first",
    "replan": "replan",
    "summary": "summary",
})

graph.add_conditional_edges("history_check", route_after_history_check, {
    "ask_review_or_continue": "ask_review_or_continue",
    "diagnose": "diagnose",
})

graph.add_conditional_edges("ask_review_or_continue", route_after_choice, {
    "diagnose": "diagnose",
    "explain": "explain",
})

graph.add_conditional_edges("diagnose", route_after_diagnosis, {
    "explain": "explain",
    "knowledge_retrieval": "knowledge_retrieval",
    "summary": "summary",
})

graph.add_conditional_edges("restate_check", route_after_restate, {
    "followup": "followup",
    "explain": "explain",
    "summary": "summary",
})

graph.add_conditional_edges("rag_first", route_after_rag, {
    "rag_answer": "rag_answer",
    "llm_answer": "llm_answer",
})
```

---

## 四、检查点设计

### 4.1 存储配置

```python
# app/agent/checkpointer.py

from langgraph.checkpoint.sqlite import SqliteSaver
from app.core.config import settings

def get_checkpointer():
    """获取SQLite检查点存储器"""
    return SqliteSaver.from_conn_string(settings.session_sqlite_path)
```

### 4.2 图编译配置

```python
def build_learning_graph_v2():
    """构建带检查点的图"""
    graph = StateGraph(LearningState)
    # ... 节点和边定义 ...

    checkpointer = get_checkpointer()
    return graph.compile(checkpointer=checkpointer)
```

### 4.3 使用场景

#### 4.3.1 正常会话

```python
def run_session(session_id: str, user_input: str):
    graph = build_learning_graph_v2()
    result = graph.invoke(
        {"user_input": user_input},
        config={"configurable": {"thread_id": session_id}}
    )
    return result
```

#### 4.3.2 恢复中断会话

```python
def resume_session(session_id: str):
    graph = build_learning_graph_v2()
    state = graph.get_state({"configurable": {"thread_id": session_id}})

    if state and state.values.get("waiting_for_choice"):
        # 用户之前在等待选择，继续等待
        return state.values

    # 继续执行
    result = graph.invoke(None, config={"configurable": {"thread_id": session_id}})
    return result
```

#### 4.3.3 回放执行过程

```python
def replay_session(session_id: str):
    graph = build_learning_graph_v2()
    history = list(graph.get_state_history(
        {"configurable": {"thread_id": session_id}}
    ))

    for idx, state in enumerate(history):
        print(f"Step {idx}: stage={state.values.get('stage')}")

    return history
```

### 4.4 状态恢复策略

| 中断阶段 | 恢复策略 |
|----------|----------|
| `ask_review_or_continue` | 恢复到等待选择状态 |
| `explain` | 检测已讲解，继续到 `restate_check` |
| `followup` | 提供选项：继续回答 或 跳到总结 |

---

## 五、重试策略设计

### 5.1 策略定义

```python
# app/agent/retry_policy.py

from langgraph.pregel import RetryPolicy

# LLM调用重试策略
LLM_RETRY = RetryPolicy(
    max_attempts=3,
    initial_interval=2.0,
    backoff_factor=2.0,
    jitter=True,
    retry_on=[ConnectionError, TimeoutError, RateLimitError],
)

# RAG检索重试策略
RAG_RETRY = RetryPolicy(
    max_attempts=2,
    initial_interval=1.0,
    backoff_factor=2.0,
    jitter=True,
    retry_on=[ConnectionError, TimeoutError],
)

# 数据库查询重试策略
DB_RETRY = RetryPolicy(
    max_attempts=3,
    initial_interval=0.5,
    backoff_factor=1.5,
    jitter=True,
    retry_on=[ConnectionError, DatabaseError],
)
```

### 5.2 降级策略

| 节点 | 重试失败后降级行为 |
|------|-------------------|
| `history_check` | 设置 `has_history=False`，继续流程 |
| `diagnose` | 使用默认诊断模板 |
| `explain` | 尝试RAG检索，否则使用通用模板 |
| `restate_check` | 跳过评估，直接进入 `followup` |
| `rag_first` | 设置 `rag_found=False`，走LLM回答 |

### 5.3 节点配置

```python
def build_learning_graph_v2():
    graph = StateGraph(LearningState)

    # 为各节点配置重试策略
    graph.add_node("diagnose", diagnose_node, retry=LLM_RETRY)
    graph.add_node("explain", explain_node, retry=LLM_RETRY)
    graph.add_node("restate_check", restate_check_node, retry=LLM_RETRY)
    graph.add_node("followup", followup_node, retry=LLM_RETRY)
    graph.add_node("summary", summary_node, retry=LLM_RETRY)
    graph.add_node("history_check", history_check_node, retry=DB_RETRY)
    graph.add_node("rag_first", rag_first_node, retry=RAG_RETRY)
```

---

## 六、文件结构

```
app/agent/
├── __init__.py
├── graph.py              # 旧版图（保留兼容）
├── graph_v2.py           # 新版图（条件边+检查点+重试）
├── state.py              # 状态定义（扩展）
├── nodes.py              # 节点定义（拆分出来）
├── routers.py            # 路由函数（条件边逻辑）
├── checkpointer.py       # 检查点配置
└── retry_policy.py       # 重试策略定义

tests/
├── test_agent_graph_v2.py        # 新图单元测试
├── test_agent_conditional_edges.py  # 条件边测试
└── test_agent_checkpointer.py    # 检查点测试
```

---

## 七、迁移策略

### 7.1 阶段一：创建新文件（1周）

1. 创建 `graph_v2.py`，实现完整的新图结构
2. 创建 `nodes.py`，拆分节点定义
3. 创建 `routers.py`，定义条件边路由函数
4. 创建 `checkpointer.py`，配置检查点
5. 创建 `retry_policy.py`，定义重试策略

### 7.2 阶段二：集成测试（1周）

1. 编写新图的单元测试
2. 编写条件边测试
3. 编写检查点测试
4. 编写重试策略测试

### 7.3 阶段三：流量切换（1周）

1. 在 `agent_service.py` 中添加开关
2. 支持 `graph` 或 `graph_v2` 选择
3. 灰度发布，逐步切换流量
4. 监控新图的稳定性和性能

### 7.4 阶段四：清理（1周）

1. 验证新图稳定后，废弃旧图
2. 将 `graph_v2` 重命名为 `graph`
3. 清理冗余代码

---

## 附录：关键判断条件汇总

| 条件边 | 判断条件 | 路由目标 |
|--------|----------|----------|
| `route_by_intent` | intent == "qa_direct" | rag_first |
| | intent == "replan" | replan |
| | intent == "review" | summary |
| | 其他（默认） | history_check |
| `route_after_history_check` | has_history == True | ask_review_or_continue |
| | has_history == False | diagnose |
| `route_after_choice` | user_choice == "review" | diagnose |
| | user_choice == "continue" | explain |
| `route_after_diagnosis` | diagnosis包含"已掌握"/"熟悉" | summary |
| | diagnosis包含"需要补充" | knowledge_retrieval |
| | 其他 | explain |
| `route_after_restate` | restatement_eval包含"已理解"/"准确" | summary |
| | 包含"错误"/"混淆"且循环<3次 | explain（循环） |
| | 其他 | followup |
| `route_after_rag` | rag_found == True | rag_answer |
| | rag_found == False | llm_answer |
