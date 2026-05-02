"""Phase 3c Task 3：SLO checker 比对阈值。"""
from slo.aggregator import SliReport
from slo.loader import Threshold
from slo.checker import check, CheckResult, Breach


def test_all_within_threshold_passes():
    thresholds = [
        Threshold("completion_latency_ms", "<=", 15000, "p95"),
        Threshold("task_success_rate", ">=", 0.97, "ratio"),
    ]
    reports = [
        SliReport("completion_latency_ms", "p95", 12000, 12),
        SliReport("task_success_rate", "ratio", 0.99, 12),
    ]
    result = check(reports, thresholds)
    assert isinstance(result, CheckResult)
    assert result.passed is True
    assert result.breaches == []


def test_le_breach_when_actual_above_threshold():
    thresholds = [Threshold("completion_latency_ms", "<=", 15000, "p95")]
    reports = [SliReport("completion_latency_ms", "p95", 18000, 12)]
    result = check(reports, thresholds)
    assert result.passed is False
    assert result.breaches == [
        Breach("completion_latency_ms", "<=", 15000, 18000)
    ]


def test_ge_breach_when_actual_below_threshold():
    thresholds = [Threshold("task_success_rate", ">=", 0.97, "ratio")]
    reports = [SliReport("task_success_rate", "ratio", 0.85, 12)]
    result = check(reports, thresholds)
    assert result.passed is False
    assert result.breaches[0].sli_name == "task_success_rate"


def test_missing_sli_is_recorded_in_skipped_not_breach():
    """阈值定义了但 aggregator 没产出 → 计入 skipped，不算违反。"""
    thresholds = [
        Threshold("retry_recovery_rate", ">=", 0.70, "ratio"),
        Threshold("task_success_rate", ">=", 0.97, "ratio"),
    ]
    reports = [SliReport("task_success_rate", "ratio", 0.99, 12)]
    result = check(reports, thresholds)
    assert result.passed is True
    assert result.breaches == []
    assert result.skipped == ["retry_recovery_rate"]


def test_multiple_breaches_all_collected():
    thresholds = [
        Threshold("completion_latency_ms", "<=", 15000, "p95"),
        Threshold("task_success_rate", ">=", 0.97, "ratio"),
    ]
    reports = [
        SliReport("completion_latency_ms", "p95", 18000, 12),
        SliReport("task_success_rate", "ratio", 0.85, 12),
    ]
    result = check(reports, thresholds)
    assert result.passed is False
    assert len(result.breaches) == 2
