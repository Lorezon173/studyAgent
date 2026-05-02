"""节点共享工具：时间戳、追踪等内部辅助函数。"""

from datetime import datetime, UTC

from app.agent.state import LearningState


def _get_timestamp() -> str:
    """获取ISO格式时间戳"""
    return datetime.now(UTC).isoformat()


def _append_trace(state: LearningState, phase: str, data: dict) -> None:
    """追加执行追踪。"""
    label = phase
    payload = data
    try:
        from app.agent.node_registry import get_registry
        from app.monitoring.desensitize import sanitize_metadata

        meta, _fn = get_registry().get(phase)
        label = meta.trace_label or phase
        if meta.sensitive:
            payload = sanitize_metadata(data)
    except KeyError:
        if phase.endswith("_error"):
            try:
                base_phase = phase[:-6]
                meta, _fn = get_registry().get(base_phase)
                if meta.sensitive:
                    payload = sanitize_metadata(data)
            except KeyError:
                pass

    # Phase 7 Task 3：阻断超长字符串撑爆 branch_trace
    from app.monitoring.desensitize import truncate_payload
    payload = truncate_payload(payload)

    traces = state.get("branch_trace", [])
    traces.append({
        "phase": label,
        "timestamp": _get_timestamp(),
        **payload
    })
    state["branch_trace"] = traces


def _rule_based_route(user_input: str) -> str:
    """基于规则的意图路由"""
    text = user_input.lower()
    if any(k in text for k in ["重规划", "replan", "换个目标", "重新计划"]):
        return "replan"
    if any(k in text for k in ["总结", "复盘", "回顾", "review"]):
        return "review"
    if any(k in text for k in ["为什么", "怎么", "是什么", "?", "？", "请直接回答"]):
        return "qa_direct"
    return "teach_loop"
