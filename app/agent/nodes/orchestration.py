"""编排节点：意图路由 / 重规划 / 检索规划 / 证据守门 / 回答策略 / 恢复。"""

import json

from app.agent.state import LearningState
from app.agent.node_decorator import node
from app.agent.nodes._shared import _append_trace, _rule_based_route
from app.services.llm import llm_service


@node(name="intent_router", retry="LLM_RETRY", trace_label="Intent Router")
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


@node(name="replan", retry="LLM_RETRY", trace_label="Replan")
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


@node(name="retrieval_planner", trace_label="Retrieval Planner")
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


@node(name="evidence_gate", trace_label="Evidence Gate")
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


@node(name="answer_policy", trace_label="Answer Policy")
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


@node(name="recovery", trace_label="Recovery")
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
