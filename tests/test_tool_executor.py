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


def test_execute_retrieval_tools_ignores_invalid_tool_plan_entries(monkeypatch):
    called_tools: list[str] = []

    def fake_run_skill(name: str, **kwargs):
        called_tools.append(name)
        return {
            "items": [
                {
                    "chunk_id": f"{name}-1",
                    "text": f"from-{name}",
                    "score": 0.7,
                }
            ]
        }

    monkeypatch.setattr("app.services.tool_executor._run_skill", fake_run_skill)

    rows, used_tools = execute_retrieval_tools(
        query="解释二分查找",
        topic="二分查找",
        user_id=123,
        tool_route={"tool": "search_local_textbook"},
        tool_plan=[None, "", "  ", "search_personal_memory"],
        top_k=3,
    )

    assert called_tools == ["search_personal_memory"]
    assert used_tools == ["search_personal_memory"]
    assert all(row.get("tool") == "search_personal_memory" for row in rows)


def test_execute_retrieval_tools_without_plan_runs_only_primary_tool(monkeypatch):
    called_tools: list[str] = []

    def fake_run_skill(name: str, **kwargs):
        called_tools.append(name)
        return {
            "items": [
                {
                    "chunk_id": f"{name}-1",
                    "text": f"from-{name}",
                    "score": 0.8,
                }
            ]
        }

    monkeypatch.setattr("app.services.tool_executor._run_skill", fake_run_skill)

    rows, used_tools = execute_retrieval_tools(
        query="解释二分查找",
        topic="二分查找",
        user_id=123,
        tool_route={"tool": "search_local_textbook"},
        tool_plan=None,
        top_k=3,
    )

    assert called_tools == ["search_local_textbook"]
    assert used_tools == ["search_local_textbook"]
    assert all(row.get("tool") == "search_local_textbook" for row in rows)


def test_execute_retrieval_tools_with_explicit_empty_plan_runs_nothing(monkeypatch):
    called_tools: list[str] = []

    def fake_run_skill(name: str, **kwargs):
        called_tools.append(name)
        return {"items": [{"chunk_id": f"{name}-1", "text": f"from-{name}", "score": 0.8}]}

    monkeypatch.setattr("app.services.tool_executor._run_skill", fake_run_skill)

    rows, used_tools = execute_retrieval_tools(
        query="解释二分查找",
        topic="二分查找",
        user_id=123,
        tool_route={"tool": "search_local_textbook"},
        tool_plan=[],
        top_k=3,
    )

    assert called_tools == []
    assert rows == []
    assert used_tools == []


def test_execute_retrieval_tools_with_explicit_all_invalid_plan_runs_nothing(monkeypatch):
    called_tools: list[str] = []

    def fake_run_skill(name: str, **kwargs):
        called_tools.append(name)
        return {"items": [{"chunk_id": f"{name}-1", "text": f"from-{name}", "score": 0.8}]}

    monkeypatch.setattr("app.services.tool_executor._run_skill", fake_run_skill)

    rows, used_tools = execute_retrieval_tools(
        query="解释二分查找",
        topic="二分查找",
        user_id=123,
        tool_route={"tool": "search_local_textbook"},
        tool_plan=[None, "", "  "],
        top_k=3,
    )

    assert called_tools == []
    assert rows == []
    assert used_tools == []
