from typing import Any

from app.skills.registry import skill_registry


def _run_skill(name: str, **kwargs: Any) -> dict[str, Any]:
    skill = skill_registry.get(name)
    if skill is None:
        return {}
    result = skill.run(**kwargs)
    return result if isinstance(result, dict) else {}


def _normalize_tool_plan(tool_plan: list[Any] | None) -> list[str] | None:
    if tool_plan is None:
        return None
    return [name.strip() for name in tool_plan if isinstance(name, str) and name.strip()]


def execute_retrieval_tools(
    *,
    query: str,
    topic: str | None,
    user_id: int | None,
    tool_route: dict[str, Any] | None,
    tool_plan: list[str] | None = None,
    top_k: int,
) -> tuple[list[dict[str, Any]], list[str]]:
    explicit_tool_plan = _normalize_tool_plan(tool_plan)
    if tool_plan is not None:
        tools_to_run = explicit_tool_plan or []
    elif tool_route is not None and "tool_plan" in tool_route:
        derived_tool_plan = _normalize_tool_plan(tool_route.get("tool_plan"))
        tools_to_run = derived_tool_plan or []
    else:
        primary_raw = (tool_route or {}).get("tool")
        primary = primary_raw.strip() if isinstance(primary_raw, str) and primary_raw.strip() else "search_local_textbook"
        tools_to_run = [primary]

    rows: list[dict[str, Any]] = []
    used_tools: list[str] = []
    for tool_name in tools_to_run:
        payload = _run_skill(
            tool_name,
            query=query,
            topic=topic,
            user_id=user_id,
            top_k=top_k,
        )
        items = payload.get("items", [])
        if isinstance(items, list) and items:
            rows.extend([{**x, "tool": tool_name} for x in items if isinstance(x, dict)])
            used_tools.append(tool_name)

    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in sorted(rows, key=lambda x: float(x.get("score", 0.0)), reverse=True):
        cid = str(row.get("chunk_id", ""))
        if cid and cid in seen:
            continue
        if cid:
            seen.add(cid)
        deduped.append(row)
        if len(deduped) >= max(1, top_k):
            break
    return deduped, used_tools

