# app/services/answer_templates.py
"""回答模板服务

根据证据置信等级提供不同的回答模板。
"""
from __future__ import annotations
from dataclasses import dataclass


@dataclass
class AnswerTemplate:
    """回答模板"""
    template_id: str
    content: str
    boundary_notice: str


ANSWER_TEMPLATES: dict[str, AnswerTemplate] = {
    "high": AnswerTemplate(
        template_id="high",
        content="{answer}\n\n参考来源：{citations}",
        boundary_notice="",
    ),
    "medium": AnswerTemplate(
        template_id="medium",
        content="{answer}",
        boundary_notice="基于已有信息回答，建议结合教材核实。",
    ),
    "low": AnswerTemplate(
        template_id="low",
        content="{answer}",
        boundary_notice="【重要】当前证据不足，以下为推测性回答，请查阅权威资料确认。",
    ),
}


def get_answer_template(confidence_level: str) -> AnswerTemplate:
    """根据置信等级返回回答模板

    Args:
        confidence_level: 置信等级（high/medium/low）

    Returns:
        AnswerTemplate: 回答模板
    """
    return ANSWER_TEMPLATES.get(confidence_level, ANSWER_TEMPLATES["medium"])
