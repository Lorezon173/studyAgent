from app.services.rag_coordinator import execute_rag


def test_execute_rag_uses_query_plan(monkeypatch):
    monkeypatch.setattr(
        "app.services.rag_coordinator.build_query_plan",
        lambda user_input, topic: type(
            "P",
            (),
            {
                "mode": "freshness",
                "rewritten_query": "LangGraph 最新版本",
                "top_k": 5,
                "enable_web": True,
                "reason": "test",
            },
        )(),
    )
    monkeypatch.setattr(
        "app.services.rag_coordinator.execute_retrieval_tools",
        lambda **kwargs: ([{"chunk_id": "c1", "text": "x", "score": 1.0}], ["search_web"]),
    )

    rows, meta = execute_rag(query="LangGraph 最新版本", topic="框架", user_id=1, tool_route=None, top_k=2)
    assert rows
    assert meta.hit_count == 1
    assert meta.reason == "tool_retrieval"
    assert meta.used_tools == ["search_web"]
    assert meta.query_mode == "freshness"
