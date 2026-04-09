from langgraph.graph import END, StateGraph

from app.agent.state import LearningState
from app.core.prompts import (
    DIAGNOSE_PROMPT,
    EXPLAIN_PROMPT,
    RESTATE_CHECK_PROMPT,
    FOLLOWUP_PROMPT,
    SUMMARY_PROMPT,
)
from app.services.llm import llm_service


def diagnose_node(state: LearningState) -> LearningState:
    """诊断节点：识别用户先验知识水平"""
    topic = state.get("topic") or "未指定主题"
    user_input = state["user_input"]
    topic_context = state.get("topic_context", "")

    prompt = DIAGNOSE_PROMPT.format(topic=topic, user_input=user_input, topic_context=topic_context)
    diagnosis = llm_service.invoke(
        system_prompt="你是严谨的学习诊断助手。",
        user_prompt=prompt,
    )

    state["diagnosis"] = diagnosis
    state["stage"] = "diagnosed"
    return state


def explain_node(state: LearningState) -> LearningState:
    """讲解节点：用费曼法解释概念"""
    topic = state.get("topic") or "未指定主题"
    user_input = state.get("user_input", "")
    topic_context = state.get("topic_context", "")

    prompt = EXPLAIN_PROMPT.format(topic=topic, user_input=user_input, topic_context=topic_context)
    if bool(state.get("stream_output", False)):
        explanation = llm_service.invoke(
            system_prompt="你是擅长费曼学习法的教学助手。",
            user_prompt=prompt,
            stream_output=True,
        )
    else:
        explanation = llm_service.invoke(
            system_prompt="你是擅长费曼学习法的教学助手。",
            user_prompt=prompt,
        )

    state["explanation"] = explanation
    state["reply"] = explanation
    state["stage"] = "explained"
    return state


def restate_check_node(state: LearningState) -> LearningState:
    """复述检测节点：检验用户理解的深度"""
    topic = state.get("topic") or "未指定主题"
    explanation = state.get("explanation", "")
    user_input = state["user_input"]
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

    if bool(state.get("stream_output", False)):
        question = llm_service.invoke(
            system_prompt="你是费曼学习法中的追问老师。",
            user_prompt=prompt,
            stream_output=True,
        )
    else:
        question = llm_service.invoke(
            system_prompt="你是费曼学习法中的追问老师。",
            user_prompt=prompt,
        )

    state["followup_question"] = question
    state["reply"] = question
    state["stage"] = "followup_generated"
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

    if bool(state.get("stream_output", False)):
        summary = llm_service.invoke(
            system_prompt="你是负责复盘学习成果的老师。",
            user_prompt=prompt,
            stream_output=True,
        )
    else:
        summary = llm_service.invoke(
            system_prompt="你是负责复盘学习成果的老师。",
            user_prompt=prompt,
        )

    state["summary"] = summary
    state["stage"] = "summarized"
    return state


def qa_direct_node(state: LearningState) -> LearningState:
    """答疑子图节点：直接回答问题并保持原教学阶段。"""
    current_stage = state.get("stage") or "start"
    # 兼容旧测试中的 monkeypatch（未声明 stream_output 参数）。
    try:
        state["reply"] = llm_service.answer_direct(
            user_input=state.get("user_input", ""),
            topic=state.get("topic"),
            comparison_mode=bool(state.get("comparison_mode", False)),
            stream_output=bool(state.get("stream_output", False)),
        )
    except TypeError:
        state["reply"] = llm_service.answer_direct(
            user_input=state.get("user_input", ""),
            topic=state.get("topic"),
            comparison_mode=bool(state.get("comparison_mode", False)),
        )
    state["stage"] = current_stage
    return state


def build_learning_graph():
    """构建完整费曼学习法工作流（兼容链路）"""
    graph = StateGraph(LearningState)

    graph.add_node("diagnose", diagnose_node)
    graph.add_node("explain", explain_node)
    graph.add_node("restate_check", restate_check_node)
    graph.add_node("followup", followup_node)
    graph.add_node("summarize", summarize_node)

    graph.set_entry_point("diagnose")
    graph.add_edge("diagnose", "explain")
    graph.add_edge("explain", "restate_check")
    graph.add_edge("restate_check", "followup")
    graph.add_edge("followup", "summarize")
    graph.add_edge("summarize", END)

    return graph.compile()


def build_initial_graph():
    """阶段A：诊断 + 讲解"""
    graph = StateGraph(LearningState)
    graph.add_node("diagnose", diagnose_node)
    graph.add_node("explain", explain_node)
    graph.set_entry_point("diagnose")
    graph.add_edge("diagnose", "explain")
    graph.add_edge("explain", END)
    return graph.compile()


def build_restate_graph():
    """阶段B：复述检测 + 追问"""
    graph = StateGraph(LearningState)
    graph.add_node("restate_check", restate_check_node)
    graph.add_node("followup", followup_node)
    graph.set_entry_point("restate_check")
    graph.add_edge("restate_check", "followup")
    graph.add_edge("followup", END)
    return graph.compile()


def build_summary_graph():
    """阶段C：总结"""
    graph = StateGraph(LearningState)
    graph.add_node("summarize", summarize_node)
    graph.set_entry_point("summarize")
    graph.add_edge("summarize", END)
    return graph.compile()


def build_qa_direct_graph():
    """答疑子图：单节点直答，完成后恢复原阶段。"""
    graph = StateGraph(LearningState)
    graph.add_node("qa_direct", qa_direct_node)
    graph.set_entry_point("qa_direct")
    graph.add_edge("qa_direct", END)
    return graph.compile()


learning_graph = build_learning_graph()
initial_graph = build_initial_graph()
restate_graph = build_restate_graph()
summary_graph = build_summary_graph()
qa_direct_graph = build_qa_direct_graph()
