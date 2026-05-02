"""SLO 告警评估器。

纯函数：把 SliReport + Threshold + alert_rules 列表 → Alert 列表，
可选写入日志。无定时器、无守护进程。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from slo.aggregator import SliReport
from slo.checker import check
from slo.loader import Threshold


@dataclass(frozen=True)
class Alert:
    severity: str
    sli_name: str
    actual: float
    rule_summary: str


def load_alert_rules(path: Path) -> dict[str, Any]:
    """加载 alert_rules.yaml 顶层结构。"""
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _is_near_le(actual: float, threshold: float, margin: float) -> bool:
    """direction <= 时，actual 在 [threshold * (1-margin), threshold] 内即接近。"""
    if actual > threshold:
        return False
    return actual >= threshold * (1 - margin)


def _is_near_ge(actual: float, threshold: float, margin: float) -> bool:
    """direction >= 时，actual 在 [threshold, threshold/(1-margin)] 内即接近。"""
    if actual < threshold:
        return False
    upper = threshold / (1 - margin) if margin < 1 else float("inf")
    return actual <= upper


def evaluate(
    reports: list[SliReport],
    thresholds: list[Threshold],
    rules: list[dict],
    log_path: Path | None = None,
) -> list[Alert]:
    by_name_report = {r.sli_name: r for r in reports}
    by_name_threshold = {t.name: t for t in thresholds}
    breach_set = {b.sli_name for b in check(reports, thresholds).breaches}

    alerts: list[Alert] = []
    for rule in rules:
        severity = rule.get("severity", "INFO")
        trigger = rule.get("trigger", "")
        if trigger == "near_threshold":
            margin = float(rule.get("margin", 0.10))
            for t in thresholds:
                if t.name in breach_set:
                    continue
                report = by_name_report.get(t.name)
                if report is None:
                    continue
                near = (
                    _is_near_le(report.value, t.threshold, margin)
                    if t.direction == "<="
                    else _is_near_ge(report.value, t.threshold, margin)
                )
                if near:
                    summary = (
                        f"actual {report.value:.3f} within {int(margin * 100)}% "
                        f"of {t.direction} {t.threshold} threshold"
                    )
                    alerts.append(Alert(severity, t.name, report.value, summary))
        elif trigger == "any_breach":
            for sli_name in breach_set:
                report = by_name_report.get(sli_name)
                t = by_name_threshold.get(sli_name)
                if report is None or t is None:
                    continue
                summary = (
                    f"actual {report.value:.3f} {t.direction} {t.threshold} VIOLATED"
                )
                alerts.append(Alert(severity, sli_name, report.value, summary))
        elif trigger == "hard_breach":
            sli_name = rule.get("sli", "")
            direction = rule.get("direction", "<")
            value = float(rule.get("value", 0.0))
            report = by_name_report.get(sli_name)
            if report is None:
                continue
            triggered = (
                report.value < value if direction == "<"
                else report.value > value if direction == ">"
                else False
            )
            if triggered:
                summary = f"hard breach: {report.value:.3f} {direction} {value}"
                alerts.append(Alert(severity, sli_name, report.value, summary))

    if log_path is not None and alerts:
        log_path = Path(log_path)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with log_path.open("a", encoding="utf-8") as f:
            for a in alerts:
                f.write(f"[{ts}] {a.severity} {a.sli_name}: {a.rule_summary}\n")

    return alerts
