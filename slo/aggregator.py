"""SLO 聚合：把 RunRecord 列表聚合为 SliReport 列表。

纯函数，无 IO。聚合规则文档化在 plan #017。
"""
from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class RunRecord:
    item_id: str
    category: str
    success: bool
    accept_latency_ms: float
    first_token_latency_ms: float
    completion_latency_ms: float
    has_citations: bool
    expected_citations: bool
    rag_low_evidence: bool
    reply_has_disclaimer: bool


@dataclass(frozen=True)
class SliReport:
    sli_name: str
    aggregation: str
    value: float
    sample_size: int


def _percentile(sorted_values: list[float], pct: float) -> float:
    if not sorted_values:
        raise ValueError("percentile on empty list")
    n = len(sorted_values)
    idx = max(0, min(n - 1, math.ceil(pct * n) - 1))
    return float(sorted_values[idx])


def aggregate(records: list[RunRecord]) -> list[SliReport]:
    if not records:
        raise ValueError("aggregate(records) called on empty list")

    n = len(records)
    accept = sorted(r.accept_latency_ms for r in records)
    first_tok = sorted(r.first_token_latency_ms for r in records)
    complete = sorted(r.completion_latency_ms for r in records)

    success_rate = sum(1 for r in records if r.success) / n

    expected_total = sum(1 for r in records if r.expected_citations)
    cited_hits = sum(1 for r in records if r.expected_citations and r.has_citations)
    citation_coverage = (cited_hits / expected_total) if expected_total > 0 else 1.0

    low_ev_total = sum(1 for r in records if r.rag_low_evidence)
    disclaim_hits = sum(
        1 for r in records if r.rag_low_evidence and r.reply_has_disclaimer
    )
    disclaim_rate = (disclaim_hits / low_ev_total) if low_ev_total > 0 else 1.0

    return [
        SliReport("accept_latency_ms", "p95", _percentile(accept, 0.95), n),
        SliReport("first_token_latency_ms", "p95", _percentile(first_tok, 0.95), n),
        SliReport("completion_latency_ms", "p95", _percentile(complete, 0.95), n),
        SliReport("task_success_rate", "ratio", success_rate, n),
        SliReport("citation_coverage", "ratio", citation_coverage, n),
        SliReport("low_evidence_disclaim_rate", "ratio", disclaim_rate, n),
    ]
