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
from app.agent.nodes import register_all_nodes
from app.agent.node_registry import get_registry

register_all_nodes()  # ensures @node decorators have run before we read the registry
from app.agent.routers import (
    route_by_intent,
    route_after_history_check,
    route_after_choice,
    route_after_diagnosis,
    route_after_restate,
    route_after_rag,
    # Phase 2 新增路由
    route_after_evidence_gate,
    # Phase 4: 错误路由
    route_on_error_or_evidence,
    route_on_error_or_explain,
)
from app.agent.checkpointer import get_checkpointer
from app.agent.retry_policy import RETRY_POLICIES_MAP


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
    # 节点通过 @node 装饰器在导入时自动注册；
    # add_to_graph 按 meta.retry_key 解析重试策略。
    get_registry().add_to_graph(graph, retries=RETRY_POLICIES_MAP)

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
    graph.add_conditional_edges(
        "rag_first",
        route_on_error_or_evidence,
        {
            "evidence_gate": "evidence_gate",
            "recovery": "recovery",
            "retry_rag": "rag_first",
        },
    )

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
    graph.add_conditional_edges(
        "knowledge_retrieval",
        route_on_error_or_explain,
        {
            "explain": "explain",
            "recovery": "recovery",
            "retry_rag": "knowledge_retrieval",
        },
    )
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
