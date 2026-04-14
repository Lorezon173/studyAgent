# Agent设计改进方案

**文档版本**: v1.0
**创建日期**: 2026-04-15
**关联文档**: [Agent_report.md](./Agent_report.md)

---

## 目录

1. [改进总览](#一改进总览)
2. [LangGraph核心特性应用](#二langgraph核心特性应用)
3. [图结构重构方案](#三图结构重构方案)
4. [决策机制优化](#四决策机制优化)
5. [容错与冗余设计](#五容错与冗余设计)
6. [可观测性与调试](#六可观测性与调试)
7. [评估框架设计](#七评估框架设计)
8. [测试体系完善](#八测试体系完善)
9. [实施路线图](#九实施路线图)

---

## 一、改进总览

### 1.1 改进目标

| 目标 | 描述 | 关键指标 |
|------|------|----------|
| 充分利用LangGraph | 使用条件边、检查点、重试策略 | 特性使用率 > 80% |
| 增强决策能力 | 动态路由、自适应策略 | 决策准确率 > 90% |
| 完善容错机制 | 节点级容错、降级策略 | 故障恢复率 > 95% |
| 建立可观测性 | 全链路追踪、效果评估 | 问题定位时间 < 5min |

### 1.2 问题与方案映射

| 问题编号 | 问题 | 解决方案 | 章节 |
|----------|------|----------|------|
| A1 | 条件边未使用 | 引入条件边实现动态路由 | §3.2 |
| A2 | 缺少节点级容错 | RetryPolicy + 降级节点 | §5.2 |
| A3 | 缺少可观测性 | 集成追踪框架 | §6 |
| A4 | 决策逻辑分散 | 决策节点化 | §4.3 |
| A5 | 图结构简化 | 完整图重构 | §3 |
| A6 | 缺少检查点 | Checkpointer集成 | §3.4 |
| A7 | 无降级策略 | 降级节点设计 | §5.3 |
| A8 | 缺少效果评估 | 评估框架 | §7 |
| A9 | 测试覆盖不足 | 测试体系完善 | §8 |

---

## 二、LangGraph核心特性应用

### 2.1 条件边 (Conditional Edges)

**原理**: 根据状态动态决定下一个执行的节点。

**实现方案**:

```python
# app/agent/graph_v2.py

from langgraph.graph import END, StateGraph
from typing import Literal

def route_by_intent(state: LearningState) -> Literal["diagnose", "qa_direct", "replan", "summary"]:
    """根据意图路由到不同节点"""
    intent = state.get("intent", "teach_loop")
    
    if intent == "qa_direct":
        return "qa_direct"
    elif intent == "replan":
        return "replan"
    elif intent == "review":
        return "summary"
    else:
        return "diagnose"


def route_after_diagnosis(state: LearningState) -> Literal["explain", "qa_direct", "END"]:
    """根据诊断结果决定下一步"""
    diagnosis = state.get("diagnosis", "")
    
    # 如果用户已经掌握，直接进入总结
    if "已掌握" in diagnosis or "熟悉" in diagnosis:
        state["skip_explanation"] = True
        return "summary"
    
    # 如果需要外部知识，先进行知识检索
    if "需要补充" in diagnosis:
        return "knowledge_retrieval"
    
    return "explain"


def route_after_restate(state: LearningState) -> Literal["followup", "explain", "summary"]:
    """根据复述评估决定下一步"""
    eval_text = state.get("restatement_eval", "")
    
    # 如果理解程度高，可以跳过追问直接总结
    if "已理解" in eval_text or "准确" in eval_text:
        return "summary"
    
    # 如果有重大误解，需要重新讲解
    if "错误" in eval_text or "混淆" in eval_text:
        state["need_re_explain"] = True
        return "explain"
    
    return "followup"


def build_learning_graph_v2():
    """构建完整的教学图（使用条件边）"""
    graph = StateGraph(LearningState)
    
    # 添加节点
    graph.add_node("intent_router", intent_router_node)
    graph.add_node("diagnose", diagnose_node)
    graph.add_node("explain", explain_node)
    graph.add_node("restate_check", restate_check_node)
    graph.add_node("followup", followup_node)
    graph.add_node("summary", summarize_node)
    graph.add_node("qa_direct", qa_direct_node)
    graph.add_node("replan", replan_node)
    graph.add_node("knowledge_retrieval", knowledge_retrieval_node)
    
    # 设置入口
    graph.set_entry_point("intent_router")
    
    # 条件边：意图路由
    graph.add_conditional_edges(
        "intent_router",
        route_by_intent,
        {
            "diagnose": "diagnose",
            "qa_direct": "qa_direct",
            "replan": "replan",
            "summary": "summary",
        }
    )
    
    # 条件边：诊断后路由
    graph.add_conditional_edges(
        "diagnose",
        route_after_diagnosis,
        {
            "explain": "explain",
            "knowledge_retrieval": "knowledge_retrieval",
            "summary": "summary",
        }
    )
    
    # 条件边：复述后路由
    graph.add_conditional_edges(
        "restate_check",
        route_after_restate,
        {
            "followup": "followup",
            "explain": "explain",  # 循环回讲解
            "summary": "summary",
        }
    )
    
    # 固定边
    graph.add_edge("explain", "restate_check")
    graph.add_edge("knowledge_retrieval", "explain")
    graph.add_edge("followup", "summary")
    graph.add_edge("summary", END)
    graph.add_edge("qa_direct", END)
    graph.add_edge("replan", END)
    
    return graph.compile()
```

### 2.2 检查点 (Checkpointer)

**原理**: 持久化图执行状态，支持断点续传和回放。

**实现方案**:

```python
# app/agent/checkpointer.py

from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.sqlite import SqliteSaver
from typing import Optional
from app.core.config import settings

def get_checkpointer():
    """获取检查点存储器"""
    if settings.session_store_backend.lower() == "sqlite":
        return SqliteSaver.from_conn_string(settings.session_sqlite_path)
    return MemorySaver()


# app/agent/graph_v2.py

from app.agent.checkpointer import get_checkpointer

def build_learning_graph_v2():
    """构建带检查点的图"""
    graph = StateGraph(LearningState)
    # ... 节点和边定义 ...
    
    checkpointer = get_checkpointer()
    return graph.compile(checkpointer=checkpointer)


# 使用示例：恢复会话
def resume_session(session_id: str, thread_id: str):
    """恢复会话执行"""
    graph = build_learning_graph_v2()
    
    # 获取当前状态
    current_state = graph.get_state({"configurable": {"thread_id": thread_id}})
    
    if current_state:
        # 继续执行
        result = graph.invoke(
            current_state.values,
            config={"configurable": {"thread_id": thread_id}}
        )
        return result
    
    return None


# 使用示例：回放执行
def replay_execution(session_id: str, thread_id: str):
    """回放整个执行过程"""
    graph = build_learning_graph_v2()
    
    # 获取所有状态历史
    history = list(graph.get_state_history({"configurable": {"thread_id": thread_id}}))
    
    for idx, state in enumerate(history):
        print(f"Step {idx}: {state.values.get('stage')}")
    
    return history
```

### 2.3 重试策略 (Retry Policy)

**原理**: 为节点配置自动重试机制。

**实现方案**:

```python
# app/agent/retry_policy.py

from langgraph.pregel import RetryPolicy

# 默认重试策略
DEFAULT_RETRY = RetryPolicy(
    max_attempts=3,
    initial_interval=1.0,
    backoff_factor=2.0,
    jitter=True,
    retry_on=[ConnectionError, TimeoutError],
)

# LLM调用重试策略
LLM_RETRY = RetryPolicy(
    max_attempts=3,
    initial_interval=2.0,
    backoff_factor=2.0,
    jitter=True,
    retry_on=[Exception],  # LLM调用可能抛出各种异常
)


# app/agent/graph_v2.py

def build_learning_graph_v2():
    graph = StateGraph(LearningState)
    
    # 为LLM节点配置重试策略
    graph.add_node("diagnose", diagnose_node, retry=LLM_RETRY)
    graph.add_node("explain", explain_node, retry=LLM_RETRY)
    graph.add_node("restate_check", restate_check_node, retry=LLM_RETRY)
    graph.add_node("followup", followup_node, retry=LLM_RETRY)
    graph.add_node("summary", summarize_node, retry=LLM_RETRY)
    
    # ... 其他配置 ...
    return graph.compile()
```

### 2.4 人工介入 (Human-in-the-Loop)

**原理**: 在关键节点暂停执行，等待人工确认。

**实现方案**:

```python
# app/agent/graph_v2.py

def build_learning_graph_with_human_loop():
    """构建支持人工介入的图"""
    graph = StateGraph(LearningState)
    
    # 添加需要人工确认的节点
    graph.add_node("diagnose", diagnose_node)
    graph.add_node("human_confirm", human_confirm_node)
    graph.add_node("explain", explain_node)
    
    graph.set_entry_point("diagnose")
    graph.add_edge("diagnose", "human_confirm")
    graph.add_edge("human_confirm", "explain")
    
    # 编译时指定中断点
    checkpointer = get_checkpointer()
    return graph.compile(
        checkpointer=checkpointer,
        interrupt_before=["human_confirm"],  # 执行前暂停
    )


def human_confirm_node(state: LearningState) -> LearningState:
    """人工确认节点（被中断时不会执行）"""
    # 这个节点的逻辑是：当用户确认后，更新状态
    state["human_confirmed"] = True
    return state


# 使用示例
def run_with_human_confirm(thread_id: str, user_input: str):
    """运行并等待人工确认"""
    graph = build_learning_graph_with_human_loop()
    
    # 第一次调用：执行到human_confirm前暂停
    result = graph.invoke(
        {"user_input": user_input},
        config={"configurable": {"thread_id": thread_id}}
    )
    
    # 检查是否需要确认
    state = graph.get_state({"configurable": {"thread_id": thread_id}})
    if state.values.get("stage") == "diagnosed":
        # 等待用户确认
        user_approved = ask_user_approval(state.values.get("diagnosis"))
        
        if user_approved:
            # 更新状态并继续执行
            graph.update_state(
                {"configurable": {"thread_id": thread_id}},
                {"human_confirmed": True}
            )
            # 继续执行
            result = graph.invoke(None, config={"configurable": {"thread_id": thread_id}})
    
    return result
```

---

## 三、图结构重构方案

### 3.1 新图架构设计

```
                    ┌─────────────────┐
                    │  intent_router  │
                    └────────┬────────┘
                             │
           ┌─────────────────┼─────────────────┐
           │                 │                 │
           ▼                 ▼                 ▼
    ┌──────────┐      ┌──────────┐      ┌──────────┐
    │ diagnose │      │qa_direct │      │ replan   │
    └────┬─────┘      └────┬─────┘      └────┬─────┘
         │                 │                 │
    ┌────┴────┐            │                 │
    │         │            │                 │
    ▼         ▼            ▼                 ▼
┌───────┐ ┌───────┐      END               END
│explain│ │summary│
└───┬───┘ └───┬───┘
    │         │
    ▼         │
┌────────────┐│
│restate_check││
└─────┬──────┘│
      │       │
  ┌───┴───┐   │
  │       │   │
  ▼       ▼   │
┌─────┐ ┌────┴┐
│followup│explain│ ← 循环
└───┬──┘└─────┘
    │
    ▼
┌───────┐
│summary│
└───┬───┘
    │
    ▼
   END
```

### 3.2 完整图定义

**新建文件**: `app/agent/graph_v2.py`

```python
"""
学习Agent图定义 V2
充分利用LangGraph特性：条件边、检查点、重试策略
"""
from langgraph.graph import END, StateGraph
from langgraph.pregel import RetryPolicy
from typing import Literal

from app.agent.state import LearningState
from app.agent.nodes import (
    intent_router_node,
    diagnose_node,
    explain_node,
    restate_check_node,
    followup_node,
    summarize_node,
    qa_direct_node,
    replan_node,
    knowledge_retrieval_node,
    fallback_node,
)
from app.agent.routers import (
    route_by_intent,
    route_after_diagnosis,
    route_after_restate,
)
from app.agent.checkpointer import get_checkpointer
from app.agent.retry_policy import LLM_RETRY, DEFAULT_RETRY


def build_learning_graph():
    """构建完整的学习Agent图"""
    graph = StateGraph(LearningState)
    
    # ===== 添加节点 =====
    
    # 路由节点
    graph.add_node("intent_router", intent_router_node)
    
    # 核心教学节点
    graph.add_node("diagnose", diagnose_node, retry=LLM_RETRY)
    graph.add_node("explain", explain_node, retry=LLM_RETRY)
    graph.add_node("restate_check", restate_check_node, retry=LLM_RETRY)
    graph.add_node("followup", followup_node, retry=LLM_RETRY)
    graph.add_node("summary", summarize_node, retry=LLM_RETRY)
    
    # 辅助节点
    graph.add_node("qa_direct", qa_direct_node, retry=LLM_RETRY)
    graph.add_node("replan", replan_node, retry=LLM_RETRY)
    graph.add_node("knowledge_retrieval", knowledge_retrieval_node, retry=DEFAULT_RETRY)
    graph.add_node("fallback", fallback_node)  # 降级节点
    
    # ===== 设置入口 =====
    graph.set_entry_point("intent_router")
    
    # ===== 条件边 =====
    
    # 意图路由
    graph.add_conditional_edges(
        "intent_router",
        route_by_intent,
        {
            "diagnose": "diagnose",
            "qa_direct": "qa_direct",
            "replan": "replan",
            "summary": "summary",
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
            "fallback": "fallback",
        }
    )
    
    # 复述后路由
    graph.add_conditional_edges(
        "restate_check",
        route_after_restate,
        {
            "followup": "followup",
            "explain": "explain",  # 循环讲解
            "summary": "summary",
        }
    )
    
    # ===== 固定边 =====
    graph.add_edge("knowledge_retrieval", "explain")
    graph.add_edge("explain", "restate_check")
    graph.add_edge("followup", "summary")
    graph.add_edge("summary", END)
    graph.add_edge("qa_direct", END)
    graph.add_edge("replan", END)
    graph.add_edge("fallback", END)
    
    # ===== 编译图 =====
    checkpointer = get_checkpointer()
    return graph.compile(
        checkpointer=checkpointer,
        # 可选：在特定节点前中断等待人工确认
        # interrupt_before=["summary"],
    )


# 单例
_learning_graph = None

def get_learning_graph():
    """获取学习图单例"""
    global _learning_graph
    if _learning_graph is None:
        _learning_graph = build_learning_graph()
    return _learning_graph
```

### 3.3 节点定义重构

**新建文件**: `app/agent/nodes.py`

```python
"""
Agent节点定义
每个节点专注于单一职责，支持容错和降级
"""
from typing import Any
from app.agent.state import LearningState
from app.services.llm import llm_service
from app.core.prompts import (
    DIAGNOSE_PROMPT,
    EXPLAIN_PROMPT,
    RESTATE_CHECK_PROMPT,
    FOLLOWUP_PROMPT,
    SUMMARY_PROMPT,
)


def intent_router_node(state: LearningState) -> LearningState:
    """意图路由节点：识别用户意图"""
    user_input = state.get("user_input", "")
    
    try:
        raw = llm_service.route_intent(user_input)
        import json
        data = json.loads(raw)
        intent = str(data.get("intent", "teach_loop")).strip()
        confidence = float(data.get("confidence", 0.0))
        reason = str(data.get("reason", ""))
        
        # 验证意图有效性
        valid_intents = {"teach_loop", "qa_direct", "review", "replan"}
        if intent not in valid_intents:
            intent = "teach_loop"  # 默认进入教学循环
        
        state["intent"] = intent
        state["intent_confidence"] = confidence
        state["intent_reason"] = reason
        
    except Exception as e:
        # 降级：使用规则路由
        state["intent"] = _rule_based_route(user_input)
        state["intent_confidence"] = 0.7
        state["intent_reason"] = f"LLM路由失败，使用规则回退: {str(e)}"
    
    # 记录到追踪
    _append_trace(state, "intent_router", {
        "intent": state.get("intent"),
        "confidence": state.get("intent_confidence"),
    })
    
    return state


def diagnose_node(state: LearningState) -> LearningState:
    """诊断节点：识别用户先验知识水平"""
    topic = state.get("topic") or "未指定主题"
    user_input = state.get("user_input", "")
    topic_context = state.get("topic_context", "")
    
    prompt = DIAGNOSE_PROMPT.format(
        topic=topic,
        user_input=user_input,
        topic_context=topic_context
    )
    
    diagnosis = llm_service.invoke(
        system_prompt="你是严谨的学习诊断助手。",
        user_prompt=prompt,
    )
    
    state["diagnosis"] = diagnosis
    state["stage"] = "diagnosed"
    
    _append_trace(state, "diagnose", {"diagnosis_length": len(diagnosis)})
    
    return state


def explain_node(state: LearningState) -> LearningState:
    """讲解节点：用费曼法解释概念"""
    topic = state.get("topic") or "未指定主题"
    user_input = state.get("user_input", "")
    topic_context = state.get("topic_context", "")
    
    prompt = EXPLAIN_PROMPT.format(
        topic=topic,
        user_input=user_input,
        topic_context=topic_context
    )
    
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
    """复述检测节点：检验用户理解深度"""
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
    """追问节点：基于漏洞进行针对性追问"""
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
    """总结节点：输出学习成果和复习建议"""
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


def qa_direct_node(state: LearningState) -> LearningState:
    """直接问答节点"""
    current_stage = state.get("stage") or "start"
    
    reply = llm_service.answer_direct(
        user_input=state.get("user_input", ""),
        topic=state.get("topic"),
        comparison_mode=bool(state.get("comparison_mode", False)),
        stream_output=bool(state.get("stream_output", False)),
    )
    
    state["reply"] = reply
    # 保持原阶段
    state["stage"] = current_stage
    
    _append_trace(state, "qa_direct", {"reply_length": len(reply)})
    
    return state


def replan_node(state: LearningState) -> LearningState:
    """重规划节点"""
    user_input = state.get("user_input", "")
    topic = state.get("topic")
    
    # 更新计划
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


def knowledge_retrieval_node(state: LearningState) -> LearningState:
    """知识检索节点：在需要时补充知识"""
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


def fallback_node(state: LearningState) -> LearningState:
    """降级节点：当其他节点失败时提供兜底响应"""
    state["reply"] = (
        "抱歉，处理您的请求时遇到了问题。\n"
        "请尝试重新描述您的问题，或稍后再试。"
    )
    state["stage"] = "fallback"
    
    _append_trace(state, "fallback", {"reason": "Node execution failed"})
    
    return state


# ===== 辅助函数 =====

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


def _append_trace(state: LearningState, phase: str, data: dict) -> None:
    """追加执行追踪"""
    traces = state.get("branch_trace", [])
    traces.append({
        "phase": phase,
        "timestamp": _get_timestamp(),
        **data
    })
    state["branch_trace"] = traces


def _get_timestamp() -> str:
    from datetime import datetime, UTC
    return datetime.now(UTC).isoformat()
```

### 3.4 路由函数定义

**新建文件**: `app/agent/routers.py`

```python
"""
图路由函数
定义条件边的路由逻辑
"""
from typing import Literal
from app.agent.state import LearningState


def route_by_intent(state: LearningState) -> Literal["diagnose", "qa_direct", "replan", "summary"]:
    """根据意图路由"""
    intent = state.get("intent", "teach_loop")
    
    route_map = {
        "qa_direct": "qa_direct",
        "replan": "replan",
        "review": "summary",
        "teach_loop": "diagnose",
    }
    
    return route_map.get(intent, "diagnose")


def route_after_diagnosis(state: LearningState) -> Literal["explain", "knowledge_retrieval", "summary", "fallback"]:
    """诊断后的路由决策"""
    diagnosis = state.get("diagnosis", "")
    error = state.get("node_error")
    
    # 如果有错误，走降级路径
    if error:
        return "fallback"
    
    # 如果用户已经掌握，跳过讲解
    if any(k in diagnosis for k in ["已掌握", "熟悉", "理解充分"]):
        return "summary"
    
    # 如果需要外部知识
    if any(k in diagnosis for k in ["需要补充", "缺少资料", "建议参考"]):
        return "knowledge_retrieval"
    
    return "explain"


def route_after_restate(state: LearningState) -> Literal["followup", "explain", "summary"]:
    """复述评估后的路由决策"""
    eval_text = state.get("restatement_eval", "")
    loop_count = state.get("explain_loop_count", 0)
    
    # 防止无限循环
    if loop_count >= 3:
        return "summary"
    
    # 理解程度高，直接总结
    if any(k in eval_text for k in ["已理解", "准确", "完整", "正确"]):
        return "summary"
    
    # 有重大误解，重新讲解
    if any(k in eval_text for k in ["错误", "混淆", "误解", "不清楚"]):
        state["explain_loop_count"] = loop_count + 1
        return "explain"
    
    return "followup"
```

---

## 四、决策机制优化

### 4.1 决策节点化

将分散的决策逻辑封装为图的节点，提高可追溯性。

```python
# app/agent/decision_nodes.py

def topic_detection_node(state: LearningState) -> LearningState:
    """主题检测节点"""
    user_input = state.get("user_input", "")
    current_topic = state.get("topic")
    
    try:
        raw = llm_service.detect_topic(user_input, current_topic)
        data = json.loads(raw)
        
        topic = data.get("topic")
        changed = bool(data.get("changed", False))
        confidence = float(data.get("confidence", 0.0))
        reason = str(data.get("reason", ""))
        comparison_mode = bool(data.get("comparison_mode", False))
        
        state["topic_confidence"] = confidence
        state["topic_changed"] = changed
        state["topic_reason"] = reason
        state["comparison_mode"] = comparison_mode
        
        if topic and topic != current_topic:
            state["topic"] = topic
            
    except Exception as e:
        state["topic_confidence"] = 0.0
        state["topic_reason"] = f"检测失败: {str(e)}"
    
    return state


def tool_selection_node(state: LearningState) -> LearningState:
    """工具选择节点"""
    from app.services.agent_runtime import route_tool
    
    user_input = state.get("user_input", "")
    user_id = state.get("user_id")
    
    tool_route = route_tool(user_input, user_id=user_id)
    
    state["tool_route"] = {
        "tool": tool_route.tool,
        "confidence": tool_route.confidence,
        "reason": tool_route.reason,
        "candidates": tool_route.candidates,
    }
    
    return state
```

### 4.2 决策审计日志

```python
# app/agent/audit.py

class DecisionAudit:
    """决策审计日志"""
    
    @staticmethod
    def log(state: LearningState, decision_type: str, details: dict) -> None:
        """记录决策日志"""
        audit_entry = {
            "timestamp": datetime.now(UTC).isoformat(),
            "session_id": state.get("session_id"),
            "decision_type": decision_type,
            "details": details,
            "state_snapshot": {
                "stage": state.get("stage"),
                "topic": state.get("topic"),
                "intent": state.get("intent"),
            }
        }
        
        # 追加到审计日志
        audit_log = state.get("audit_log", [])
        audit_log.append(audit_entry)
        state["audit_log"] = audit_log
        
        # 可选：持久化到数据库
        _persist_audit(audit_entry)


# 在决策节点中使用
def intent_router_node(state: LearningState) -> LearningState:
    # ... 决策逻辑 ...
    
    DecisionAudit.log(state, "intent_routing", {
        "intent": intent,
        "confidence": confidence,
        "reason": reason,
        "method": "llm" if not fallback else "rule",
    })
    
    return state
```

---

## 五、容错与冗余设计

### 5.1 节点级容错

```python
# app/agent/fault_tolerance.py

from functools import wraps
from typing import Callable, Any

def with_fallback(fallback_func: Callable[[LearningState], LearningState]):
    """节点容错装饰器"""
    def decorator(node_func: Callable[[LearningState], LearningState]):
        @wraps(node_func)
        def wrapper(state: LearningState) -> LearningState:
            try:
                return node_func(state)
            except Exception as e:
                # 记录错误
                state["node_error"] = str(e)
                state["error_node"] = node_func.__name__
                
                # 调用降级函数
                return fallback_func(state)
        return wrapper
    return decorator


# 使用示例
@with_fallback(fallback_node)
def diagnose_node(state: LearningState) -> LearningState:
    # ... 正常逻辑 ...
    pass
```

### 5.2 降级策略矩阵

| 节点 | 主要策略 | 降级策略 | 完全失败 |
|------|----------|----------|----------|
| intent_router | LLM路由 | 规则路由 | 默认teach_loop |
| diagnose | LLM诊断 | 简化诊断模板 | 跳过诊断 |
| explain | LLM讲解 | 知识库检索 | 通用模板 |
| restate_check | LLM评估 | 关键词检测 | 跳过评估 |
| summary | LLM总结 | 模板总结 | 简单结束 |

```python
# app/agent/fallbacks.py

def diagnose_fallback(state: LearningState) -> LearningState:
    """诊断节点降级策略"""
    state["diagnosis"] = "诊断服务暂时不可用，将使用通用教学策略。"
    state["stage"] = "diagnosed"
    return state


def explain_fallback(state: LearningState) -> LearningState:
    """讲解节点降级策略"""
    topic = state.get("topic", "该主题")
    
    # 尝试从知识库检索
    from app.services.rag_service import rag_service
    results = rag_service.retrieve(
        query=f"{topic} 定义 概念",
        topic=topic,
        top_k=1,
    )
    
    if results:
        state["explanation"] = results[0].get("text", "")
    else:
        state["explanation"] = f"关于{topic}，请参考相关教材或资料进行学习。"
    
    state["stage"] = "explained"
    return state


def summary_fallback(state: LearningState) -> LearningState:
    """总结节点降级策略"""
    topic = state.get("topic", "学习内容")
    
    state["summary"] = (
        f"本次学习了{topic}。\n"
        "建议后续继续巩固相关知识点。"
    )
    state["stage"] = "summarized"
    return state
```

### 5.3 熔断机制

```python
# app/agent/circuit_breaker.py

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict

@dataclass
class CircuitState:
    """熔断器状态"""
    failure_count: int = 0
    last_failure: datetime | None = None
    state: str = "closed"  # closed, open, half_open


class CircuitBreaker:
    """节点熔断器"""
    
    def __init__(
        self,
        failure_threshold: int = 3,
        recovery_timeout: int = 60,
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = timedelta(seconds=recovery_timeout)
        self.circuits: Dict[str, CircuitState] = {}
    
    def is_available(self, node_name: str) -> bool:
        """检查节点是否可用"""
        circuit = self.circuits.get(node_name, CircuitState())
        
        if circuit.state == "open":
            # 检查是否可以尝试恢复
            if circuit.last_failure:
                if datetime.now() - circuit.last_failure > self.recovery_timeout:
                    # 进入半开状态
                    circuit.state = "half_open"
                    self.circuits[node_name] = circuit
                    return True
            return False
        
        return True
    
    def record_success(self, node_name: str) -> None:
        """记录成功"""
        circuit = self.circuits.get(node_name, CircuitState())
        circuit.failure_count = 0
        circuit.state = "closed"
        self.circuits[node_name] = circuit
    
    def record_failure(self, node_name: str) -> None:
        """记录失败"""
        circuit = self.circuits.get(node_name, CircuitState())
        circuit.failure_count += 1
        circuit.last_failure = datetime.now()
        
        if circuit.failure_count >= self.failure_threshold:
            circuit.state = "open"
        
        self.circuits[node_name] = circuit


# 全局熔断器
circuit_breaker = CircuitBreaker()


# 使用示例
def diagnose_node(state: LearningState) -> LearningState:
    node_name = "diagnose"
    
    if not circuit_breaker.is_available(node_name):
        # 熔断器打开，使用降级
        return diagnose_fallback(state)
    
    try:
        # 正常执行
        result = _do_diagnose(state)
        circuit_breaker.record_success(node_name)
        return result
    except Exception as e:
        circuit_breaker.record_failure(node_name)
        raise
```

---

## 六、可观测性与调试

### 6.1 执行追踪

```python
# app/agent/tracing.py

from dataclasses import dataclass, field
from datetime import datetime, UTC
from typing import Any
import json

@dataclass
class Span:
    """执行跨度"""
    name: str
    start_time: datetime
    end_time: datetime | None = None
    attributes: dict = field(default_factory=dict)
    events: list = field(default_factory=list)
    
    def end(self) -> None:
        self.end_time = datetime.now(UTC)
    
    @property
    def duration_ms(self) -> float:
        if self.end_time:
            delta = self.end_time - self.start_time
            return delta.total_seconds() * 1000
        return 0.0


class ExecutionTracer:
    """执行追踪器"""
    
    def __init__(self):
        self.spans: list[Span] = []
        self.current_span: Span | None = None
    
    def start_span(self, name: str, attributes: dict = None) -> Span:
        """开始一个跨度"""
        span = Span(
            name=name,
            start_time=datetime.now(UTC),
            attributes=attributes or {},
        )
        self.spans.append(span)
        return span
    
    def add_event(self, name: str, attributes: dict = None) -> None:
        """添加事件"""
        if self.current_span:
            self.current_span.events.append({
                "name": name,
                "timestamp": datetime.now(UTC).isoformat(),
                "attributes": attributes or {},
            })
    
    def export(self) -> dict:
        """导出追踪数据"""
        return {
            "spans": [
                {
                    "name": s.name,
                    "start_time": s.start_time.isoformat(),
                    "end_time": s.end_time.isoformat() if s.end_time else None,
                    "duration_ms": s.duration_ms,
                    "attributes": s.attributes,
                    "events": s.events,
                }
                for s in self.spans
            ]
        }


# 节点追踪装饰器
def traced(node_func):
    """节点追踪装饰器"""
    @wraps(node_func)
    def wrapper(state: LearningState) -> LearningState:
        tracer = state.get("_tracer") or ExecutionTracer()
        state["_tracer"] = tracer
        
        span = tracer.start_span(
            name=node_func.__name__,
            attributes={"input_stage": state.get("stage")}
        )
        
        try:
            result = node_func(state)
            span.attributes["output_stage"] = result.get("stage")
            span.attributes["success"] = True
            return result
        except Exception as e:
            span.attributes["success"] = False
            span.attributes["error"] = str(e)
            raise
        finally:
            span.end()
    
    return wrapper
```

### 6.2 LangSmith集成

```python
# app/agent/langsmith_integration.py

from langsmith import Client
from app.core.config import settings

def setup_langsmith():
    """配置LangSmith追踪"""
    import os
    
    if settings.langsmith_api_key:
        os.environ["LANGSMITH_API_KEY"] = settings.langsmith_api_key
        os.environ["LANGSMITH_TRACING"] = "true"
        os.environ["LANGSMITH_PROJECT"] = settings.langsmith_project or "study-agent"
        
        return Client()
    
    return None


# 在图编译时启用追踪
def build_learning_graph():
    # ... 图定义 ...
    
    client = setup_langsmith()
    
    if client:
        # LangSmith会自动追踪LangGraph执行
        pass
    
    return graph.compile(checkpointer=checkpointer)
```

### 6.3 图可视化

```python
# app/agent/visualization.py

def visualize_graph(graph, output_path: str = "graph.png"):
    """可视化图结构"""
    try:
        from IPython.display import Image, display
        
        # 获取图的Mermaid表示
        mermaid = graph.get_graph().draw_mermaid()
        
        # 保存为图片
        with open(output_path.replace('.png', '.mmd'), 'w') as f:
            f.write(mermaid)
        
        print(f"Graph saved to {output_path}")
        print(mermaid)
        
    except ImportError:
        print("IPython not available, skipping visualization")


# 使用
if __name__ == "__main__":
    graph = build_learning_graph()
    visualize_graph(graph)
```

---

## 七、评估框架设计

### 7.1 评估指标体系

| 维度 | 指标 | 计算方式 | 目标值 |
|------|------|----------|--------|
| 教学效果 | 知识掌握率 | 总结评估分数 | > 70% |
| 交互质量 | 用户满意度 | 反馈评分 | > 4.0/5 |
| 系统性能 | 响应延迟 | 节点执行时间 | < 3s |
| 容错能力 | 故障恢复率 | 降级成功/总故障 | > 95% |
| 决策准确性 | 意图识别率 | 正确意图/总意图 | > 90% |

### 7.2 评估器实现

**新建文件**: `app/evaluation/agent_evaluator.py`

```python
"""
Agent评估框架
"""

from dataclasses import dataclass
from typing import Any
import json

@dataclass
class EvaluationResult:
    """评估结果"""
    session_id: str
    metrics: dict[str, float]
    details: dict[str, Any]
    passed: bool
    score: float


class AgentEvaluator:
    """Agent评估器"""
    
    def __init__(self):
        self.evaluators = {
            "teaching_effectiveness": self._evaluate_teaching,
            "interaction_quality": self._evaluate_interaction,
            "decision_accuracy": self._evaluate_decisions,
            "system_performance": self._evaluate_performance,
        }
    
    def evaluate(self, state: dict, history: list[dict]) -> EvaluationResult:
        """综合评估"""
        metrics = {}
        details = {}
        
        for name, evaluator in self.evaluators.items():
            try:
                score, detail = evaluator(state, history)
                metrics[name] = score
                details[name] = detail
            except Exception as e:
                metrics[name] = 0.0
                details[name] = {"error": str(e)}
        
        # 计算综合分数
        weights = {
            "teaching_effectiveness": 0.35,
            "interaction_quality": 0.25,
            "decision_accuracy": 0.25,
            "system_performance": 0.15,
        }
        
        total_score = sum(
            metrics.get(name, 0) * weight
            for name, weight in weights.items()
        )
        
        # 判断是否通过
        passed = total_score >= 0.7
        
        return EvaluationResult(
            session_id=state.get("session_id", ""),
            metrics=metrics,
            details=details,
            passed=passed,
            score=total_score,
        )
    
    def _evaluate_teaching(self, state: dict, history: list) -> tuple[float, dict]:
        """评估教学效果"""
        mastery_score = state.get("mastery_score", 0)
        
        # 基于掌握度评分
        score = mastery_score / 100.0
        
        # 考虑讲解循环次数（过多说明效果不好）
        loop_count = state.get("explain_loop_count", 0)
        loop_penalty = min(loop_count * 0.1, 0.3)
        
        final_score = max(0, score - loop_penalty)
        
        details = {
            "mastery_score": mastery_score,
            "loop_count": loop_count,
            "loop_penalty": loop_penalty,
        }
        
        return final_score, details
    
    def _evaluate_interaction(self, state: dict, history: list) -> tuple[float, dict]:
        """评估交互质量"""
        # 基于历史记录分析
        user_messages = [h for h in history if h.startswith("用户:")]
        assistant_messages = [h for h in history if h.startswith("助手:")]
        
        # 交互轮次
        turn_count = len(user_messages)
        
        # 交互质量评分
        if turn_count < 2:
            score = 0.5  # 太少
        elif turn_count > 10:
            score = 0.6  # 太多可能说明效果不好
        else:
            score = 0.8 + min(turn_count - 2, 3) * 0.05
        
        details = {
            "turn_count": turn_count,
            "user_message_count": len(user_messages),
            "assistant_message_count": len(assistant_messages),
        }
        
        return min(score, 1.0), details
    
    def _evaluate_decisions(self, state: dict, history: list) -> tuple[float, dict]:
        """评估决策准确性"""
        branch_trace = state.get("branch_trace", [])
        
        # 统计决策
        decisions = [t for t in branch_trace if t.get("phase") in ["router", "intent_router"]]
        
        if not decisions:
            return 0.7, {"note": "No decisions recorded"}
        
        # 分析决策置信度
        confidences = [d.get("confidence", 0) for d in decisions if "confidence" in d]
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0.5
        
        details = {
            "decision_count": len(decisions),
            "avg_confidence": avg_confidence,
        }
        
        return avg_confidence, details
    
    def _evaluate_performance(self, state: dict, history: list) -> tuple[float, dict]:
        """评估系统性能"""
        branch_trace = state.get("branch_trace", [])
        
        # 计算各阶段耗时（如果有timestamp）
        durations = []
        prev_time = None
        
        for trace in branch_trace:
            timestamp = trace.get("timestamp")
            if timestamp and prev_time:
                from datetime import datetime
                try:
                    t1 = datetime.fromisoformat(prev_time)
                    t2 = datetime.fromisoformat(timestamp)
                    duration = (t2 - t1).total_seconds()
                    durations.append(duration)
                except:
                    pass
            prev_time = timestamp
        
        if not durations:
            return 0.8, {"note": "No timing data"}
        
        avg_duration = sum(durations) / len(durations)
        
        # 性能评分：平均每个节点执行时间
        if avg_duration < 1:
            score = 1.0
        elif avg_duration < 3:
            score = 0.8
        elif avg_duration < 5:
            score = 0.6
        else:
            score = 0.4
        
        details = {
            "avg_duration_seconds": avg_duration,
            "total_duration_seconds": sum(durations),
            "node_count": len(durations),
        }
        
        return score, details


# 评估报告生成
def generate_evaluation_report(result: EvaluationResult) -> str:
    """生成评估报告"""
    report = f"""
# Agent评估报告

## 会话信息
- Session ID: {result.session_id}
- 综合评分: {result.score:.2%}
- 评估结果: {'通过' if result.passed else '未通过'}

## 指标详情

| 指标 | 得分 | 详情 |
|------|------|------|
| 教学效果 | {result.metrics.get('teaching_effectiveness', 0):.2%} | {result.details.get('teaching_effectiveness', {})} |
| 交互质量 | {result.metrics.get('interaction_quality', 0):.2%} | {result.details.get('interaction_quality', {})} |
| 决策准确性 | {result.metrics.get('decision_accuracy', 0):.2%} | {result.details.get('decision_accuracy', {})} |
| 系统性能 | {result.metrics.get('system_performance', 0):.2%} | {result.details.get('system_performance', {})} |
"""
    return report
```

### 7.3 A/B测试框架

```python
# app/evaluation/ab_test.py

from dataclasses import dataclass
from typing import Literal
import random

@dataclass
class ABTestConfig:
    """A/B测试配置"""
    test_name: str
    variants: dict[str, float]  # variant_name -> traffic_ratio
    metrics: list[str]


class ABTestFramework:
    """A/B测试框架"""
    
    def __init__(self):
        self.tests: dict[str, ABTestConfig] = {}
        self.results: dict[str, dict] = {}
    
    def register_test(self, config: ABTestConfig) -> None:
        """注册测试"""
        self.tests[config.test_name] = config
        self.results[config.test_name] = {v: [] for v in config.variants}
    
    def assign_variant(self, test_name: str, user_id: str) -> str:
        """分配变体"""
        config = self.tests.get(test_name)
        if not config:
            return "control"
        
        # 基于用户ID的一致性哈希
        hash_val = hash(f"{test_name}:{user_id}") % 100
        cumulative = 0
        
        for variant, ratio in config.variants.items():
            cumulative += ratio * 100
            if hash_val < cumulative:
                return variant
        
        return "control"
    
    def record_result(
        self,
        test_name: str,
        variant: str,
        metrics: dict[str, float],
    ) -> None:
        """记录结果"""
        if test_name in self.results:
            self.results[test_name][variant].append(metrics)
    
    def analyze(self, test_name: str) -> dict:
        """分析测试结果"""
        if test_name not in self.results:
            return {}
        
        test_results = self.results[test_name]
        config = self.tests[test_name]
        
        analysis = {}
        for variant, data in test_results.items():
            if not data:
                continue
            
            for metric in config.metrics:
                values = [d.get(metric, 0) for d in data]
                avg = sum(values) / len(values) if values else 0
                
                key = f"{variant}.{metric}"
                analysis[key] = {
                    "mean": avg,
                    "count": len(values),
                    "sum": sum(values),
                }
        
        return analysis
```

---

## 八、测试体系完善

### 8.1 单元测试

**新建文件**: `tests/test_agent_graph.py`

```python
"""
Agent图单元测试
"""
import pytest
from app.agent.graph_v2 import build_learning_graph
from app.agent.state import LearningState


@pytest.fixture
def graph():
    return build_learning_graph()


@pytest.fixture
def initial_state() -> LearningState:
    return {
        "session_id": "test-session",
        "user_input": "我想学习二分查找",
        "topic": "二分查找",
        "stage": "start",
        "history": [],
        "branch_trace": [],
    }


class TestIntentRouter:
    """意图路由测试"""
    
    def test_route_to_teach_loop(self, graph, initial_state, monkeypatch):
        """测试正常教学路由"""
        monkeypatch.setattr(
            "app.services.llm.llm_service.route_intent",
            lambda x: '{"intent":"teach_loop","confidence":0.9,"reason":"学习请求"}'
        )
        
        result = graph.invoke(initial_state)
        assert result["intent"] == "teach_loop"
        assert result["stage"] in ["diagnosed", "explained"]
    
    def test_route_to_qa_direct(self, graph, initial_state, monkeypatch):
        """测试直接问答路由"""
        initial_state["user_input"] = "二分查找是什么？请直接回答"
        
        monkeypatch.setattr(
            "app.services.llm.llm_service.route_intent",
            lambda x: '{"intent":"qa_direct","confidence":0.95,"reason":"直接问答"}'
        )
        monkeypatch.setattr(
            "app.services.llm.llm_service.answer_direct",
            lambda **kw: "二分查找是一种在有序数组中查找的算法"
        )
        
        result = graph.invoke(initial_state)
        assert result["intent"] == "qa_direct"
    
    def test_route_fallback_on_invalid_intent(self, graph, initial_state, monkeypatch):
        """测试无效意图的回退"""
        monkeypatch.setattr(
            "app.services.llm.llm_service.route_intent",
            lambda x: '{"intent":"invalid_intent","confidence":0.5}'
        )
        
        result = graph.invoke(initial_state)
        assert result["intent"] == "teach_loop"  # 回退到默认


class TestConditionalEdges:
    """条件边测试"""
    
    def test_skip_explanation_when_mastered(self, graph, monkeypatch):
        """测试已掌握时跳过讲解"""
        state = {
            "session_id": "test",
            "user_input": "我熟悉二分查找",
            "topic": "二分查找",
            "stage": "start",
            "diagnosis": "用户已掌握该知识点",
            "branch_trace": [],
        }
        
        # 模拟诊断结果
        monkeypatch.setattr(
            "app.services.llm.llm_service.invoke",
            lambda **kw: "用户已掌握二分查找的核心概念"
        )
        
        result = graph.invoke(state)
        # 应该跳过讲解直接到总结
        assert result["stage"] == "summarized"
    
    def test_loop_back_to_explain(self, graph, monkeypatch):
        """测试复述失败后循环回讲解"""
        state = {
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
        
        result = graph.invoke(state)
        # 应该循环回讲解
        assert result["explain_loop_count"] >= 1


class TestFaultTolerance:
    """容错测试"""
    
    def test_fallback_on_llm_failure(self, graph, initial_state, monkeypatch):
        """测试LLM失败时的降级"""
        def failing_invoke(**kwargs):
            raise ConnectionError("LLM服务不可用")
        
        monkeypatch.setattr(
            "app.services.llm.llm_service.invoke",
            failing_invoke
        )
        
        result = graph.invoke(initial_state)
        # 应该使用降级策略
        assert "reply" in result
        assert result.get("node_error") or result.get("stage") == "fallback"


class TestCheckpointer:
    """检查点测试"""
    
    def test_state_persistence(self, graph):
        """测试状态持久化"""
        thread_id = "test-thread-1"
        state = {
            "session_id": "persist-test",
            "user_input": "学习排序算法",
            "topic": "排序算法",
            "stage": "start",
        }
        
        # 第一次执行
        result1 = graph.invoke(
            state,
            config={"configurable": {"thread_id": thread_id}}
        )
        
        # 获取保存的状态
        saved_state = graph.get_state(
            {"configurable": {"thread_id": thread_id}}
        )
        
        assert saved_state is not None
        assert saved_state.values.get("stage") in ["diagnosed", "explained", "summarized"]
```

### 8.2 集成测试

```python
# tests/test_agent_integration.py

"""
Agent集成测试
"""
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.services.session_store import clear_all_sessions


client = TestClient(app)


@pytest.fixture(autouse=True)
def cleanup():
    clear_all_sessions()
    yield
    clear_all_sessions()


class TestFullLearningFlow:
    """完整学习流程测试"""
    
    def test_complete_teaching_cycle(self, monkeypatch):
        """测试完整教学周期"""
        # Mock LLM调用
        responses = {
            "diagnose": "用户对二分查找有初步了解",
            "explain": "二分查找是一种在有序数组中...",
            "restate_check": "用户理解较好，抓住了核心概念",
            "followup": "请问二分查找的时间复杂度是多少？",
            "summary": "本次学习了二分查找，掌握了核心概念。",
        }
        
        def mock_invoke(system_prompt, user_prompt, **kw):
            if "诊断" in system_prompt:
                return responses["diagnose"]
            elif "费曼" in system_prompt or "教学" in system_prompt:
                return responses["explain"]
            elif "复述" in system_prompt:
                return responses["restate_check"]
            elif "追问" in system_prompt:
                return responses["followup"]
            else:
                return responses["summary"]
        
        monkeypatch.setattr("app.services.llm.llm_service.invoke", mock_invoke)
        monkeypatch.setattr(
            "app.services.llm.llm_service.route_intent",
            lambda x: '{"intent":"teach_loop","confidence":0.9}'
        )
        monkeypatch.setattr(
            "app.services.llm.llm_service.detect_topic",
            lambda x, y: '{"topic":"二分查找","changed":false,"confidence":0.9}'
        )
        
        session_id = "full-cycle-test"
        
        # 第一轮：开始学习
        resp1 = client.post("/chat", json={
            "session_id": session_id,
            "user_input": "我想学习二分查找",
            "topic": "二分查找",
        })
        assert resp1.status_code == 200
        assert resp1.json()["stage"] == "explained"
        
        # 第二轮：复述理解
        resp2 = client.post("/chat", json={
            "session_id": session_id,
            "user_input": "二分查找就是每次取中间值比较",
        })
        assert resp2.status_code == 200
        
        # 第三轮：回答追问
        resp3 = client.post("/chat", json={
            "session_id": session_id,
            "user_input": "时间复杂度是O(log n)",
        })
        assert resp3.status_code == 200
        assert resp3.json()["stage"] == "summarized"
```

### 8.3 性能测试

```python
# tests/test_agent_performance.py

"""
Agent性能测试
"""
import pytest
import time
from app.agent.graph_v2 import build_learning_graph


class TestPerformance:
    """性能基准测试"""
    
    @pytest.mark.benchmark
    def test_single_turn_latency(self, benchmark, monkeypatch):
        """测试单轮响应延迟"""
        monkeypatch.setattr(
            "app.services.llm.llm_service.invoke",
            lambda **kw: "mock response"
        )
        monkeypatch.setattr(
            "app.services.llm.llm_service.route_intent",
            lambda x: '{"intent":"teach_loop"}'
        )
        
        graph = build_learning_graph()
        state = {
            "session_id": "perf-test",
            "user_input": "测试问题",
            "topic": "测试",
        }
        
        result = benchmark(graph.invoke, state)
        
        # 断言延迟 < 3秒
        assert benchmark.stats.mean < 3.0
    
    @pytest.mark.benchmark
    def test_throughput(self, benchmark, monkeypatch):
        """测试吞吐量"""
        monkeypatch.setattr(
            "app.services.llm.llm_service.invoke",
            lambda **kw: "mock"
        )
        
        graph = build_learning_graph()
        
        def run_multiple():
            for i in range(10):
                graph.invoke({
                    "session_id": f"throughput-{i}",
                    "user_input": f"问题{i}",
                })
        
        benchmark(run_multiple)
```

---

## 九、实施路线图

### 9.1 阶段一：核心重构 (1-2周)

| 任务 | 文件 | 工作量 |
|------|------|--------|
| 引入条件边 | `graph_v2.py`, `routers.py` | 3天 |
| 节点重构 | `nodes.py` | 2天 |
| 检查点集成 | `checkpointer.py` | 2天 |
| 重试策略 | `retry_policy.py` | 1天 |

### 9.2 阶段二：容错增强 (1周)

| 任务 | 文件 | 工作量 |
|------|------|--------|
| 降级策略 | `fallbacks.py` | 2天 |
| 熔断机制 | `circuit_breaker.py` | 2天 |
| 容错装饰器 | `fault_tolerance.py` | 1天 |

### 9.3 阶段三：可观测性 (1周)

| 任务 | 文件 | 工作量 |
|------|------|--------|
| 执行追踪 | `tracing.py` | 2天 |
| LangSmith集成 | `langsmith_integration.py` | 1天 |
| 图可视化 | `visualization.py` | 1天 |
| 决策审计 | `audit.py` | 1天 |

### 9.4 阶段四：评估体系 (1-2周)

| 任务 | 文件 | 工作量 |
|------|------|--------|
| 评估框架 | `agent_evaluator.py` | 3天 |
| A/B测试 | `ab_test.py` | 2天 |
| 测试完善 | `tests/test_agent_*.py` | 3天 |

---

## 附录：文件结构

```
app/agent/
├── __init__.py
├── graph.py              # 旧版图（保留兼容）
├── graph_v2.py           # 新版图（使用条件边）
├── state.py              # 状态定义
├── nodes.py              # 节点定义
├── routers.py            # 路由函数
├── checkpointer.py       # 检查点
├── retry_policy.py       # 重试策略
├── fault_tolerance.py    # 容错机制
├── fallbacks.py          # 降级策略
├── circuit_breaker.py    # 熔断器
├── tracing.py            # 执行追踪
├── audit.py              # 决策审计
├── visualization.py      # 图可视化
└── langsmith_integration.py

app/evaluation/
├── __init__.py
├── agent_evaluator.py    # Agent评估器
└── ab_test.py            # A/B测试框架

tests/
├── test_agent_graph.py          # 图单元测试
├── test_agent_integration.py    # 集成测试
└── test_agent_performance.py    # 性能测试
```

---

**文档维护**: 本文档应随代码实现同步更新
**最后更新**: 2026-04-15
