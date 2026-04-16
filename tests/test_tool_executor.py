from app.services.tool_executor import execute_retrieval_tools


def test_execute_retrieval_tools_obeys_explicit_tool_plan(monkeypatch):
    def fake_run_skill(name: str, **kwargs):
        return {
            "items": [
                {
                    "chunk_id": f"{name}-1",
                    "text": f"from-{name}",
                    "score": 0.9,
                }
            ]
        }

    monkeypatch.setattr("app.services.tool_executor._run_skill", fake_run_skill)

    rows, used_tools = execute_retrieval_tools(
        query="解释二分查找",
        topic="二分查找",
        user_id=123,
        tool_route={"tool": "search_local_textbook"},
        tool_plan=["search_personal_memory"],
        top_k=3,
    )

    assert used_tools == ["search_personal_memory"]
    assert all(row.get("tool") == "search_personal_memory" for row in rows)
