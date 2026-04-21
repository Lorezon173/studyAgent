# tests/test_answer_templates.py
"""回答模板服务测试"""
from app.services.answer_templates import get_answer_template, AnswerTemplate


def test_template_for_high_confidence():
    """测试高置信度模板"""
    template = get_answer_template("high")
    assert template.template_id == "high"
    assert "参考来源" in template.content
    assert template.boundary_notice == ""


def test_template_for_low_confidence():
    """测试低置信度模板"""
    template = get_answer_template("low")
    assert template.template_id == "low"
    assert "重要" in template.boundary_notice


def test_template_defaults_to_medium():
    """测试未知置信度默认返回中等模板"""
    template = get_answer_template("unknown")
    assert template.template_id == "medium"


def test_answer_template_dataclass():
    """测试 AnswerTemplate 数据类"""
    template = AnswerTemplate(
        template_id="test",
        content="Test content",
        boundary_notice="Test notice",
    )
    assert template.template_id == "test"
    assert template.content == "Test content"
    assert template.boundary_notice == "Test notice"
