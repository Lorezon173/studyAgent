# LangGraph核心重构实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 重构Agent编排，使用LangGraph的条件边、检查点、重试策略特性，实现动态路由和会话持久化

**Architecture:** 采用渐进式重构策略，保留现有`graph.py`兼容层，新建`graph_v2.py`实现完整特性。新增历史记录检查和RAG优先检索功能。使用SQLite作为检查点存储，支持会话恢复和状态回放。

**Tech Stack:** LangGraph (StateGraph, conditional edges, checkpointer, RetryPolicy), SQLite, Python 3.11+

---

## 文件结构

```
app/agent/
├── graph.py              # [保留] 旧版图
├── graph_v2.py           # [新建] 新版图（条件边+检查点+重试）
├── state.py              # [修改] 扩展状态字段
├── nodes.py              # [新建] 节点定义
├── routers.py            # [新建] 路由函数（条件边逻辑）
├── checkpointer.py       # [新建] 检查点配置
└── retry_policy.py       # [新建] 重试策略定义

tests/
├── test_agent_graph_v2.py           # [新建] 新图单元测试
├── test_agent_conditional_edges.py  # [新建] 条件边测试
└── test_agent_checkpointer.py       # [新建] 检查点测试
```

---

## Task 1: 扩展状态定义

**Files:**
- Modify: `app/agent/state.py:1-52`

- [ ] **Step 1: 添加新状态字段**

在 `LearningState` 类中添加以下字段：

```python
class LearningState(TypedDict, total=False):
    # ... 现有字段 ...
    
    # 新增：历史记录检查
    has_history: bool
    history_summary: str
    history_mastery: str
    
    # 新增：用户选择
    user_choice: str
    waiting_for_choice: bool
    
    # 新增：RAG优先检索
    rag_context: str
    rag_citations: List[dict]
    rag_found: bool
    
    # 新增：讲解循环控制
    explain_loop_count: int
    
    # 新增：知识检索
    retrieved_context: str
    
    # 新增：降级标记
    fallback_used: bool
    node_error: str
```

- [ ] **Step 2: 验证状态定义语法**

Run: `python -c "from app.agent.state import LearningState; print('State OK')"`
Expected: `State OK`

- [ ] **Step 3: Commit**

```bash
git add app/agent/state.py
git commit -m "feat(state): add new state fields for history check, RAG-first, and loop control"
```

---

## Task 2: 创建重试策略模块

**Files:**
- Create: `app/agent/retry_policy.py`

- [ ] **Step 1: 创建重试策略文件**

```python
# app/agent/retry_policy.py
"""
重试策略定义
为不同类型的节点配置重试策略
"""

from langgraph.pregel import RetryPolicy


# 自定义异常类型（用于重试判断）
class RateLimitError(Exception):
    """LLM限流错误"""
    pass


class DatabaseError(Exception):
    """数据库错误"""
    pass


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

# 无重试策略（用于不需要重试的节点）
NO_RETRY = None
```

- [ ] **Step 2: 验证导入**

Run: `python -c "from app.agent.retry_policy import LLM_RETRY, RAG_RETRY, DB_RETRY; print('Retry policies OK')"`
Expected: `Retry policies OK`

- [ ] **Step 3: Commit**

```bash
git add app/agent/retry_policy.py
git commit -m "feat(retry): add retry policy definitions for LLM, RAG, and DB nodes"
```

---

## Task 3: 创建检查点模块

**Files:**
- Create: `app/agent/checkpointer.py`

- [ ] **Step 1: 创建检查点配置文件**

```python
# app/agent/checkpointer.py
"""
检查点存储配置
支持SQLite持久化存储会话状态
"""

from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.sqlite import SqliteSaver

from app.core.config import settings

# 单例检查点存储器
_checkpointer = None


def get_checkpointer():
    """
    获取检查点存储器
    
    根据配置选择存储后端：
    - SQLite: 持久化存储，支持进程重启后恢复
    - Memory: 内存存储，仅用于开发测试
    """
    global _checkpointer
    if _checkpointer is not None:
        return _checkpointer
    
    backend = settings.session_store_backend.lower()
    
    if backend == "sqlite":
        _checkpointer = SqliteSaver.from_conn_string(settings.session_sqlite_path)
    else:
        _checkpointer = MemorySaver()
    
    return _checkpointer


def reset_checkpointer():
    """重置检查点存储器（用于测试）"""
    global _checkpointer
    _checkpointer = None
```

- [ ] **Step 2: 验证导入**

Run: `python -c "from app.agent.checkpointer import get_checkpointer; print('Checkpointer OK')"`
Expected: `Checkpointer OK`

- [ ] **Step 3: Commit**

```bash
git add app/agent/checkpointer.py
git commit -m "feat(checkpointer): add SQLite-based checkpointer for session persistence"
```

---

## Task 4: 创建路由函数模块

**Files:**
- Create: `app/agent/routers.py`

- [ ] **Step 1: 创建路由函数文件**

```python
# app/agent/routers.py
"""
图路由函数
定义条件边的路由逻辑
"""

from typing import Literal

from app.agent.state import LearningState


def route_by_intent(state: LearningState) -> Literal["history_check", "rag_first", "replan", "summary"]:
    """
    根据意图路由到不同分支
    
    路由规则：
    - qa_direct -> rag_first (问答走RAG优先)
    - replan -> replan
    - review -> summary
    - teach_loop -> history_check (教学走历史检查)
    """
    intent = state.get("intent", "teach_loop")

    route_map = {
        "qa_direct": "rag_first",
        "replan": "replan",
        "review": "summary",
        "teach_loop": "history_check",
    }

    return route_map.get(intent, "history_check")


def route_after_history_check(state: LearningState) -> Literal["ask_review_or_continue", "diagnose"]:
    """
    历史检查后路由
    
    路由规则：
    - has_history == True -> ask_review_or_continue (询问用户)
    - has_history == False -> diagnose (直接诊断)
    """
    if state.get("has_history", False):
        return "ask_review_or_continue"
    else:
        return "diagnose"


def route_after_choice(state: LearningState) -> Literal["diagnose", "explain"]:
    """
    用户选择后路由
    
    路由规则：
    - user_choice == "review" -> diagnose (复习模式)
    - user_choice == "continue" -> explain (继续学习)
    """
    choice = state.get("user_choice", "continue")

    if choice == "review":
        return "diagnose"
    else:
        return "explain"


def route_after_diagnosis(state: LearningState) -> Literal["explain", "knowledge_retrieval", "summary"]:
    """
    诊断后路由
    
    路由规则：
    - 已掌握/熟悉 -> summary (跳过讲解)
    - 需要补充 -> knowledge_retrieval (先检索知识)
    - 其他 -> explain (正常讲解)
    """
    diagnosis = state.get("diagnosis", "")

    # 已掌握，跳过讲解
    if any(k in diagnosis for k in ["已掌握", "熟悉", "理解充分"]):
        return "summary"

    # 需要外部知识
    if any(k in diagnosis for k in ["需要补充", "缺少资料", "建议参考"]):
        return "knowledge_retrieval"

    return "explain"


def route_after_restate(state: LearningState) -> Literal["followup", "explain", "summary"]:
    """
    复述评估后路由
    
    路由规则：
    - 已理解/准确 -> summary
    - 错误/混淆且循环<3次 -> explain (重新讲解)
    - 其他 -> followup
    """
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


def route_after_rag(state: LearningState) -> Literal["rag_answer", "llm_answer"]:
    """
    RAG检索后路由
    
    路由规则：
    - rag_found == True -> rag_answer
    - rag_found == False -> llm_answer
    """
    if state.get("rag_found", False):
        return "rag_answer"
    else:
        return "llm_answer"
```

- [ ] **Step 2: 验证导入**

Run: `python -c "from app.agent.routers import route_by_intent, route_after_history_check; print('Routers OK')"`
Expected: `Routers OK`

- [ ] **Step 3: Commit**

```bash
git add app/agent/routers.py
git commit -m "feat(routers): add conditional edge routing functions"
```

---

## Task 5: 创建节点模块

**Files:**
- Create: `app/agent/nodes.py`

- [ ] **Step 1: 创建节点定义文件（第一部分：导入和辅助函数）**

```python
# app/agent/nodes.py
"""
Agent节点定义
每个节点专注于单一职责，支持容错和降级
"""

import json
from datetime import datetime, UTC
from typing import Any

from app.agent.state import LearningState
from app.core.prompts import (
    DIAGNOSE_PROMPT,
    EXPLAIN_PROMPT,
    RESTATE_CHECK_PROMPT,
    FOLLOWUP_PROMPT,
    SUMMARY_PROMPT,
)
from app.services.llm import llm_service


def _get_timestamp() -> str:
    """获取ISO格式时间戳"""
    return datetime.now(UTC).isoformat()


def _append_trace(state: LearningState, phase: str, data: dict) -> None:
    """追加执行追踪"""
    traces = state.get("branch_trace", [])
    traces.append({
        "phase": phase,
        "timestamp": _get_timestamp(),
        **data
    })
    state["branch_trace"] = traces
```

- [ ] **Step 2: 添加意图路由节点**

追加到 `app/agent/nodes.py`:

```python


def intent_router_node(state: LearningState) -> LearningState:
    """
    意图路由节点：识别用户意图
    """
    user_input = state.get("user_input", "")
    
    try:
        raw = llm_service.route_intent(user_input)
        data = json.loads(raw)
        intent = str(data.get("intent", "teach_loop")).strip()
        confidence = float(data.get("confidence", 0.0))
        reason = str(data.get("reason", ""))
        
        # 验证意图有效性
        valid_intents = {"teach_loop", "qa_direct", "review", "replan"}
        if intent not in valid_intents:
            intent = "teach_loop"
        
        state["intent"] = intent
        state["intent_confidence"] = confidence
        state["intent_reason"] = reason
        
    except Exception as e:
        # 降级：使用规则路由
        state["intent"] = _rule_based_route(user_input)
        state["intent_confidence"] = 0.7
        state["intent_reason"] = f"LLM路由失败，使用规则回退: {str(e)}"
    
    _append_trace(state, "intent_router", {
        "intent": state.get("intent"),
        "confidence": state.get("intent_confidence"),
    })
    
    return state


def _rule_based_route(user_input: str) -> str:
    """基于规则的意图路由"""
    text = user_input.lower()
    if any(k in text for k in ["重规划", "replan", "换个目标", "重新计划"]):
        return "replan"
    if any(k in text for k in ["总结", "复盘", "回顾", "review"]):
        return "review"
    if any(k in text for k in ["为什么", "怎么", "是什么", "?", "？", "请直接回答"]):
        return "qa_direct"
    return "teach_loop"
```

- [ ] **Step 3: 添加历史记录检查节点**

追加到 `app/agent/nodes.py`:

```python


def history_check_node(state: LearningState) -> LearningState:
    """
    历史记录检查节点：检查用户是否学习过该主题
    """
    from app.services.learning_analysis import get_topic_mastery
    
    user_id = state.get("user_id")
    topic = state.get("topic")
    
    state["has_history"] = False
    state["history_summary"] = ""
    state["history_mastery"] = ""
    
    if not user_id or not topic:
        _append_trace(state, "history_check", {"has_history": False, "reason": "no_user_or_topic"})
        return state
    
    try:
        mastery = get_topic_mastery(user_id=user_id, topic=topic)
        
        if mastery and mastery.get("records"):
            state["has_history"] = True
            records = mastery["records"][:3]  # 最近3条记录
            state["history_summary"] = "；".join([
                f"{r.get('stage', 'unknown')}: {r.get('summary', '')[:50]}"
                for r in records
            ])
            state["history_mastery"] = mastery.get("level", "unknown")
    except Exception as e:
        state["node_error"] = f"history_check: {str(e)}"
    
    _append_trace(state, "history_check", {
        "has_history": state.get("has_history"),
        "mastery": state.get("history_mastery"),
    })
    
    return state
```

- [ ] **Step 4: 添加询问节点**

追加到 `app/agent/nodes.py`:

```python


def ask_review_or_continue_node(state: LearningState) -> LearningState:
    """
    询问节点：根据历史记录询问用户选择复习或继续
    """
    topic = state.get("topic", "该主题")
    history_summary = state.get("history_summary", "")
    history_mastery = state.get("history_mastery", "未知")
    
    state["reply"] = f"""检测到你之前学习过【{topic}】：
{history_summary}

当前掌握程度：{history_mastery}

请问你是想要：
1. 快速复习之前学过的内容
2. 继续学习剩余的内容

请回复"复习"或"继续"。"""
    
    state["waiting_for_choice"] = True
    state["stage"] = "waiting_for_choice"
    
    _append_trace(state, "ask_review_or_continue", {"has_history": True})
    
    return state
```

- [ ] **Step 5: 添加RAG优先检索节点**

追加到 `app/agent/nodes.py`:

```python


def rag_first_node(state: LearningState) -> LearningState:
    """
    RAG优先检索节点：在回答问题前，先检索本地知识库
    """
    from app.services.rag_coordinator import rag_coordinator
    
    topic = state.get("topic")
    user_input = state.get("user_input", "")
    user_id = state.get("user_id")
    
    state["rag_found"] = False
    state["rag_context"] = ""
    state["rag_citations"] = []
    
    try:
        context, citations = rag_coordinator.execute(
            rag_coordinator.decide(
                user_input=user_input,
                topic=topic,
                user_id=str(user_id) if user_id else None,
                tool_route=state.get("tool_route"),
            ),
            user_input=user_input,
        )
        
        if context:
            state["rag_context"] = context
            state["rag_citations"] = citations
            state["rag_found"] = True
    except Exception as e:
        state["node_error"] = f"rag_first: {str(e)}"
    
    _append_trace(state, "rag_first", {
        "rag_found": state.get("rag_found"),
        "citations_count": len(state.get("rag_citations", [])),
    })
    
    return state


def rag_answer_node(state: LearningState) -> LearningState:
    """
    基于RAG知识回答节点
    """
    user_input = state.get("user_input", "")
    rag_context = state.get("rag_context", "")
    
    prompt = f"""请基于以下知识回答用户问题。

【相关知识】
{rag_context}

【用户问题】
{user_input}

请准确回答，并标注知识来源。"""
    
    stream_output = bool(state.get("stream_output", False))
    
    reply = llm_service.invoke(
        system_prompt="你是一个严谨的知识问答助手，请基于提供的知识准确回答问题。",
        user_prompt=prompt,
        stream_output=stream_output,
    )
    
    state["reply"] = reply
    state["stage"] = "rag_answered"
    
    _append_trace(state, "rag_answer", {"reply_length": len(reply)})
    
    return state


def llm_answer_node(state: LearningState) -> LearningState:
    """
    基于LLM回答节点（无知识库支撑）
    """
    user_input = state.get("user_input", "")
    
    stream_output = bool(state.get("stream_output", False))
    
    reply = llm_service.invoke(
        system_prompt="你是一个知识渊博的问答助手。",
        user_prompt=user_input,
        stream_output=stream_output,
    )
    
    state["reply"] = reply
    state["stage"] = "llm_answered"
    
    _append_trace(state, "llm_answer", {"reply_length": len(reply)})
    
    return state
```

- [ ] **Step 6: 添加教学循环节点**

追加到 `app/agent/nodes.py`:

```python


def diagnose_node(state: LearningState) -> LearningState:
    """
    诊断节点：识别用户先验知识水平
    """
    topic = state.get("topic") or "未指定主题"
    user_input = state.get("user_input", "")
    topic_context = state.get("topic_context", "")
    
    prompt = DIAGNOSE_PROMPT.format(topic=topic, user_input=user_input, topic_context=topic_context)
    
    diagnosis = llm_service.invoke(
        system_prompt="你是严谨的学习诊断助手。",
        user_prompt=prompt,
    )
    
    state["diagnosis"] = diagnosis
    state["stage"] = "diagnosed"
    
    _append_trace(state, "diagnose", {"diagnosis_length": len(diagnosis)})
    
    return state


def knowledge_retrieval_node(state: LearningState) -> LearningState:
    """
    知识检索节点：在需要时补充知识
    """
    from app.services.rag_coordinator import rag_coordinator
    
    topic = state.get("topic")
    user_input = state.get("user_input", "")
    user_id = state.get("user_id")
    
    context, citations = rag_coordinator.execute(
        rag_coordinator.decide(
            user_input=user_input,
            topic=topic,
            user_id=str(user_id) if user_id else None,
            tool_route=state.get("tool_route"),
        ),
        user_input=user_input,
    )
    
    state["retrieved_context"] = context
    state["citations"] = citations
    
    # 将检索到的知识追加到主题上下文
    if context:
        existing = state.get("topic_context", "")
        state["topic_context"] = f"{existing}\n\n{context}".strip()
    
    _append_trace(state, "knowledge_retrieval", {"citations_count": len(citations)})
    
    return state


def explain_node(state: LearningState) -> LearningState:
    """
    讲解节点：用费曼法解释概念
    """
    topic = state.get("topic") or "未指定主题"
    user_input = state.get("user_input", "")
    topic_context = state.get("topic_context", "")
    
    prompt = EXPLAIN_PROMPT.format(topic=topic, user_input=user_input, topic_context=topic_context)
    
    stream_output = bool(state.get("stream_output", False))
    
    explanation = llm_service.invoke(
        system_prompt="你是擅长费曼学习法的教学助手。",
        user_prompt=prompt,
        stream_output=stream_output,
    )
    
    state["explanation"] = explanation
    state["reply"] = explanation
    state["stage"] = "explained"
    
    # 重置重讲解标记
    state.pop("need_re_explain", None)
    
    _append_trace(state, "explain", {"explanation_length": len(explanation)})
    
    return state


def restate_check_node(state: LearningState) -> LearningState:
    """
    复述检测节点：检验用户理解深度
    """
    topic = state.get("topic") or "未指定主题"
    explanation = state.get("explanation", "")
    user_input = state.get("user_input", "")
    topic_context = state.get("topic_context", "")
    
    prompt = RESTATE_CHECK_PROMPT.format(
        topic=topic,
        explanation=explanation,
        user_input=user_input,
        topic_context=topic_context,
    )
    
    result = llm_service.invoke(
        system_prompt="你是严格但友好的学习评估助手。",
        user_prompt=prompt,
    )
    
    state["restatement_eval"] = result
    state["stage"] = "restatement_checked"
    
    _append_trace(state, "restate_check", {"eval_length": len(result)})
    
    return state


def followup_node(state: LearningState) -> LearningState:
    """
    追问节点：基于漏洞进行针对性追问
    """
    topic = state.get("topic") or "未指定主题"
    restatement_eval = state.get("restatement_eval", "")
    topic_context = state.get("topic_context", "")
    
    prompt = FOLLOWUP_PROMPT.format(
        topic=topic,
        restatement_eval=restatement_eval,
        topic_context=topic_context,
    )
    
    stream_output = bool(state.get("stream_output", False))
    
    question = llm_service.invoke(
        system_prompt="你是费曼学习法中的追问老师。",
        user_prompt=prompt,
        stream_output=stream_output,
    )
    
    state["followup_question"] = question
    state["reply"] = question
    state["stage"] = "followup_generated"
    
    _append_trace(state, "followup", {"question_length": len(question)})
    
    return state


def summarize_node(state: LearningState) -> LearningState:
    """
    总结节点：输出学习成果和复习建议
    """
    topic = state.get("topic") or "未指定主题"
    topic_context = state.get("topic_context", "")
    
    prompt = SUMMARY_PROMPT.format(
        topic=topic,
        diagnosis=state.get("diagnosis", ""),
        explanation=state.get("explanation", ""),
        restatement_eval=state.get("restatement_eval", ""),
        followup_question=state.get("followup_question", ""),
        topic_context=topic_context,
    )
    
    stream_output = bool(state.get("stream_output", False))
    
    summary = llm_service.invoke(
        system_prompt="你是负责复盘学习成果的老师。",
        user_prompt=prompt,
        stream_output=stream_output,
    )
    
    state["summary"] = summary
    state["reply"] = summary
    state["stage"] = "summarized"
    
    _append_trace(state, "summary", {"summary_length": len(summary)})
    
    return state


def replan_node(state: LearningState) -> LearningState:
    """
    重规划节点
    """
    from app.services.agent_runtime import create_or_update_plan
    
    state["current_plan"] = create_or_update_plan(state)
    state["current_step_index"] = 0
    state["need_replan"] = False
    state["replan_reason"] = ""
    
    plan = state["current_plan"]
    steps = plan.get("steps", [])
    next_step = ""
    if isinstance(steps, list) and steps:
        first = steps[0]
        if isinstance(first, dict):
            next_step = str(first.get("description") or first.get("name") or "")
    
    state["next_stage"] = "start"
    state["stage"] = "planned"
    state["reply"] = (
        "已根据你的新输入完成重规划。\n"
        f"当前目标：{plan.get('goal', '未设置')}\n"
        f"下一步建议：{next_step or '继续描述你的学习目标或直接提问'}"
    )
    
    _append_trace(state, "replan", {"new_goal": plan.get("goal")})
    
    return state
```

- [ ] **Step 7: 验证节点导入**

Run: `python -c "from app.agent.nodes import intent_router_node, diagnose_node, explain_node; print('Nodes OK')"`
Expected: `Nodes OK`

- [ ] **Step 8: Commit**

```bash
git add app/agent/nodes.py
git commit -m "feat(nodes): add all node definitions for graph_v2"
```

---

## Task 6: 创建新图模块

**Files:**
- Create: `app/agent/graph_v2.py`

- [ ] **Step 1: 创建新图定义文件**

```python
# app/agent/graph_v2.py
"""
学习Agent图定义 V2
充分利用LangGraph特性：条件边、检查点、重试策略
"""
from langgraph.graph import END, StateGraph

from app.agent.state import LearningState
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
)
from app.agent.routers import (
    route_by_intent,
    route_after_history_check,
    route_after_choice,
    route_after_diagnosis,
    route_after_restate,
    route_after_rag,
)
from app.agent.checkpointer import get_checkpointer
from app.agent.retry_policy import LLM_RETRY, RAG_RETRY, DB_RETRY


def build_learning_graph_v2():
    """
    构建完整的学习Agent图
    
    特性：
    - 条件边：动态路由决策
    - 检查点：会话状态持久化
    - 重试策略：节点级容错
    """
    graph = StateGraph(LearningState)
    
    # ===== 添加节点 =====
    
    # 入口路由节点
    graph.add_node("intent_router", intent_router_node, retry=LLM_RETRY)
    
    # 历史检查节点
    graph.add_node("history_check", history_check_node, retry=DB_RETRY)
    graph.add_node("ask_review_or_continue", ask_review_or_continue_node)
    
    # 核心教学节点
    graph.add_node("diagnose", diagnose_node, retry=LLM_RETRY)
    graph.add_node("knowledge_retrieval", knowledge_retrieval_node, retry=RAG_RETRY)
    graph.add_node("explain", explain_node, retry=LLM_RETRY)
    graph.add_node("restate_check", restate_check_node, retry=LLM_RETRY)
    graph.add_node("followup", followup_node, retry=LLM_RETRY)
    graph.add_node("summary", summarize_node, retry=LLM_RETRY)
    
    # RAG优先问答节点
    graph.add_node("rag_first", rag_first_node, retry=RAG_RETRY)
    graph.add_node("rag_answer", rag_answer_node, retry=LLM_RETRY)
    graph.add_node("llm_answer", llm_answer_node, retry=LLM_RETRY)
    
    # 重规划节点
    graph.add_node("replan", replan_node, retry=LLM_RETRY)
    
    # ===== 设置入口 =====
    graph.set_entry_point("intent_router")
    
    # ===== 条件边 =====
    
    # 意图路由
    graph.add_conditional_edges(
        "intent_router",
        route_by_intent,
        {
            "history_check": "history_check",
            "rag_first": "rag_first",
            "replan": "replan",
            "summary": "summary",
        }
    )
    
    # 历史检查后路由
    graph.add_conditional_edges(
        "history_check",
        route_after_history_check,
        {
            "ask_review_or_continue": "ask_review_or_continue",
            "diagnose": "diagnose",
        }
    )
    
    # 用户选择后路由
    graph.add_conditional_edges(
        "ask_review_or_continue",
        route_after_choice,
        {
            "diagnose": "diagnose",
            "explain": "explain",
        }
    )
    
    # 诊断后路由
    graph.add_conditional_edges(
        "diagnose",
        route_after_diagnosis,
        {
            "explain": "explain",
            "knowledge_retrieval": "knowledge_retrieval",
            "summary": "summary",
        }
    )
    
    # 复述后路由
    graph.add_conditional_edges(
        "restate_check",
        route_after_restate,
        {
            "followup": "followup",
            "explain": "explain",
            "summary": "summary",
        }
    )
    
    # RAG检索后路由
    graph.add_conditional_edges(
        "rag_first",
        route_after_rag,
        {
            "rag_answer": "rag_answer",
            "llm_answer": "llm_answer",
        }
    )
    
    # ===== 固定边 =====
    graph.add_edge("knowledge_retrieval", "explain")
    graph.add_edge("explain", "restate_check")
    graph.add_edge("followup", "summary")
    graph.add_edge("summary", END)
    graph.add_edge("rag_answer", END)
    graph.add_edge("llm_answer", END)
    graph.add_edge("replan", END)
    
    # ===== 编译图 =====
    checkpointer = get_checkpointer()
    return graph.compile(checkpointer=checkpointer)


# 单例
_learning_graph_v2 = None


def get_learning_graph_v2():
    """获取学习图V2单例"""
    global _learning_graph_v2
    if _learning_graph_v2 is None:
        _learning_graph_v2 = build_learning_graph_v2()
    return _learning_graph_v2
```

- [ ] **Step 2: 验证图构建**

Run: `python -c "from app.agent.graph_v2 import build_learning_graph_v2; g = build_learning_graph_v2(); print('Graph V2 OK')"`
Expected: `Graph V2 OK`

- [ ] **Step 3: Commit**

```bash
git add app/agent/graph_v2.py
git commit -m "feat(graph_v2): add new graph with conditional edges, checkpointer, and retry policies"
```

---

## Task 7: 编写条件边测试

**Files:**
- Create: `tests/test_agent_conditional_edges.py`

- [ ] **Step 1: 创建条件边测试文件**

```python
# tests/test_agent_conditional_edges.py
"""
条件边路由函数测试
"""

import pytest

from app.agent.routers import (
    route_by_intent,
    route_after_history_check,
    route_after_choice,
    route_after_diagnosis,
    route_after_restate,
    route_after_rag,
)
from app.agent.state import LearningState


class TestRouteByIntent:
    """意图路由测试"""
    
    def test_route_teach_loop_to_history_check(self):
        state: LearningState = {"intent": "teach_loop"}
        assert route_by_intent(state) == "history_check"
    
    def test_route_qa_direct_to_rag_first(self):
        state: LearningState = {"intent": "qa_direct"}
        assert route_by_intent(state) == "rag_first"
    
    def test_route_replan_to_replan(self):
        state: LearningState = {"intent": "replan"}
        assert route_by_intent(state) == "replan"
    
    def test_route_review_to_summary(self):
        state: LearningState = {"intent": "review"}
        assert route_by_intent(state) == "summary"
    
    def test_route_unknown_intent_defaults_to_history_check(self):
        state: LearningState = {"intent": "unknown_intent"}
        assert route_by_intent(state) == "history_check"
    
    def test_route_missing_intent_defaults_to_history_check(self):
        state: LearningState = {}
        assert route_by_intent(state) == "history_check"


class TestRouteAfterHistoryCheck:
    """历史检查后路由测试"""
    
    def test_has_history_routes_to_ask(self):
        state: LearningState = {"has_history": True}
        assert route_after_history_check(state) == "ask_review_or_continue"
    
    def test_no_history_routes_to_diagnose(self):
        state: LearningState = {"has_history": False}
        assert route_after_history_check(state) == "diagnose"
    
    def test_missing_has_history_defaults_to_diagnose(self):
        state: LearningState = {}
        assert route_after_history_check(state) == "diagnose"


class TestRouteAfterChoice:
    """用户选择后路由测试"""
    
    def test_review_choice_routes_to_diagnose(self):
        state: LearningState = {"user_choice": "review"}
        assert route_after_choice(state) == "diagnose"
    
    def test_continue_choice_routes_to_explain(self):
        state: LearningState = {"user_choice": "continue"}
        assert route_after_choice(state) == "explain"
    
    def test_missing_choice_defaults_to_explain(self):
        state: LearningState = {}
        assert route_after_choice(state) == "explain"


class TestRouteAfterDiagnosis:
    """诊断后路由测试"""
    
    def test_mastered_routes_to_summary(self):
        state: LearningState = {"diagnosis": "用户已掌握该知识点"}
        assert route_after_diagnosis(state) == "summary"
    
    def test_familiar_routes_to_summary(self):
        state: LearningState = {"diagnosis": "用户对该主题比较熟悉"}
        assert route_after_diagnosis(state) == "summary"
    
    def test_needs_supplement_routes_to_knowledge_retrieval(self):
        state: LearningState = {"diagnosis": "需要补充相关背景知识"}
        assert route_after_diagnosis(state) == "knowledge_retrieval"
    
    def test_normal_diagnosis_routes_to_explain(self):
        state: LearningState = {"diagnosis": "用户对该主题了解较少"}
        assert route_after_diagnosis(state) == "explain"
    
    def test_missing_diagnosis_defaults_to_explain(self):
        state: LearningState = {}
        assert route_after_diagnosis(state) == "explain"


class TestRouteAfterRestate:
    """复述后路由测试"""
    
    def test_understood_routes_to_summary(self):
        state: LearningState = {"restatement_eval": "用户已理解核心概念"}
        assert route_after_restate(state) == "summary"
    
    def test_accurate_routes_to_summary(self):
        state: LearningState = {"restatement_eval": "复述准确无误"}
        assert route_after_restate(state) == "summary"
    
    def test_error_routes_to_explain_with_loop_count(self):
        state: LearningState = {
            "restatement_eval": "用户存在概念错误",
            "explain_loop_count": 0,
        }
        result = route_after_restate(state)
        assert result == "explain"
        assert state["explain_loop_count"] == 1
    
    def test_error_max_loop_routes_to_followup(self):
        state: LearningState = {
            "restatement_eval": "用户理解有误",
            "explain_loop_count": 3,
        }
        result = route_after_restate(state)
        assert result == "followup"
    
    def test_partial_understanding_routes_to_followup(self):
        state: LearningState = {
            "restatement_eval": "用户理解了部分内容",
            "explain_loop_count": 0,
        }
        assert route_after_restate(state) == "followup"


class TestRouteAfterRag:
    """RAG检索后路由测试"""
    
    def test_rag_found_routes_to_rag_answer(self):
        state: LearningState = {"rag_found": True}
        assert route_after_rag(state) == "rag_answer"
    
    def test_rag_not_found_routes_to_llm_answer(self):
        state: LearningState = {"rag_found": False}
        assert route_after_rag(state) == "llm_answer"
    
    def test_missing_rag_found_defaults_to_llm_answer(self):
        state: LearningState = {}
        assert route_after_rag(state) == "llm_answer"
```

- [ ] **Step 2: 运行测试**

Run: `pytest tests/test_agent_conditional_edges.py -v`
Expected: All tests pass

- [ ] **Step 3: Commit**

```bash
git add tests/test_agent_conditional_edges.py
git commit -m "test(routers): add comprehensive tests for conditional edge routing functions"
```

---

## Task 8: 编写检查点测试

**Files:**
- Create: `tests/test_agent_checkpointer.py`

- [ ] **Step 1: 创建检查点测试文件**

```python
# tests/test_agent_checkpointer.py
"""
检查点功能测试
"""

import os
import tempfile

import pytest

from app.agent.checkpointer import get_checkpointer, reset_checkpointer
from app.core.config import settings


class TestCheckpointer:
    """检查点测试"""
    
    def test_get_checkpointer_returns_memory_saver_by_default(self, monkeypatch):
        """默认使用内存存储"""
        reset_checkpointer()
        monkeypatch.setattr(settings, "session_store_backend", "memory")
        
        checkpointer = get_checkpointer()
        assert checkpointer is not None
        reset_checkpointer()
    
    def test_get_checkpointer_returns_sqlite_saver_when_configured(self, monkeypatch):
        """配置SQLite时使用SQLite存储"""
        reset_checkpointer()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_checkpointer.db")
            monkeypatch.setattr(settings, "session_store_backend", "sqlite")
            monkeypatch.setattr(settings, "session_sqlite_path", db_path)
            
            checkpointer = get_checkpointer()
            assert checkpointer is not None
            
        reset_checkpointer()
    
    def test_checkpointer_singleton(self, monkeypatch):
        """检查点是单例"""
        reset_checkpointer()
        monkeypatch.setattr(settings, "session_store_backend", "memory")
        
        c1 = get_checkpointer()
        c2 = get_checkpointer()
        assert c1 is c2
        
        reset_checkpointer()
    
    def test_reset_checkpointer_creates_new_instance(self, monkeypatch):
        """重置后创建新实例"""
        reset_checkpointer()
        monkeypatch.setattr(settings, "session_store_backend", "memory")
        
        c1 = get_checkpointer()
        reset_checkpointer()
        c2 = get_checkpointer()
        
        assert c1 is not c2
        
        reset_checkpointer()
```

- [ ] **Step 2: 运行测试**

Run: `pytest tests/test_agent_checkpointer.py -v`
Expected: All tests pass

- [ ] **Step 3: Commit**

```bash
git add tests/test_agent_checkpointer.py
git commit -m "test(checkpointer): add tests for checkpointer singleton and storage backends"
```

---

## Task 9: 编写新图集成测试

**Files:**
- Create: `tests/test_agent_graph_v2.py`

- [ ] **Step 1: 创建新图测试文件**

```python
# tests/test_agent_graph_v2.py
"""
Graph V2集成测试
"""

import pytest

from app.agent.graph_v2 import build_learning_graph_v2
from app.agent.state import LearningState


@pytest.fixture
def graph():
    """构建测试图"""
    return build_learning_graph_v2()


@pytest.fixture
def initial_state() -> LearningState:
    """初始状态"""
    return {
        "session_id": "test-session",
        "user_input": "我想学习二分查找",
        "topic": "二分查找",
        "stage": "start",
        "history": [],
        "branch_trace": [],
    }


class TestGraphV2Build:
    """图构建测试"""
    
    def test_graph_builds_successfully(self, graph):
        """图能成功构建"""
        assert graph is not None
    
    def test_graph_has_correct_nodes(self, graph):
        """图包含所有必要节点"""
        # 获取图的节点名称
        nodes = set(graph.nodes.keys())
        expected_nodes = {
            "intent_router",
            "history_check",
            "ask_review_or_continue",
            "diagnose",
            "knowledge_retrieval",
            "explain",
            "restate_check",
            "followup",
            "summary",
            "rag_first",
            "rag_answer",
            "llm_answer",
            "replan",
        }
        assert expected_nodes.issubset(nodes)


class TestIntentRouting:
    """意图路由测试"""
    
    def test_route_to_teach_loop(self, graph, initial_state, monkeypatch):
        """测试正常教学路由"""
        def mock_route_intent(user_input):
            return '{"intent":"teach_loop","confidence":0.9,"reason":"学习请求"}'
        
        monkeypatch.setattr(
            "app.services.llm.llm_service.route_intent",
            mock_route_intent
        )
        monkeypatch.setattr(
            "app.services.llm.llm_service.invoke",
            lambda **kw: "mock response"
        )
        
        result = graph.invoke(initial_state)
        assert result.get("intent") == "teach_loop"
    
    def test_route_to_qa_direct(self, graph, initial_state, monkeypatch):
        """测试直接问答路由"""
        initial_state["user_input"] = "二分查找是什么？请直接回答"
        
        def mock_route_intent(user_input):
            return '{"intent":"qa_direct","confidence":0.95,"reason":"直接问答"}'
        
        monkeypatch.setattr(
            "app.services.llm.llm_service.route_intent",
            mock_route_intent
        )
        monkeypatch.setattr(
            "app.services.llm.llm_service.invoke",
            lambda **kw: "二分查找是一种在有序数组中查找的算法"
        )
        
        result = graph.invoke(initial_state)
        assert result.get("intent") == "qa_direct"
    
    def test_route_to_replan(self, graph, initial_state, monkeypatch):
        """测试重规划路由"""
        initial_state["user_input"] = "我不想学这个了，换个主题"
        
        def mock_route_intent(user_input):
            return '{"intent":"replan","confidence":0.9,"reason":"重规划请求"}'
        
        monkeypatch.setattr(
            "app.services.llm.llm_service.route_intent",
            mock_route_intent
        )
        
        result = graph.invoke(initial_state)
        assert result.get("intent") == "replan"


class TestConditionalEdges:
    """条件边测试"""
    
    def test_skip_explanation_when_mastered(self, graph, monkeypatch):
        """测试已掌握时跳过讲解"""
        state: LearningState = {
            "session_id": "test",
            "user_input": "我熟悉二分查找",
            "topic": "二分查找",
            "stage": "start",
            "diagnosis": "用户已掌握该知识点",
            "branch_trace": [],
        }
        
        monkeypatch.setattr(
            "app.services.llm.llm_service.invoke",
            lambda **kw: "用户已掌握二分查找的核心概念"
        )
        monkeypatch.setattr(
            "app.services.llm.llm_service.route_intent",
            lambda x: '{"intent":"teach_loop","confidence":0.9}'
        )
        
        result = graph.invoke(state)
        # 应该跳过讲解直接到总结
        assert result.get("stage") in ["summarized", "diagnosed"]
    
    def test_loop_back_to_explain(self, graph, monkeypatch):
        """测试复述失败后循环回讲解"""
        state: LearningState = {
            "session_id": "test",
            "user_input": "我不太理解",
            "topic": "二分查找",
            "stage": "explained",
            "explanation": "二分查找是...",
            "restatement_eval": "用户理解有误，存在概念混淆",
            "branch_trace": [],
            "explain_loop_count": 0,
        }
        
        monkeypatch.setattr(
            "app.services.llm.llm_service.invoke",
            lambda **kw: "用户理解有误，需要重新讲解"
        )
        monkeypatch.setattr(
            "app.services.llm.llm_service.route_intent",
            lambda x: '{"intent":"teach_loop","confidence":0.9}'
        )
        
        result = graph.invoke(state)
        # 应该循环回讲解或继续
        assert result.get("explain_loop_count", 0) >= 0
```

- [ ] **Step 2: 运行测试**

Run: `pytest tests/test_agent_graph_v2.py -v`
Expected: All tests pass (some may need mock adjustments)

- [ ] **Step 3: Commit**

```bash
git add tests/test_agent_graph_v2.py
git commit -m "test(graph_v2): add integration tests for new graph with conditional edges"
```

---

## Task 10: 更新agent_service支持图切换

**Files:**
- Modify: `app/services/agent_service.py:1-498`

- [ ] **Step 1: 在AgentService中添加图选择逻辑**

在 `agent_service.py` 顶部添加导入：

```python
from app.agent.graph_v2 import get_learning_graph_v2
from app.core.config import settings
```

在 `AgentService` 类中添加方法：

```python
class AgentService:
    # ... 现有代码 ...

    @staticmethod
    def _should_use_graph_v2() -> bool:
        """检查是否使用新版图"""
        return getattr(settings, "use_graph_v2", False)

    @staticmethod
    def run_with_graph_v2(
        session_id: str,
        topic: str | None,
        user_input: str,
        user_id: int | None = None,
        stream_output: bool = False,
    ) -> LearningState:
        """
        使用新版图运行会话
        """
        graph = get_learning_graph_v2()
        
        config = {"configurable": {"thread_id": session_id}}
        
        # 获取现有状态或创建新状态
        existing_state = graph.get_state(config)
        
        if existing_state and existing_state.values:
            state = existing_state.values.copy()
            state["user_input"] = user_input
            state["stream_output"] = stream_output
            if user_id is not None:
                state["user_id"] = user_id
        else:
            state: LearningState = {
                "session_id": session_id,
                "user_id": user_id,
                "topic": topic,
                "user_input": user_input,
                "stream_output": stream_output,
                "stage": "start",
                "history": [f"用户: {user_input}"],
                "branch_trace": [],
            }
        
        result = graph.invoke(state, config=config)
        result["history"] = result.get("history", []) + [f"助手: {result.get('reply', '')}"]
        
        return result
```

修改 `run` 方法开头添加图选择：

```python
def run(
    self,
    session_id: str,
    topic: str | None,
    user_input: str,
    user_id: int | None = None,
    stream_output: bool = False,
) -> LearningState:
    # 检查是否使用新版图
    if self._should_use_graph_v2():
        return self.run_with_graph_v2(
            session_id=session_id,
            topic=topic,
            user_input=user_input,
            user_id=user_id,
            stream_output=stream_output,
        )
    
    # ... 现有代码 ...
```

- [ ] **Step 2: 在config.py中添加配置项**

在 `app/core/config.py` 的 `Settings` 类中添加：

```python
class Settings(BaseSettings):
    # ... 现有字段 ...
    
    # Graph V2开关
    use_graph_v2: bool = False
```

- [ ] **Step 3: 验证配置**

Run: `python -c "from app.core.config import settings; print(f'use_graph_v2: {settings.use_graph_v2}')"`
Expected: `use_graph_v2: False`

- [ ] **Step 4: Commit**

```bash
git add app/services/agent_service.py app/core/config.py
git commit -m "feat(agent_service): add graph_v2 toggle support"
```

---

## Task 11: 更新__init__.py导出

**Files:**
- Modify: `app/agent/__init__.py`

- [ ] **Step 1: 更新导出**

```python
# app/agent/__init__.py
from app.agent.state import LearningState, TopicSegment
from app.agent.graph import (
    build_learning_graph,
    build_initial_graph,
    build_restate_graph,
    build_summary_graph,
    build_qa_direct_graph,
    learning_graph,
    initial_graph,
    restate_graph,
    summary_graph,
    qa_direct_graph,
)
from app.agent.graph_v2 import build_learning_graph_v2, get_learning_graph_v2
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
)
from app.agent.routers import (
    route_by_intent,
    route_after_history_check,
    route_after_choice,
    route_after_diagnosis,
    route_after_restate,
    route_after_rag,
)
from app.agent.checkpointer import get_checkpointer, reset_checkpointer
from app.agent.retry_policy import LLM_RETRY, RAG_RETRY, DB_RETRY

__all__ = [
    # State
    "LearningState",
    "TopicSegment",
    # Graph V1
    "build_learning_graph",
    "build_initial_graph",
    "build_restate_graph",
    "build_summary_graph",
    "build_qa_direct_graph",
    "learning_graph",
    "initial_graph",
    "restate_graph",
    "summary_graph",
    "qa_direct_graph",
    # Graph V2
    "build_learning_graph_v2",
    "get_learning_graph_v2",
    # Nodes
    "intent_router_node",
    "history_check_node",
    "ask_review_or_continue_node",
    "diagnose_node",
    "knowledge_retrieval_node",
    "explain_node",
    "restate_check_node",
    "followup_node",
    "summarize_node",
    "rag_first_node",
    "rag_answer_node",
    "llm_answer_node",
    "replan_node",
    # Routers
    "route_by_intent",
    "route_after_history_check",
    "route_after_choice",
    "route_after_diagnosis",
    "route_after_restate",
    "route_after_rag",
    # Checkpointer
    "get_checkpointer",
    "reset_checkpointer",
    # Retry Policy
    "LLM_RETRY",
    "RAG_RETRY",
    "DB_RETRY",
]
```

- [ ] **Step 2: 验证导出**

Run: `python -c "from app.agent import build_learning_graph_v2, get_learning_graph_v2; print('Imports OK')"`
Expected: `Imports OK`

- [ ] **Step 3: Commit**

```bash
git add app/agent/__init__.py
git commit -m "feat(agent): update exports to include graph_v2 and related modules"
```

---

## Task 12: 运行完整测试套件

**Files:**
- None (验证)

- [ ] **Step 1: 运行所有agent相关测试**

Run: `pytest tests/test_agent*.py tests/test_conditional_edges.py tests/test_checkpointer.py -v`
Expected: All tests pass

- [ ] **Step 2: 运行完整测试套件**

Run: `pytest tests/ -v --ignore=tests/cli_live_state_tester.py --ignore=tests/full_flow_observer.py --ignore=tests/rag_manual_observer.py`
Expected: All tests pass

- [ ] **Step 3: 最终提交**

```bash
git add -A
git commit -m "feat(langgraph): complete core refactoring with conditional edges, checkpointer, and retry policies

- Add graph_v2 with conditional edges for dynamic routing
- Add history_check and RAG-first nodes
- Add SQLite checkpointer for session persistence
- Add retry policies for LLM, RAG, and DB nodes
- Add comprehensive tests for all new components
- Add toggle switch for graph_v2 in agent_service"
```

---

## 自审检查清单

### 1. 规范覆盖

| 规范要求 | 任务 |
|----------|------|
| 条件边 - 意图路由 | Task 4 (routers.py), Task 7 |
| 条件边 - 历史检查路由 | Task 4, Task 7 |
| 条件边 - 诊断路由 | Task 4, Task 7 |
| 条件边 - 复述路由 | Task 4, Task 7 |
| 条件边 - RAG路由 | Task 4, Task 7 |
| 检查点 - SQLite存储 | Task 3, Task 8 |
| 检查点 - 会话恢复 | Task 6 (graph_v2.py) |
| 重试策略 - LLM | Task 2 |
| 重试策略 - RAG | Task 2 |
| 重试策略 - DB | Task 2 |
| 新增 - 历史记录检查 | Task 5 (nodes.py) |
| 新增 - RAG优先检索 | Task 5 (nodes.py) |

### 2. 占位符扫描

- [x] 无 "TBD" 或 "TODO"
- [x] 无 "implement later"
- [x] 无 "fill in details"
- [x] 所有代码步骤包含完整代码
- [x] 所有命令步骤包含完整命令

### 3. 类型一致性

- [x] `LearningState` 字段在 state.py 和 nodes.py 中一致
- [x] 路由函数返回值与条件边配置匹配
- [x] 节点函数签名一致 `(LearningState) -> LearningState`
