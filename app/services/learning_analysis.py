from datetime import UTC, datetime, timedelta

from app.agent.state import LearningState
from app.services.learning_profile_store import (
    append_topic_memory_entry,
    replace_error_patterns,
    save_session_summary,
    upsert_mastery_profile,
    upsert_review_plan,
)
from app.services.evaluation_service import evaluate_learning_state
from app.services.personal_rag_store import append_personal_memory


def _calc_mastery_score(state: LearningState) -> tuple[int, str, str]:
    text = " ".join(
        [
            state.get("restatement_eval", ""),
            state.get("summary", ""),
            state.get("user_input", ""),
        ]
    ).lower()

    score = 60
    if any(k in text for k in ["准确", "清晰", "掌握", "理解较好", "正确"]):
        score += 20
    if any(k in text for k in ["不准确", "漏洞", "混淆", "不清楚", "错误"]):
        score -= 20
    if any(k in text for k in ["举例", "类比", "应用"]):
        score += 10

    score = max(0, min(100, score))
    if score >= 80:
        level = "high"
    elif score >= 60:
        level = "medium"
    else:
        level = "low"

    rationale = f"基于复述评估与总结文本规则计算，当前得分 {score}。"
    return score, level, rationale


def _extract_error_labels(state: LearningState) -> list[str]:
    text = " ".join([state.get("restatement_eval", ""), state.get("summary", "")]).lower()
    labels: list[str] = []
    if any(k in text for k in ["术语", "定义", "概念不清"]):
        labels.append("定义不清")
    if any(k in text for k in ["混淆", "区别", "对比不清"]):
        labels.append("概念混淆")
    if any(k in text for k in ["应用", "场景", "不会用"]):
        labels.append("应用不足")
    if any(k in text for k in ["步骤", "流程", "顺序"]):
        labels.append("流程理解不足")
    if not labels:
        labels.append("待进一步观察")
    return labels


def _build_review_plan(score: int) -> tuple[str, list[str]]:
    now = datetime.now(UTC)
    if score >= 80:
        next_dt = now + timedelta(days=3)
        suggestions = ["做1次综合题巩固", "尝试给他人讲解该知识点"]
    elif score >= 60:
        next_dt = now + timedelta(days=1)
        suggestions = ["复习核心定义", "完成2道针对性练习题"]
    else:
        next_dt = now + timedelta(hours=12)
        suggestions = ["重新学习基础概念", "完成3道入门题并复述解题过程"]
    return next_dt.isoformat(), suggestions


def persist_learning_outcome(state: LearningState) -> LearningState:
    session_id = state["session_id"]
    topic = state.get("topic")
    summary = state.get("summary", "")
    now = datetime.now(UTC).isoformat()

    # 模块3：掌握度评估（优先 LLM 结构化评估，失败则回退规则）
    eval_result = None
    try:
        eval_result = evaluate_learning_state(state)
    except Exception:
        eval_result = None

    if eval_result:
        score = int(eval_result["score"])
        level = str(eval_result["level"])
        rationale = str(eval_result["rationale"])
        error_labels = list(eval_result["error_labels"])
    else:
        score, level, rationale = _calc_mastery_score(state)
        error_labels = _extract_error_labels(state)

    user_id = state.get("user_id")
    save_session_summary(session_id, topic, summary, now, user_id=user_id)
    upsert_mastery_profile(session_id, topic, score, level, rationale, now, user_id=user_id)

    # 模块4：错因归纳
    replace_error_patterns(
        session_id,
        topic,
        error_labels,
        state.get("restatement_eval", ""),
        now,
        user_id=user_id,
    )

    # 模块5：复习计划
    next_review_at, suggestions = _build_review_plan(score)
    upsert_review_plan(session_id, topic, next_review_at, suggestions, now, user_id=user_id)

    # 长期记忆沉淀：按 topic 追加历史条目
    append_topic_memory_entry(
        session_id=session_id,
        topic=topic,
        entry_type="summary",
        content=summary,
        score=score,
        level=level,
        created_at=now,
        user_id=user_id,
    )
    append_personal_memory(
        user_id=state.get("user_id"),
        session_id=session_id,
        topic=topic,
        content=summary,
        source="summary",
        score=score,
        level=level,
        created_at=now,
    )
    append_topic_memory_entry(
        session_id=session_id,
        topic=topic,
        entry_type="errors",
        content=state.get("restatement_eval", ""),
        score=score,
        level=level,
        created_at=now,
        user_id=user_id,
    )
    append_topic_memory_entry(
        session_id=session_id,
        topic=topic,
        entry_type="review_plan",
        content="; ".join(suggestions),
        score=score,
        level=level,
        created_at=now,
        user_id=user_id,
    )

    state["mastery_score"] = score
    state["mastery_level"] = level
    state["mastery_rationale"] = rationale
    state["error_labels"] = error_labels
    state["next_review_at"] = next_review_at
    return state
