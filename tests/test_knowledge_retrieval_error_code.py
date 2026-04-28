"""Tests for knowledge_retrieval_node typed error_code on exception."""
from unittest.mock import patch

from app.agent.nodes import knowledge_retrieval_node


def test_knowledge_retrieval_writes_error_code_on_timeout():
    state = {"user_input": "什么是B+树", "topic": "数据结构"}
    with patch(
        "app.agent.nodes.qa.execute_rag",
        side_effect=TimeoutError("timed out"),
    ):
        result = knowledge_retrieval_node(state)
    assert result.get("error_code") == "llm_timeout"
    assert result.get("node_error")


def test_knowledge_retrieval_writes_db_error_on_connection_refused():
    state = {"user_input": "什么是B+树", "topic": "数据结构"}
    with patch(
        "app.agent.nodes.qa.execute_rag",
        side_effect=RuntimeError("connection refused"),
    ):
        result = knowledge_retrieval_node(state)
    assert result.get("error_code") == "db_error"


def test_knowledge_retrieval_no_error_code_on_success():
    state = {"user_input": "什么是B+树", "topic": "数据结构"}
    fake_meta = type("M", (), {
        "reason": "ok",
        "used_tools": [],
        "hit_count": 0,
        "fallback_used": False,
        "query_mode": "fact",
        "query_reason": "test",
    })()
    with patch(
        "app.agent.nodes.qa.execute_rag",
        return_value=([], fake_meta),
    ):
        result = knowledge_retrieval_node(state)
    assert not result.get("error_code")

