"""Phase 3d Task 1：alert_evaluator 触发与日志。"""
from pathlib import Path
import pytest

from slo.aggregator import SliReport
from slo.loader import Threshold
from slo.alert_evaluator import Alert, evaluate, load_alert_rules


REPO_ROOT = Path(__file__).resolve().parent.parent


def _info_rule():
    return [{"severity": "INFO", "trigger": "near_threshold", "margin": 0.10}]


def _warn_rule():
    return [{"severity": "WARN", "trigger": "any_breach"}]


def _crit_rule():
    return [
        {
            "severity": "CRIT",
            "trigger": "hard_breach",
            "sli": "task_success_rate",
            "direction": "<",
            "value": 0.90,
        }
    ]


def test_load_alert_rules_from_yaml():
    rules_data = load_alert_rules(REPO_ROOT / "slo" / "alert_rules.yaml")
    assert rules_data["version"] == "v1"
    assert "severity_rules" in rules_data
    severities = {r["severity"] for r in rules_data["severity_rules"]}
    assert severities == {"INFO", "WARN", "CRIT"}


def test_no_alert_when_all_within_safe_zone():
    """所有 actual 距阈值 > 10%，不触发任何 alert。"""
    thresholds = [Threshold("completion_latency_ms", "<=", 1000, "p95")]
    reports = [SliReport("completion_latency_ms", "p95", 500, 12)]
    alerts = evaluate(reports, thresholds, _info_rule() + _warn_rule())
    assert alerts == []


def test_info_when_near_le_threshold():
    """direction <= 时 actual 在 [threshold*0.9, threshold] 内触发 INFO。"""
    thresholds = [Threshold("completion_latency_ms", "<=", 1000, "p95")]
    reports = [SliReport("completion_latency_ms", "p95", 950, 12)]
    alerts = evaluate(reports, thresholds, _info_rule())
    assert len(alerts) == 1
    assert alerts[0].severity == "INFO"
    assert alerts[0].sli_name == "completion_latency_ms"


def test_info_when_near_ge_threshold():
    """direction >= 时 actual 在 [threshold, threshold/(1-margin)] 内触发 INFO。"""
    thresholds = [Threshold("task_success_rate", ">=", 0.97, "ratio")]
    reports = [SliReport("task_success_rate", "ratio", 0.975, 12)]
    alerts = evaluate(reports, thresholds, _info_rule())
    assert len(alerts) == 1
    assert alerts[0].severity == "INFO"


def test_warn_when_any_breach():
    """超阈值的 SLI 触发 WARN（不再触发 INFO）。"""
    thresholds = [
        Threshold("completion_latency_ms", "<=", 1000, "p95"),
        Threshold("task_success_rate", ">=", 0.97, "ratio"),
    ]
    reports = [
        SliReport("completion_latency_ms", "p95", 1500, 12),
        SliReport("task_success_rate", "ratio", 0.99, 12),
    ]
    alerts = evaluate(reports, thresholds, _info_rule() + _warn_rule())
    severities = [a.severity for a in alerts]
    assert "WARN" in severities
    breached = [a for a in alerts if a.sli_name == "completion_latency_ms"]
    assert {a.severity for a in breached} == {"WARN"}


def test_crit_when_task_success_rate_below_hard_threshold():
    """task_success_rate < 0.90 触发 CRIT，绕过 thresholds.yaml。"""
    thresholds = [Threshold("task_success_rate", ">=", 0.97, "ratio")]
    reports = [SliReport("task_success_rate", "ratio", 0.85, 12)]
    alerts = evaluate(reports, thresholds, _warn_rule() + _crit_rule())
    severities = [a.severity for a in alerts]
    assert "CRIT" in severities
    assert "WARN" in severities


def test_evaluator_writes_log(tmp_path):
    """alerts 写日志（每条一行）。"""
    log = tmp_path / "alerts.log"
    thresholds = [Threshold("completion_latency_ms", "<=", 1000, "p95")]
    reports = [SliReport("completion_latency_ms", "p95", 1500, 12)]
    alerts = evaluate(reports, thresholds, _warn_rule(), log_path=log)
    assert len(alerts) == 1
    contents = log.read_text(encoding="utf-8")
    assert "WARN" in contents
    assert "completion_latency_ms" in contents
    assert contents.strip().startswith("[")


def test_evaluator_creates_log_parent_dir(tmp_path):
    """log_path 父目录不存在时应自动创建。"""
    log = tmp_path / "deep" / "nested" / "alerts.log"
    thresholds = [Threshold("task_success_rate", ">=", 0.97, "ratio")]
    reports = [SliReport("task_success_rate", "ratio", 0.85, 12)]
    evaluate(reports, thresholds, _warn_rule(), log_path=log)
    assert log.exists()


def test_evaluator_returns_empty_when_no_rules():
    thresholds = [Threshold("completion_latency_ms", "<=", 1000, "p95")]
    reports = [SliReport("completion_latency_ms", "p95", 1500, 12)]
    alerts = evaluate(reports, thresholds, [])
    assert alerts == []
