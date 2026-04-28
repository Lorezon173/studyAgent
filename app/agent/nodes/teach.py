"""教学循环节点：诊断 / 讲解 / 复述检测 / 追问 / 总结 / 历史检查 / 询问。"""

from app.agent.state import LearningState
from app.agent.node_decorator import node
from app.agent.nodes._shared import _append_trace
from app.core.prompts import (
    DIAGNOSE_PROMPT,
    EXPLAIN_PROMPT,
    RESTATE_CHECK_PROMPT,
    FOLLOWUP_PROMPT,
    SUMMARY_PROMPT,
)
from app.services.llm import llm_service


@node(name="history_check", retry="DB_RETRY", trace_label="History Check")
def history_check_node(state: LearningState) -> LearningState:
    """历史记录检查节点：检查用户是否学习过该主题"""
    from app.services.learning_profile_store import (
        list_topic_memory_entries,
        aggregate_by_topic,
    )

    user_id = state.get("user_id")
    topic = state.get("topic")

    state["has_history"] = False
    state["history_summary"] = ""
    state["history_mastery"] = ""

    if not user_id or not topic:
        _append_trace(state, "history_check", {"has_history": False, "reason": "no_user_or_topic"})
        return state

    try:
        records = list_topic_memory_entries(topic=topic, limit=3, user_id=user_id)

        if records:
            state["has_history"] = True
            state["history_summary"] = "；".join([
                f"{r.get('entry_type', 'unknown')}: {r.get('content', '')[:50]}"
                for r in records
            ])
            # 取最新记录的掌握程度
            if records:
                state["history_mastery"] = records[0].get("level", "unknown")
        else:
            # 尝试通过 aggregate_by_topic 检查
            agg = aggregate_by_topic(topic=topic, user_id=user_id)
            if agg.get("sessions"):
                state["has_history"] = True
                sessions = agg["sessions"][:3]
                state["history_summary"] = "；".join([
                    f"session: {s.get('level', 'unknown')} (score: {s.get('score', 'N/A')})"
                    for s in sessions
                ])
                if sessions:
                    state["history_mastery"] = sessions[0].get("level", "unknown")
    except Exception as e:
        state["node_error"] = f"history_check: {str(e)}"

    _append_trace(state, "history_check", {
        "has_history": state.get("has_history"),
        "mastery": state.get("history_mastery"),
    })

    return state


@node(name="ask_review_or_continue", trace_label="Ask Review or Continue")
def ask_review_or_continue_node(state: LearningState) -> LearningState:
    """询问节点：根据历史记录询问用户选择复习或继续"""
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


@node(name="diagnose", retry="LLM_RETRY", trace_label="Diagnose")
def diagnose_node(state: LearningState) -> LearningState:
    """诊断节点：识别用户先验知识水平"""
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


@node(name="explain", retry="LLM_RETRY", trace_label="Explain")
def explain_node(state: LearningState) -> LearningState:
    """讲解节点：用费曼法解释概念"""
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

    state.pop("need_re_explain", None)

    _append_trace(state, "explain", {"explanation_length": len(explanation)})

    return state


@node(name="restate_check", retry="LLM_RETRY", trace_label="Restate Check")
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


@node(name="followup", retry="LLM_RETRY", trace_label="Followup")
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


@node(name="summary", retry="LLM_RETRY", trace_label="Summary")
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
