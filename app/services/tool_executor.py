from typing import Any

from app.skills.registry import skill_registry


def _run_skill(name: str, **kwargs: Any) -> dict[str, Any]:
    skill = skill_registry.get(name)
    if skill is None:
        return {}
    result = skill.run(**kwargs)
    return result if isinstance(result, dict) else {}


def execute_retrieval_tools(
    *,
    query: str,
    topic: str | None,
    user_id: int | None,
    tool_route: dict[str, Any] | None,
    tool_plan: list[str] | None = None,
    top_k: int,
) -> tuple[list[dict[str, Any]], list[str]]:
    explicit_tool_plan = tool_plan
    if explicit_tool_plan is None:
        route_tool_plan = (tool_route or {}).get("tool_plan")
        if isinstance(route_tool_plan, list):
            explicit_tool_plan = [str(x).strip() for x in route_tool_plan if str(x).strip()]

    if explicit_tool_plan is not None:
        tools_to_run = [str(x).strip() for x in explicit_tool_plan if str(x).strip()]
    else:
        primary = str((tool_route or {}).get("tool") or "search_local_textbook")
        tools_to_run = [primary]

        # 兼容旧行为：有 user_id 时仍补充 personal 轨道证据，避免召回退化。
        if user_id is not None and primary == "search_local_textbook":
            tools_to_run.append("search_personal_memory")
        elif user_id is not None and primary == "search_personal_memory":
            tools_to_run.append("search_local_textbook")

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

