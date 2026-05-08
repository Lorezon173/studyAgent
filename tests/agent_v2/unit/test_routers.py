"""路由函数单元测试。"""
import pytest
from app.agent.routers import (
    route_by_intent,
    route_after_history_check,
    route_after_choice,
    route_after_diagnosis,
    route_after_restate,
    route_after_rag,
    route_after_evidence_gate,
    route_on_error_or_evidence,
    route_on_error_or_explain,
)
from app.agent.state import LearningState


# ========== route_by_intent ==========

def test_route_by_intent_teach_loop():
    state: LearningState = {"intent": "teach_loop"}
    assert route_by_intent(state) == "history_check"


def test_route_by_intent_qa_direct():
    state: LearningState = {"intent": "qa_direct"}
    assert route_by_intent(state) == "rag_first"


def test_route_by_intent_replan():
    state: LearningState = {"intent": "replan"}
    assert route_by_intent(state) == "replan"


def test_route_by_intent_review():
    state: LearningState = {"intent": "review"}
    assert route_by_intent(state) == "summary"


def test_route_by_intent_default():
    state: LearningState = {}  # 无 intent
    assert route_by_intent(state) == "history_check"


# ========== route_after_history_check ==========

def test_route_after_history_check_has_history():
    state: LearningState = {"has_history": True}
    assert route_after_history_check(state) == "ask_review_or_continue"


def test_route_after_history_check_no_history():
    state: LearningState = {"has_history": False}
    assert route_after_history_check(state) == "diagnose"


# ========== route_after_choice ==========

def test_route_after_choice_review():
    state: LearningState = {"user_choice": "review"}
    assert route_after_choice(state) == "diagnose"


def test_route_after_choice_continue():
    state: LearningState = {"user_choice": "continue"}
    assert route_after_choice(state) == "explain"


# ========== route_after_diagnosis ==========

def test_route_after_diagnosis_mastered():
    state: LearningState = {"diagnosis": "用户已掌握该知识点"}
    assert route_after_diagnosis(state) == "summary"


def test_route_after_diagnosis_familiar():
    state: LearningState = {"diagnosis": "用户对该主题比较熟悉"}
    assert route_after_diagnosis(state) == "summary"


def test_route_after_diagnosis_need_materials():
    state: LearningState = {"diagnosis": "需要补充外部资料"}
    assert route_after_diagnosis(state) == "knowledge_retrieval"


def test_route_after_diagnosis_normal():
    state: LearningState = {"diagnosis": "用户理解程度一般"}
    assert route_after_diagnosis(state) == "explain"


# ========== route_after_restate ==========

def test_route_after_restate_understood():
    state: LearningState = {"restatement_eval": "复述已理解且准确"}
    assert route_after_restate(state) == "summary"


def test_route_after_restate_correct():
    state: LearningState = {"restatement_eval": "复述正确完整"}
    assert route_after_restate(state) == "summary"


def test_route_after_restate_wrong_retry():
    state: LearningState = {"restatement_eval": "存在错误理解", "explain_loop_count": 0}
    result = route_after_restate(state)
    assert result == "explain"
    assert state["explain_loop_count"] == 1


def test_route_after_restate_wrong_max_retry():
    state: LearningState = {"restatement_eval": "存在混淆", "explain_loop_count": 3}
    result = route_after_restate(state)
    assert result == "followup"  # 已达最大重试次数


def test_route_after_restate_partial():
    # 不包含"已理解/准确/完整/正确"也不包含"错误/混淆/误解/不清楚"
    state: LearningState = {"restatement_eval": "一般，还需加强"}
    assert route_after_restate(state) == "followup"


# ========== route_after_rag ==========

def test_route_after_rag_found():
    state: LearningState = {"rag_found": True, "rag_confidence_level": "high"}
    assert route_after_rag(state) == "rag_answer"


def test_route_after_rag_not_found():
    state: LearningState = {"rag_found": False}
    assert route_after_rag(state) == "llm_answer"


def test_route_after_rag_low_confidence():
    state: LearningState = {"rag_found": True, "rag_confidence_level": "low"}
    assert route_after_rag(state) == "llm_answer"


# ========== route_after_evidence_gate ==========

def test_route_after_evidence_gate_pass():
    state: LearningState = {"gate_status": "pass"}
    assert route_after_evidence_gate(state) == "answer_policy"


def test_route_after_evidence_gate_supplement():
    state: LearningState = {"gate_status": "supplement"}
    assert route_after_evidence_gate(state) == "answer_policy"


def test_route_after_evidence_gate_reject():
    state: LearningState = {"gate_status": "reject"}
    assert route_after_evidence_gate(state) == "recovery"


# ========== route_on_error_or_evidence ==========

def test_route_on_error_or_evidence_no_error():
    state: LearningState = {}
    assert route_on_error_or_evidence(state) == "evidence_gate"


def test_route_on_error_or_evidence_with_error():
    # llm_timeout 可能是 retryable，添加 retry_trace 确保进入 recovery
    state: LearningState = {"node_error": "LLM timeout", "error_code": "llm_timeout", "retry_trace": ["rag_first"]}
    assert route_on_error_or_evidence(state) == "recovery"


# ========== route_on_error_or_explain ==========

def test_route_on_error_or_explain_no_error():
    state: LearningState = {}
    assert route_on_error_or_explain(state) == "explain"


def test_route_on_error_or_explain_with_error():
    state: LearningState = {"node_error": "RAG failure", "error_code": "rag_failure"}
    assert route_on_error_or_explain(state) == "recovery"
