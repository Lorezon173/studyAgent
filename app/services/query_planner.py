from dataclasses import dataclass


@dataclass(frozen=True)
class QueryPlan:
    mode: str
    rewritten_query: str
    top_k: int
    enable_web: bool
    reason: str


def build_query_plan(user_input: str, topic: str | None) -> QueryPlan:
    text = (user_input or "").strip()
    lowered = text.lower()
    if any(k in lowered for k in ["最新", "最近", "release", "版本", "today", "this week"]):
        return QueryPlan(
            mode="freshness",
            rewritten_query=f"{text} {topic or ''}".strip(),
            top_k=5,
            enable_web=True,
            reason="freshness_signal_detected",
        )
    if any(k in text for k in ["对比", "区别", "优缺点"]):
        return QueryPlan(
            mode="comparison",
            rewritten_query=text,
            top_k=5,
            enable_web=False,
            reason="comparison_signal_detected",
        )
    return QueryPlan(
        mode="fact",
        rewritten_query=text,
        top_k=3,
        enable_web=False,
        reason="default_fact_mode",
    )
