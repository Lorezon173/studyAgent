"""Orchestrator Eval Subagent 单元测试。"""
import json
from app.agent.system_eval.orchestrator_eval import orchestrator_eval_node


def test_orchestrator_eval_correct_intent(monkeypatch):
    """意图识别正确时，intent_accuracy 应为 100。"""
    monkeypatch.setattr(
        "app.services.llm.llm_service.invoke",
        lambda system_prompt, user_prompt, stream_output=False: json.dumps({
            "is_correct": True, "should_be": "teach_loop", "reason": "匹配",
        }),
    )

    result = orchestrator_eval_node({
        "session_id": "sess-1",
        "user_input": "我想学二分查找",
        "detected_intent": "teach_loop",
        "task_queue": [{"type": "teach"}, {"type": "evaluate"}],
        "teaching_eval_result": {"teaching_score": 80.0},
        "actual_flow": ["teaching_agent", "eval_agent"],
        "response_time_ms": 150.0,
    })

    assert result["session_id"] == "sess-1"
    assert result["intent_accuracy"] == 100.0
    assert result["routing_score"] >= 60.0
    assert result["orchestrator_score"] > 0
    assert isinstance(result["improvement_suggestions"], list)


def test_orchestrator_eval_wrong_intent(monkeypatch):
    """意图识别错误时，intent_accuracy 应为 50。"""
    monkeypatch.setattr(
        "app.services.llm.llm_service.invoke",
        lambda system_prompt, user_prompt, stream_output=False: json.dumps({
            "is_correct": False, "should_be": "qa_direct", "reason": "应是问答",
        }),
    )

    result = orchestrator_eval_node({
        "session_id": "sess-2",
        "user_input": "二分查找的时间复杂度是什么？",
        "detected_intent": "teach_loop",
        "task_queue": [{"type": "teach"}],
        "teaching_eval_result": {"teaching_score": 40.0},
        "actual_flow": ["teaching_agent"],
        "response_time_ms": 200.0,
    })

    assert result["intent_accuracy"] == 50.0
