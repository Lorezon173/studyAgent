"""教学节点单元测试。"""
import pytest
from app.agent.nodes.teach import (
    history_check_node,
    diagnose_node,
    explain_node,
    restate_check_node,
    followup_node,
    summarize_node,
)
from app.agent.state import LearningState


class TestHistoryCheckNode:
    def test_history_check_no_user_or_topic(self):
        state: LearningState = {}
        result = history_check_node(state)

        assert result["has_history"] is False

    def test_history_check_no_history(self, monkeypatch):
        def fake_list_entries(topic, limit, user_id):
            return []

        def fake_aggregate(topic, user_id):
            return {"sessions": []}

        monkeypatch.setattr("app.services.learning_profile_store.list_topic_memory_entries", fake_list_entries)
        monkeypatch.setattr("app.services.learning_profile_store.aggregate_by_topic", fake_aggregate)

        state: LearningState = {"user_id": 1, "topic": "二分查找"}
        result = history_check_node(state)

        assert result["has_history"] is False

    def test_history_check_has_history(self, monkeypatch):
        def fake_list_entries(topic, limit, user_id):
            return [{"entry_type": "session", "content": "掌握了基本概念", "level": "medium"}]

        monkeypatch.setattr("app.services.learning_profile_store.list_topic_memory_entries", fake_list_entries)

        state: LearningState = {"user_id": 1, "topic": "二分查找"}
        result = history_check_node(state)

        assert result["has_history"] is True
        assert "history_summary" in result


class TestDiagnoseNode:
    def test_diagnose_generates_diagnosis(self, monkeypatch):
        def fake_invoke(system_prompt, user_prompt, stream_output=False):
            return "用户对二分查找有基本了解，但边界条件不清晰。"

        monkeypatch.setattr("app.services.llm.llm_service.invoke", fake_invoke)

        state: LearningState = {
            "user_input": "我知道二分查找要取中间值",
            "topic": "二分查找",
            "topic_context": ""
        }
        result = diagnose_node(state)

        assert "diagnosis" in result
        assert result["stage"] == "diagnosed"

    def test_diagnose_updates_state(self, monkeypatch):
        def fake_invoke(system_prompt, user_prompt, stream_output=False):
            return "诊断结果"

        monkeypatch.setattr("app.services.llm.llm_service.invoke", fake_invoke)

        state: LearningState = {"user_input": "test", "topic": "test"}
        result = diagnose_node(state)

        assert "diagnosis" in result


class TestExplainNode:
    def test_explain_generates_explanation(self, monkeypatch):
        def fake_invoke(system_prompt, user_prompt, stream_output=False):
            return "二分查找每次比较中间元素，缩小搜索范围。"

        monkeypatch.setattr("app.services.llm.llm_service.invoke", fake_invoke)

        state: LearningState = {
            "user_input": "讲解二分查找",
            "topic": "二分查找",
            "topic_context": "",
            "diagnosis": "用户基础一般"
        }
        result = explain_node(state)

        assert "explanation" in result
        assert result["stage"] == "explained"

    def test_explain_uses_context(self, monkeypatch):
        captured = {}

        def fake_invoke(system_prompt, user_prompt, stream_output=False):
            captured["user_prompt"] = user_prompt
            return "讲解内容"

        monkeypatch.setattr("app.services.llm.llm_service.invoke", fake_invoke)

        state: LearningState = {
            "user_input": "讲解",
            "topic": "二分查找",
            "topic_context": "用户之前学过线性查找",
            "diagnosis": ""
        }
        explain_node(state)

        assert "用户之前学过线性查找" in captured["user_prompt"]


class TestRestateCheckNode:
    def test_restate_check_evaluates(self, monkeypatch):
        def fake_invoke(system_prompt, user_prompt, stream_output=False):
            return "复述准确，理解程度高。"

        monkeypatch.setattr("app.services.llm.llm_service.invoke", fake_invoke)

        state: LearningState = {
            "user_input": "每次取中间值比较",
            "explanation": "二分查找的核心是取中间值"
        }
        result = restate_check_node(state)

        assert "restatement_eval" in result

    def test_restate_check_detects_misunderstanding(self, monkeypatch):
        def fake_invoke(system_prompt, user_prompt, stream_output=False):
            return "复述存在错误，对边界条件理解有误。"

        monkeypatch.setattr("app.services.llm.llm_service.invoke", fake_invoke)

        state: LearningState = {
            "user_input": "每次取第一个元素",
            "explanation": "二分查找取中间值"
        }
        result = restate_check_node(state)

        assert "错误" in result["restatement_eval"] or "误解" in result["restatement_eval"]


class TestFollowupNode:
    def test_followup_generates_question(self, monkeypatch):
        def fake_invoke(system_prompt, user_prompt, stream_output=False):
            return "请说明为什么数组必须有序？"

        monkeypatch.setattr("app.services.llm.llm_service.invoke", fake_invoke)

        state: LearningState = {
            "user_input": "我理解了",
            "topic": "二分查找",
            "restatement_eval": "理解较好"
        }
        result = followup_node(state)

        assert "followup_question" in result
        assert result["stage"] == "followup_generated"


class TestSummarizeNode:
    def test_summarize_generates_summary(self, monkeypatch):
        def fake_invoke(system_prompt, user_prompt, stream_output=False):
            return "本节课学习了二分查找的基本原理和时间复杂度。"

        monkeypatch.setattr("app.services.llm.llm_service.invoke", fake_invoke)

        state: LearningState = {
            "user_input": "我明白了",
            "topic": "二分查找",
            "diagnosis": "基础理解",
            "explanation": "二分查找讲解"
        }
        result = summarize_node(state)

        assert "summary" in result
        assert result["stage"] == "summarized"

    def test_summarize_sets_reply(self, monkeypatch):
        def fake_invoke(system_prompt, user_prompt, stream_output=False):
            return "总结内容"

        monkeypatch.setattr("app.services.llm.llm_service.invoke", fake_invoke)

        state: LearningState = {
            "user_input": "我明白了",
            "topic": "二分查找",
            "diagnosis": "",
            "explanation": ""
        }
        result = summarize_node(state)

        assert result["reply"] == "总结内容"
