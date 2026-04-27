# app/agent/graph_v2.py
"""
学习Agent图定义 V2
充分利用LangGraph特性：条件边、检查点、重试策略

Phase 2 增强：
- 新增检索规划节点（retrieval_planner）
- 新增证据守门节点（evidence_gate）
- 新增回答策略节点（answer_policy）
- 新增恢复节点（recovery）
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
    # Phase 2 新增节点
    retrieval_planner_node,
    evidence_gate_node,
    answer_policy_node,
    recovery_node,
)
from app.agent.routers import (
    route_by_intent,
    route_after_history_check,
    route_after_choice,
    route_after_diagnosis,
    route_after_restate,
    route_after_rag,
    # Phase 2 新增路由
    route_after_evidence_gate,
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
    - Phase 2: 编排增强节点
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

    # ===== Phase 2: 编排增强节点 =====
    graph.add_node("retrieval_planner", retrieval_planner_node)
    graph.add_node("evidence_gate", evidence_gate_node)
    graph.add_node("answer_policy", answer_policy_node)
    graph.add_node("recovery", recovery_node)

    # ===== 设置入口 =====
    graph.set_entry_point("intent_router")

    # ===== 条件边 =====

    # 意图路由
    graph.add_conditional_edges(
        "intent_router",
        route_by_intent,
        {
            "history_check": "history_check",
            "rag_first": "retrieval_planner",
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

    # RAG检索后进入证据守门
    graph.add_edge("retrieval_planner", "rag_first")
    graph.add_edge("rag_first", "evidence_gate")

    # 证据守门后路由
    graph.add_conditional_edges(
        "evidence_gate",
        route_after_evidence_gate,
        {
            "answer_policy": "answer_policy",
            "recovery": "recovery",
        },
    )

    # 回答策略后选择具体回答节点
    graph.add_conditional_edges(
        "answer_policy",
        route_after_rag,
        {
            "rag_answer": "rag_answer",
            "llm_answer": "llm_answer",
        },
    )

    # ===== 固定边 =====
    graph.add_edge("knowledge_retrieval", "explain")
    graph.add_edge("explain", "restate_check")
    graph.add_edge("followup", "summary")
    graph.add_edge("summary", END)
    graph.add_edge("rag_answer", END)
    graph.add_edge("llm_answer", END)
    graph.add_edge("replan", END)
    graph.add_edge("recovery", END)  # Phase 2: 恢复节点结束

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
