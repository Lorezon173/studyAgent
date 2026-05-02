"""Phase 3c Task 2：SLO aggregator 计算。"""
import pytest

from slo.aggregator import RunRecord, aggregate, SliReport


def _make_record(**overrides) -> RunRecord:
    base = dict(
        item_id="x",
        category="factual",
        success=True,
        accept_latency_ms=0.0,
        first_token_latency_ms=100.0,
        completion_latency_ms=1000.0,
        has_citations=True,
        expected_citations=True,
        rag_low_evidence=False,
        reply_has_disclaimer=False,
    )
    base.update(overrides)
    return RunRecord(**base)


def test_aggregate_p95_completion_latency():
    records = [
        _make_record(completion_latency_ms=v) for v in
        [100, 200, 300, 400, 500, 600, 700, 800, 900, 1000,
         1100, 1200, 1300, 1400, 1500, 1600, 1700, 1800, 1900, 2000]
    ]
    reports = {r.sli_name: r for r in aggregate(records)}
    p95 = reports["completion_latency_ms"]
    assert p95.aggregation == "p95"
    # 20 个样本 P95 = index 18 (0-based) = 1900
    assert p95.value == 1900.0
    assert p95.sample_size == 20


def test_aggregate_task_success_rate():
    records = [_make_record(success=s) for s in [True] * 9 + [False]]
    reports = {r.sli_name: r for r in aggregate(records)}
    assert reports["task_success_rate"].value == 0.9


def test_citation_coverage_only_counts_expected_items():
    """规划题/总结题 expected_citations=False，不应拉低分母。"""
    records = [
        _make_record(expected_citations=True, has_citations=True),
        _make_record(expected_citations=True, has_citations=False),
        _make_record(expected_citations=False, has_citations=False),
        _make_record(expected_citations=False, has_citations=False),
    ]
    reports = {r.sli_name: r for r in aggregate(records)}
    assert reports["citation_coverage"].value == 0.5


def test_low_evidence_disclaim_rate_with_zero_low_evidence_returns_one():
    """无任何低证据样本时，覆盖率视为 1.0（vacuously true）。"""
    records = [_make_record(rag_low_evidence=False) for _ in range(5)]
    reports = {r.sli_name: r for r in aggregate(records)}
    assert reports["low_evidence_disclaim_rate"].value == 1.0


def test_low_evidence_disclaim_rate_partial():
    records = [
        _make_record(rag_low_evidence=True, reply_has_disclaimer=True),
        _make_record(rag_low_evidence=True, reply_has_disclaimer=True),
        _make_record(rag_low_evidence=True, reply_has_disclaimer=False),
        _make_record(rag_low_evidence=False),
    ]
    reports = {r.sli_name: r for r in aggregate(records)}
    assert abs(reports["low_evidence_disclaim_rate"].value - 2 / 3) < 1e-9


def test_aggregate_emits_six_reports():
    records = [_make_record() for _ in range(3)]
    reports = aggregate(records)
    names = {r.sli_name for r in reports}
    assert names == {
        "accept_latency_ms",
        "first_token_latency_ms",
        "completion_latency_ms",
        "task_success_rate",
        "citation_coverage",
        "low_evidence_disclaim_rate",
    }


def test_aggregate_raises_on_empty_records():
    with pytest.raises(ValueError, match="empty"):
        aggregate([])
