"""Retrieval Agent 单元测试。"""
from app.agent.multi_agent.retrieval_agent import retrieval_agent_node


def _make_state(**overrides):
    base = {
        "session_id": "test-1",
        "user_id": 1,
        "user_input": "什么是二分查找？",
        "topic": "二分查找",
        "current_agent": "orchestrator",
        "task_queue": [],
        "completed_tasks": [],
        "teaching_output": {},
        "eval_output": {},
        "retrieval_output": {},
        "final_reply": "",
        "mastery_score": None,
        "branch_trace": [],
    }
    base.update(overrides)
    return base


def test_retrieval_agent_when_rag_enabled(monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "rag_enabled", True)

    monkeypatch.setattr(
        "app.services.rag_service.rag_service.retrieve",
        lambda query, topic, top_k: [
            {"chunk_id": "c1", "text": "二分查找每次取中间值", "score": 3, "source_type": "text", "title": "教材"},
        ],
    )
    monkeypatch.setattr(
        "app.services.rag_service.rag_service.retrieve_scoped",
        lambda query, scope, user_id, topic, top_k: [],
    )

    state = _make_state(user_id=1)
    result = retrieval_agent_node(state)
    assert "retrieval_output" in result
    assert result["retrieval_output"]["rag_found"] is True
    assert len(result["retrieval_output"]["citations"]) > 0


def test_retrieval_agent_when_rag_disabled(monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "rag_enabled", False)

    state = _make_state()
    result = retrieval_agent_node(state)
    assert result["retrieval_output"]["rag_found"] is False
