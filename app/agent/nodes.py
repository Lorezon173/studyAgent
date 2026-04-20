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


def intent_router_node(state: LearningState) -> LearningState:
    """意图路由节点：识别用户意图"""
    user_input = state.get("user_input", "")

    try:
        raw = llm_service.route_intent(user_input)
        data = json.loads(raw)
        intent = str(data.get("intent", "teach_loop")).strip()
        confidence = float(data.get("confidence", 0.0))
        reason = str(data.get("reason", ""))

        valid_intents = {"teach_loop", "qa_direct", "review", "replan"}
        if intent not in valid_intents:
            intent = "teach_loop"

        state["intent"] = intent
        state["intent_confidence"] = confidence
        state["intent_reason"] = reason

    except Exception as e:
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


def rag_first_node(state: LearningState) -> LearningState:
    """RAG优先检索节点：在回答问题前，先检索本地知识库"""
    from app.services.rag_coordinator import decide_rag_call, execute_rag

    topic = state.get("topic")
    user_input = state.get("user_input", "")
    user_id = state.get("user_id")

    state["rag_found"] = False
    state["rag_context"] = ""
    state["rag_citations"] = []
    state["rag_confidence_level"] = "low"
    state["rag_low_evidence"] = True
    state["rag_avg_score"] = 0.0

    try:
        decision = decide_rag_call(user_input=user_input)
        if not decision.should_call:
            _append_trace(state, "rag_first", {
                "rag_found": False,
                "reason": decision.reason,
                "citations_count": 0,
            })
            return state

        rows, meta = execute_rag(
            query=user_input,
            topic=topic,
            user_id=user_id,
            tool_route=state.get("tool_route"),
            top_k=5,
        )

        if rows:
            context_parts = []
            citations = []
            for row in rows:
                content = row.get("text", "")
                if content:
                    context_parts.append(content)
                citations.append({
                    "source": row.get("source", "unknown"),
                    "score": row.get("score", 0),
                })
            state["rag_context"] = "\n\n".join(context_parts)
            state["rag_citations"] = citations
            state["rag_found"] = True
            scores = [float(row.get("score", 0.0)) for row in rows]
            avg_score = sum(scores) / len(scores) if scores else 0.0
            state["rag_avg_score"] = avg_score
            if len(rows) >= 2 and avg_score >= 0.7:
                state["rag_confidence_level"] = "high"
                state["rag_low_evidence"] = False
            elif len(rows) >= 1 and avg_score >= 0.45:
                state["rag_confidence_level"] = "medium"
                state["rag_low_evidence"] = False
    except Exception as e:
        state["node_error"] = f"rag_first: {str(e)}"

    _append_trace(state, "rag_first", {
        "rag_found": state.get("rag_found"),
        "citations_count": len(state.get("rag_citations", [])),
    })

    return state


def rag_answer_node(state: LearningState) -> LearningState:
    """基于RAG知识回答节点"""
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
    if state.get("rag_low_evidence"):
        state["reply"] = (
            f"{state['reply']}\n\n"
            "【证据边界声明】当前可用证据较弱，以下内容包含推断，请优先结合教材或权威资料核验。"
        )
    state["stage"] = "rag_answered"

    _append_trace(state, "rag_answer", {"reply_length": len(reply)})

    return state


def llm_answer_node(state: LearningState) -> LearningState:
    """基于LLM回答节点（无知识库支撑）"""
    user_input = state.get("user_input", "")

    stream_output = bool(state.get("stream_output", False))

    reply = llm_service.invoke(
        system_prompt="你是一个知识渊博的问答助手。",
        user_prompt=user_input,
        stream_output=stream_output,
    )

    state["reply"] = reply
    if state.get("rag_low_evidence"):
        state["reply"] = (
            f"{state['reply']}\n\n"
            "【证据边界声明】当前可用证据较弱，以下内容包含推断，请优先结合教材或权威资料核验。"
        )
    state["stage"] = "llm_answered"

    _append_trace(state, "llm_answer", {"reply_length": len(reply)})

    return state


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


def knowledge_retrieval_node(state: LearningState) -> LearningState:
    """知识检索节点：在需要时补充知识"""
    from app.services.rag_coordinator import decide_rag_call, execute_rag

    topic = state.get("topic")
    user_input = state.get("user_input", "")
    user_id = state.get("user_id")

    state["retrieved_context"] = ""
    state["citations"] = []

    try:
        decision = decide_rag_call(user_input=user_input)
        if not decision.should_call:
            _append_trace(state, "knowledge_retrieval", {
                "citations_count": 0,
                "reason": decision.reason,
            })
            return state

        rows, meta = execute_rag(
            query=user_input,
            topic=topic,
            user_id=user_id,
            tool_route=state.get("tool_route"),
            top_k=5,
        )

        if rows:
            context_parts = []
            citations = []
            for row in rows:
                content = row.get("content", "")
                if content:
                    context_parts.append(content)
                citations.append({
                    "source": row.get("source", "unknown"),
                    "score": row.get("score", 0),
                })
            context = "\n\n".join(context_parts)
            state["retrieved_context"] = context
            state["citations"] = citations

            if context:
                existing = state.get("topic_context", "")
                state["topic_context"] = f"{existing}\n\n{context}".strip()
    except Exception as e:
        state["node_error"] = f"knowledge_retrieval: {str(e)}"

    _append_trace(state, "knowledge_retrieval", {"citations_count": len(state.get("citations", []))})

    return state


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


def replan_node(state: LearningState) -> LearningState:
    """重规划节点"""
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


# ===== Phase 2: 编排增强节点 =====


def retrieval_planner_node(state: LearningState) -> dict:
    """检索规划节点

    根据用户输入和主题，构建查询计划并选择检索策略。

    输入：
        - user_input: 用户输入
        - topic: 当前学习主题

    输出：
        - retrieval_mode: 查询模式
        - retrieval_strategy: 检索策略配置
    """
    from app.services.query_planner import build_query_plan
    from app.services.retrieval_strategy import get_retrieval_strategy

    user_input = state.get("user_input", "")
    topic = state.get("topic")

    # 复用 Phase 1 的查询规划
    plan = build_query_plan(user_input, topic)

    # 根据模式获取检索策略
    strategy = get_retrieval_strategy(plan.mode)

    _append_trace(state, "retrieval_planner", {
        "mode": plan.mode,
        "reason": plan.reason,
    })

    return {
        "retrieval_mode": plan.mode,
        "retrieval_strategy": strategy,
    }


def evidence_gate_node(state: LearningState) -> dict:
    """证据守门节点

    验证证据质量，决定是否可以进入回答阶段。

    输入：
        - user_input: 用户查询
        - rag_context: RAG 检索上下文
        - rag_found: 是否找到证据

    输出：
        - gate_status: 守门状态
        - gate_coverage_score: 覆盖度分数
        - gate_missing_keywords: 缺失关键词
    """
    from app.services.evidence_validator import validate_evidence

    user_input = state.get("user_input", "")
    rag_context = state.get("rag_context", "")
    rag_found = state.get("rag_found", False)

    if not rag_found or not rag_context:
        _append_trace(state, "evidence_gate", {
            "status": "reject",
            "reason": "no_evidence",
        })
        return {
            "gate_status": "reject",
            "gate_coverage_score": 0.0,
            "gate_missing_keywords": [],
        }

    # 将上下文转换为证据块
    evidence_chunks = [{"text": rag_context, "score": 0.8}]

    # 调用验证服务
    result = validate_evidence(user_input, evidence_chunks)

    _append_trace(state, "evidence_gate", {
        "status": result.status,
        "coverage": result.coverage_score,
    })

    return {
        "gate_status": result.status,
        "gate_coverage_score": result.coverage_score,
        "gate_missing_keywords": result.missing_keywords,
    }


def answer_policy_node(state: LearningState) -> dict:
    """回答策略节点

    根据证据置信等级选择回答模板，生成边界声明。

    输入：
        - rag_confidence_level: 证据置信等级
        - gate_status: 守门状态

    输出：
        - answer_template_id: 回答模板ID
        - boundary_notice: 边界声明文本
    """
    from app.services.answer_templates import get_answer_template

    confidence_level = state.get("rag_confidence_level", "medium")
    gate_status = state.get("gate_status", "supplement")

    # 根据守门状态调整置信等级
    if gate_status == "reject":
        confidence_level = "low"
    elif gate_status == "supplement":
        confidence_level = "medium"

    # 获取模板
    template = get_answer_template(confidence_level)

    _append_trace(state, "answer_policy", {
        "template_id": template.template_id,
        "confidence_level": confidence_level,
    })

    return {
        "answer_template_id": template.template_id,
        "boundary_notice": template.boundary_notice,
    }


def recovery_node(state: LearningState) -> dict:
    """恢复节点

    处理节点失败，执行降级策略。

    输入：
        - node_error: 错误信息
        - stage: 当前阶段

    输出：
        - recovery_action: 恢复动作
        - fallback_triggered: 是否降级
        - reply: 降级响应文本
    """
    from app.services.error_classifier import classify_error

    error_info = state.get("node_error", "")
    stage = state.get("stage", "unknown")

    # 创建错误对象
    error = Exception(error_info) if error_info else Exception("Unknown error")

    # 分类错误
    classification = classify_error(error)

    # 生成降级响应
    fallback_messages = {
        "use_cache": "正在恢复，请稍候重试。",
        "pure_llm": "当前检索服务不可用，将基于已有知识回答。",
        "suggest_refine": "未找到相关内容，建议换关键词或补充描述。",
        "delay_retry": "服务繁忙，请稍后再试。",
    }

    reply = fallback_messages.get(
        classification.fallback_action,
        "服务暂时不可用，请稍后重试。"
    )

    _append_trace(state, "recovery", {
        "error_type": classification.error_type.value,
        "action": classification.fallback_action,
    })

    return {
        "recovery_action": classification.fallback_action,
        "fallback_triggered": True,
        "error_code": classification.error_type.value,
        "reply": reply,
    }
