"""Orchestrator Eval Subagent：评估路由决策质量。"""
import json

from app.services.llm import llm_service


def _generate_orchestrator_suggestions(intent_result: str, routing_score: float) -> list[str]:
    """生成 Orchestrator 改进建议。"""
    suggestions = []
    try:
        data = json.loads(intent_result)
        if not data.get("is_correct", True):
            should_be = data.get("should_be", "unknown")
            suggestions.append(f"意图识别有误，应识别为 {should_be}")
    except (json.JSONDecodeError, TypeError):
        pass

    if routing_score < 60:
        suggestions.append("路由合理性偏低，建议优化任务队列分配策略")
    return suggestions if suggestions else ["路由决策合理，继续保持"]


def orchestrator_eval_node(input_data: dict) -> dict:
    """评估 Orchestrator 路由决策。"""
    session_id = input_data["session_id"]
    user_input = input_data.get("user_input", "")
    detected_intent = input_data.get("detected_intent", "")
    teaching_eval = input_data.get("teaching_eval_result", {})
    response_time_ms = input_data.get("response_time_ms", 0.0)

    # 1. 意图识别准确性（LLM 二次判断）
    intent_check_prompt = f"""判断以下意图识别是否正确：
用户输入：{user_input}
识别意图：{detected_intent}

返回 JSON：{{"is_correct": true/false, "should_be": "...", "reason": "..."}}"""

    intent_result = llm_service.invoke(
        system_prompt="你是一个意图识别评估专家",
        user_prompt=intent_check_prompt,
    )

    try:
        intent_data = json.loads(intent_result)
        is_correct = bool(intent_data.get("is_correct", False))
    except (json.JSONDecodeError, TypeError):
        is_correct = True

    intent_accuracy = 100.0 if is_correct else 50.0

    # 2. 路由合理性（结合教学评估结果）
    teaching_score = teaching_eval.get("teaching_score", 50.0)

    if teaching_score >= 70:
        routing_score = 80.0
    elif teaching_score >= 50:
        routing_score = 60.0
    else:
        routing_score = 40.0

    # 3. 综合评分
    orchestrator_score = intent_accuracy * 0.5 + routing_score * 0.5

    return {
        "session_id": session_id,
        "orchestrator_score": round(orchestrator_score, 2),
        "intent_accuracy": round(intent_accuracy, 2),
        "routing_score": round(routing_score, 2),
        "response_time_ms": float(response_time_ms),
        "improvement_suggestions": _generate_orchestrator_suggestions(intent_result, routing_score),
    }
