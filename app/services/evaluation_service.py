import json
import re

from app.agent.state import LearningState
from app.core.prompts import EVALUATOR_PROMPT
from app.services.llm import llm_service


def _parse_json_text(raw: str) -> dict:
    text = (raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    data = json.loads(text)
    return data if isinstance(data, dict) else {}


def evaluate_learning_state(state: LearningState) -> dict | None:
    prompt = EVALUATOR_PROMPT.format(
        topic=state.get("topic") or "未指定主题",
        user_input=state.get("user_input", ""),
        restatement_eval=state.get("restatement_eval", ""),
        summary=state.get("summary", ""),
    )
    raw = llm_service.invoke(system_prompt="你是严格输出JSON的学习评估裁判。", user_prompt=prompt)
    data = _parse_json_text(raw)

    score_1to5 = int(data.get("mastery_score_1to5", 0))
    if score_1to5 < 1 or score_1to5 > 5:
        return None

    error_labels = data.get("error_labels", [])
    if not isinstance(error_labels, list):
        error_labels = []
    error_labels = [str(x).strip() for x in error_labels if str(x).strip()]
    if not error_labels:
        error_labels = ["待进一步观察"]

    rationale = str(data.get("rationale", "LLM评估结果"))
    confidence = float(data.get("confidence", 0.0))
    confidence = max(0.0, min(1.0, confidence))

    score_100 = max(0, min(100, score_1to5 * 20))
    if score_100 >= 80:
        level = "high"
    elif score_100 >= 60:
        level = "medium"
    else:
        level = "low"

    return {
        "score": score_100,
        "level": level,
        "rationale": rationale,
        "error_labels": error_labels,
        "confidence": confidence,
        "source": "llm_judge",
    }

