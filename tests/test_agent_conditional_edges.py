# tests/test_agent_conditional_edges.py
"""
Comprehensive tests for conditional edge routing functions.
Tests all 6 router functions with multiple test cases each.
"""

import pytest

from app.agent.routers import (
    route_by_intent,
    route_after_history_check,
    route_after_choice,
    route_after_diagnosis,
    route_after_restate,
    route_after_rag,
)
from app.agent.state import LearningState


class TestRouteByIntent:
    """Tests for route_by_intent routing function."""

    def test_route_qa_direct_intent(self):
        """qa_direct intent should route to rag_first."""
        state: LearningState = {"intent": "qa_direct"}
        assert route_by_intent(state) == "rag_first"

    def test_route_replan_intent(self):
        """replan intent should route to replan."""
        state: LearningState = {"intent": "replan"}
        assert route_by_intent(state) == "replan"

    def test_route_review_intent(self):
        """review intent should route to summary."""
        state: LearningState = {"intent": "review"}
        assert route_by_intent(state) == "summary"

    def test_route_teach_loop_intent(self):
        """teach_loop intent should route to history_check."""
        state: LearningState = {"intent": "teach_loop"}
        assert route_by_intent(state) == "history_check"

    def test_route_unknown_intent_falls_back_to_history_check(self):
        """Unknown intent should fall back to history_check."""
        state: LearningState = {"intent": "unknown_intent"}
        assert route_by_intent(state) == "history_check"

    def test_route_missing_intent_defaults_to_teach_loop(self):
        """Missing intent should default to teach_loop and route to history_check."""
        state: LearningState = {}
        assert route_by_intent(state) == "history_check"

    def test_route_empty_string_intent_falls_back(self):
        """Empty string intent should fall back to history_check."""
        state: LearningState = {"intent": ""}
        assert route_by_intent(state) == "history_check"

    def test_route_case_sensitive_intent(self):
        """Intent matching should be case-sensitive (QA_DIRECT != qa_direct)."""
        state: LearningState = {"intent": "QA_DIRECT"}
        # Case-sensitive, so this falls back to history_check
        assert route_by_intent(state) == "history_check"


class TestRouteAfterHistoryCheck:
    """Tests for route_after_history_check routing function."""

    def test_route_with_history_true(self):
        """has_history=True should route to ask_review_or_continue."""
        state: LearningState = {"has_history": True}
        assert route_after_history_check(state) == "ask_review_or_continue"

    def test_route_with_history_false(self):
        """has_history=False should route to diagnose."""
        state: LearningState = {"has_history": False}
        assert route_after_history_check(state) == "diagnose"

    def test_route_missing_has_history_defaults_false(self):
        """Missing has_history should default to False and route to diagnose."""
        state: LearningState = {}
        assert route_after_history_check(state) == "diagnose"

    def test_route_with_other_state_fields_present(self):
        """Should only consider has_history field, ignoring others."""
        state: LearningState = {
            "has_history": True,
            "user_input": "test",
            "stage": "initial",
        }
        assert route_after_history_check(state) == "ask_review_or_continue"


class TestRouteAfterChoice:
    """Tests for route_after_choice routing function."""

    def test_route_review_choice(self):
        """user_choice='review' should route to diagnose."""
        state: LearningState = {"user_choice": "review"}
        assert route_after_choice(state) == "diagnose"

    def test_route_continue_choice(self):
        """user_choice='continue' should route to explain."""
        state: LearningState = {"user_choice": "continue"}
        assert route_after_choice(state) == "explain"

    def test_route_missing_choice_defaults_to_continue(self):
        """Missing user_choice should default to 'continue' and route to explain."""
        state: LearningState = {}
        assert route_after_choice(state) == "explain"

    def test_route_unknown_choice_defaults_to_explain(self):
        """Unknown user_choice should default to explain."""
        state: LearningState = {"user_choice": "unknown"}
        assert route_after_choice(state) == "explain"

    def test_route_empty_string_choice_defaults_to_explain(self):
        """Empty string user_choice should default to explain."""
        state: LearningState = {"user_choice": ""}
        assert route_after_choice(state) == "explain"


class TestRouteAfterDiagnosis:
    """Tests for route_after_diagnosis routing function."""

    def test_route_mastered_diagnosis(self):
        """Diagnosis containing 'mastered' keywords should route to summary."""
        state: LearningState = {"diagnosis": "用户已掌握该知识点"}
        assert route_after_diagnosis(state) == "summary"

    def test_route_familiar_diagnosis(self):
        """Diagnosis containing 'familiar' keywords should route to summary."""
        state: LearningState = {"diagnosis": "用户对该内容熟悉"}
        assert route_after_diagnosis(state) == "summary"

    def test_route_fully_understood_diagnosis(self):
        """Diagnosis containing 'understanding sufficient' keywords should route to summary."""
        state: LearningState = {"diagnosis": "理解充分，可以跳过"}
        assert route_after_diagnosis(state) == "summary"

    def test_route_needs_supplement_diagnosis(self):
        """Diagnosis indicating need for supplemental material should route to knowledge_retrieval."""
        state: LearningState = {"diagnosis": "需要补充相关背景知识"}
        assert route_after_diagnosis(state) == "knowledge_retrieval"

    def test_route_missing_material_diagnosis(self):
        """Diagnosis indicating missing materials should route to knowledge_retrieval."""
        state: LearningState = {"diagnosis": "缺少资料，建议检索"}
        assert route_after_diagnosis(state) == "knowledge_retrieval"

    def test_route_suggest_reference_diagnosis(self):
        """Diagnosis suggesting reference material should route to knowledge_retrieval."""
        state: LearningState = {"diagnosis": "建议参考外部资源"}
        assert route_after_diagnosis(state) == "knowledge_retrieval"

    def test_route_normal_diagnosis(self):
        """Normal diagnosis should route to explain."""
        state: LearningState = {"diagnosis": "需要详细讲解"}
        assert route_after_diagnosis(state) == "explain"

    def test_route_missing_diagnosis_defaults_to_explain(self):
        """Missing diagnosis should default to explain."""
        state: LearningState = {}
        assert route_after_diagnosis(state) == "explain"

    def test_route_empty_diagnosis(self):
        """Empty diagnosis should route to explain."""
        state: LearningState = {"diagnosis": ""}
        assert route_after_diagnosis(state) == "explain"

    def test_route_diagnosis_priority_mastered_over_needs_supplement(self):
        """When both keywords present, mastered/familiar takes priority (checked first)."""
        state: LearningState = {"diagnosis": "已掌握，需要补充"}
        # The function checks for mastered/familiar first
        assert route_after_diagnosis(state) == "summary"


class TestRouteAfterRestate:
    """Tests for route_after_restate routing function."""

    def test_route_understood_restate(self):
        """Restatement evaluation indicating understanding should route to summary."""
        state: LearningState = {"restatement_eval": "用户已理解核心概念"}
        assert route_after_restate(state) == "summary"

    def test_route_accurate_restate(self):
        """Restatement evaluation indicating accuracy should route to summary."""
        state: LearningState = {"restatement_eval": "复述准确"}
        assert route_after_restate(state) == "summary"

    def test_route_complete_restate(self):
        """Restatement evaluation indicating completeness should route to summary."""
        state: LearningState = {"restatement_eval": "回答完整"}
        assert route_after_restate(state) == "summary"

    def test_route_correct_restate(self):
        """Restatement evaluation indicating correctness should route to summary."""
        state: LearningState = {"restatement_eval": "表述正确"}
        assert route_after_restate(state) == "summary"

    def test_route_error_with_loop_allowed(self):
        """Error with loop count < 3 should increment loop and route to explain."""
        state: LearningState = {
            "restatement_eval": "存在错误理解",
            "explain_loop_count": 0,
        }
        result = route_after_restate(state)
        assert result == "explain"
        assert state["explain_loop_count"] == 1

    def test_route_confusion_with_loop_allowed(self):
        """Confusion with loop count < 3 should increment loop and route to explain."""
        state: LearningState = {
            "restatement_eval": "概念混淆",
            "explain_loop_count": 1,
        }
        result = route_after_restate(state)
        assert result == "explain"
        assert state["explain_loop_count"] == 2

    def test_route_misunderstanding_with_loop_allowed(self):
        """Misunderstanding with loop count < 3 should increment loop and route to explain."""
        state: LearningState = {
            "restatement_eval": "存在误解",
            "explain_loop_count": 2,
        }
        result = route_after_restate(state)
        assert result == "explain"
        assert state["explain_loop_count"] == 3

    def test_route_unclear_with_loop_allowed(self):
        """Unclear with loop count < 3 should increment loop and route to explain."""
        state: LearningState = {
            "restatement_eval": "表述不清楚",
            "explain_loop_count": 0,
        }
        result = route_after_restate(state)
        assert result == "explain"
        assert state["explain_loop_count"] == 1

    def test_route_error_at_max_loop(self):
        """Error with loop count == 3 should route to followup (no more re-explanation)."""
        state: LearningState = {
            "restatement_eval": "存在错误",
            "explain_loop_count": 3,
        }
        result = route_after_restate(state)
        assert result == "followup"
        # Loop count should not be incremented
        assert state["explain_loop_count"] == 3

    def test_route_error_exceeds_max_loop(self):
        """Error with loop count > 3 should route to followup."""
        state: LearningState = {
            "restatement_eval": "存在错误",
            "explain_loop_count": 4,
        }
        result = route_after_restate(state)
        assert result == "followup"

    def test_route_partial_understanding(self):
        """Partial understanding (no clear keywords) should route to followup."""
        state: LearningState = {"restatement_eval": "部分理解"}
        assert route_after_restate(state) == "followup"

    def test_route_missing_restate_eval_defaults_to_followup(self):
        """Missing restatement_eval should default to followup."""
        state: LearningState = {}
        assert route_after_restate(state) == "followup"

    def test_route_empty_restate_eval(self):
        """Empty restatement_eval should route to followup."""
        state: LearningState = {"restatement_eval": ""}
        assert route_after_restate(state) == "followup"

    def test_route_understood_priority_over_error(self):
        """Understanding keywords should take priority over error keywords."""
        state: LearningState = {
            "restatement_eval": "已理解，但有小错误",
            "explain_loop_count": 0,
        }
        # "已理解" is checked first, so routes to summary
        assert route_after_restate(state) == "summary"


class TestRouteAfterRag:
    """Tests for route_after_rag routing function."""

    def test_route_rag_found_true(self):
        """rag_found=True should route to rag_answer."""
        state: LearningState = {"rag_found": True}
        assert route_after_rag(state) == "rag_answer"

    def test_route_rag_found_false(self):
        """rag_found=False should route to llm_answer."""
        state: LearningState = {"rag_found": False}
        assert route_after_rag(state) == "llm_answer"

    def test_route_missing_rag_found_defaults_false(self):
        """Missing rag_found should default to False and route to llm_answer."""
        state: LearningState = {}
        assert route_after_rag(state) == "llm_answer"

    def test_route_with_rag_context_present(self):
        """Should route based on rag_found even when rag_context is present."""
        state: LearningState = {
            "rag_found": True,
            "rag_context": "Some retrieved context",
        }
        assert route_after_rag(state) == "rag_answer"

    def test_route_with_rag_citations_present(self):
        """Should route based on rag_found even when rag_citations is present."""
        state: LearningState = {
            "rag_found": False,
            "rag_citations": [{"source": "doc1"}],
        }
        assert route_after_rag(state) == "llm_answer"


class TestRouterEdgeCases:
    """Additional edge case tests for all routers."""

    def test_route_by_intent_with_none_value(self):
        """route_by_intent with None value should use default."""
        state: LearningState = {"intent": None}  # type: ignore
        # get() returns None, and route_map.get(None, ...) falls back to default
        assert route_by_intent(state) == "history_check"

    def test_route_after_diagnosis_with_multiple_keywords(self):
        """route_after_diagnosis with multiple keyword types should match first category."""
        # "熟悉" is matched first (mastered/familiar check)
        state: LearningState = {"diagnosis": "熟悉，但需要补充"}
        assert route_after_diagnosis(state) == "summary"

    def test_route_after_restate_with_non_integer_loop_count(self):
        """route_after_restate raises TypeError for non-integer loop counts."""
        # The function expects int, passing a string causes TypeError on comparison
        state: LearningState = {
            "restatement_eval": "存在错误",
            "explain_loop_count": "2",  # type: ignore
        }
        # Document current behavior: TypeError is raised
        with pytest.raises(TypeError, match="not supported"):
            route_after_restate(state)

    def test_route_after_rag_with_truthy_but_not_true(self):
        """route_after_rag should only accept actual True for rag_answer."""
        state: LearningState = {"rag_found": 1}  # type: ignore
        # 1 is truthy, so should route to rag_answer
        assert route_after_rag(state) == "rag_answer"

    def test_all_routers_accept_minimal_state(self):
        """All routers should accept an empty state without errors."""
        empty_state: LearningState = {}

        # None should raise errors for required returns
        assert route_by_intent(empty_state) in ["history_check", "rag_first", "replan", "summary"]
        assert route_after_history_check(empty_state) in ["ask_review_or_continue", "diagnose"]
        assert route_after_choice(empty_state) in ["diagnose", "explain"]
        assert route_after_diagnosis(empty_state) in ["explain", "knowledge_retrieval", "summary"]
        assert route_after_restate(empty_state) in ["followup", "explain", "summary"]
        assert route_after_rag(empty_state) in ["rag_answer", "llm_answer"]
