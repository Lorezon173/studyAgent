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
