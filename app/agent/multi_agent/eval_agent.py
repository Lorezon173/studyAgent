"""Eval Agent：理解程度评估。"""
import json

from app.agent.multi_agent.state import MultiAgentState
from app.services.llm import llm_service


def _parse_eval_result(raw: str) -> dict:
    """解析 LLM 评估结果，容错处理。"""
    try:
        data = json.loads(raw)
        return {
            "mastery_score": float(data.get("mastery_score", 50)),
            "mastery_level": str(data.get("mastery_level", "medium")),
            "eval_feedback": str(data.get("eval_feedback", "")),
            "error_labels": list(data.get("error_labels", [])),
        }
    except (json.JSONDecodeError, TypeError, ValueError):
        return {
            "mastery_score": 50.0,
            "mastery_level": "medium",
            "eval_feedback": raw if raw else "评估解析失败",
            "error_labels": [],
        }


def eval_agent_node(state: MultiAgentState) -> dict:
    """Eval Agent 节点：评估用户理解程度。"""
    topic = state.get("topic") or "未指定主题"
    teaching_output = state.get("teaching_output", {})
    user_input = state.get("user_input", "")

    system_prompt = "你是一个学习评估专家，负责评估用户对知识的理解程度。"
    user_prompt = f"""主题：{topic}
讲解内容：{teaching_output.get("explanation", "")}
用户输入：{user_input}

请评估用户的理解程度，返回 JSON 格式：
{{"mastery_score": 0-100, "mastery_level": "low/medium/high", "eval_feedback": "评估反馈", "error_labels": []}}"""

    result = llm_service.invoke(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
    )

    eval_data = _parse_eval_result(result)

    return {
        "eval_output": eval_data,
        "mastery_score": eval_data["mastery_score"],
        "current_agent": "aggregator",
        "branch_trace": [{"phase": "eval_agent", "mastery_score": eval_data["mastery_score"]}],
    }
