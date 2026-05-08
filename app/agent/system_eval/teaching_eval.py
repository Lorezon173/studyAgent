"""Teaching Eval Subagent：评估教学效果。"""
import json

from app.services.llm import llm_service


def _parse_score(raw: str, key: str = "clarity_score") -> float:
    """解析 LLM 返回的评分 JSON。"""
    try:
        data = json.loads(raw)
        return float(data.get(key, 50))
    except (json.JSONDecodeError, TypeError, ValueError):
        return 50.0


def _generate_suggestions(clarity_result: str, coverage_result: str) -> list[str]:
    """根据评估结果生成改进建议。"""
    suggestions = []
    try:
        c_data = json.loads(clarity_result)
        if c_data.get("clarity_score", 100) < 70:
            suggestions.append("讲解清晰度不足，建议增加更多类比和例子")
        missing = c_data.get("missing_points", [])
        if missing:
            suggestions.append(f"以下知识点未被覆盖：{', '.join(str(p) for p in missing[:3])}")
    except (json.JSONDecodeError, TypeError):
        pass
    return suggestions if suggestions else ["教学效果良好，继续保持"]


def teaching_eval_node(input_data: dict) -> dict:
    """评估教学效果。"""
    session_id = input_data["session_id"]
    topic = input_data.get("topic", "")
    teaching_output = input_data.get("teaching_output", {})
    mastery_score = input_data.get("final_mastery_score", 50.0)

    # 1. 讲解清晰度评估
    clarity_prompt = f"""评估以下讲解的清晰度（0-100分）：
主题：{topic}
讲解：{teaching_output.get("explanation", "")}

评估标准：逻辑清晰度、语言通俗性、例子恰当性
返回 JSON：{{"clarity_score": 0-100, "reason": "..."}}"""

    clarity_result = llm_service.invoke(
        system_prompt="你是一个教学评估专家",
        user_prompt=clarity_prompt,
    )
    clarity_score = _parse_score(clarity_result, "clarity_score")

    # 2. 知识覆盖率评估
    coverage_prompt = f"""评估讲解对主题核心知识点的覆盖程度（0-100分）：
主题：{topic}
讲解：{teaching_output.get("explanation", "")}

返回 JSON：{{"coverage_score": 0-100, "covered_points": [...], "missing_points": [...]}}"""

    coverage_result = llm_service.invoke(
        system_prompt="你是一个知识评估专家",
        user_prompt=coverage_prompt,
    )
    coverage_score = _parse_score(coverage_result, "coverage_score")

    # 3. 交互有效性评估（基于掌握度提升）
    effectiveness_score = min(100.0, mastery_score * 1.1)

    # 4. 综合评分
    teaching_score = clarity_score * 0.4 + coverage_score * 0.3 + effectiveness_score * 0.3

    return {
        "session_id": session_id,
        "teaching_score": round(teaching_score, 2),
        "clarity_score": round(clarity_score, 2),
        "coverage_score": round(coverage_score, 2),
        "effectiveness_score": round(effectiveness_score, 2),
        "improvement_suggestions": _generate_suggestions(clarity_result, coverage_result),
    }
