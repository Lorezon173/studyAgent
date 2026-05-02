"""SLO 阈值比对：把 SliReport + Threshold 列表对齐 → CheckResult。

纯函数，无 IO。
"""
from __future__ import annotations

from dataclasses import dataclass

from slo.aggregator import SliReport
from slo.loader import Threshold


@dataclass(frozen=True)
class Breach:
    sli_name: str
    direction: str
    threshold: float
    actual: float


@dataclass(frozen=True)
class CheckResult:
    passed: bool
    breaches: list[Breach]
    skipped: list[str]


def check(reports: list[SliReport], thresholds: list[Threshold]) -> CheckResult:
    by_name = {r.sli_name: r for r in reports}
    breaches: list[Breach] = []
    skipped: list[str] = []
    for t in thresholds:
        report = by_name.get(t.name)
        if report is None:
            skipped.append(t.name)
            continue
        actual = report.value
        ok = (
            actual <= t.threshold if t.direction == "<="
            else actual >= t.threshold
        )
        if not ok:
            breaches.append(Breach(t.name, t.direction, t.threshold, actual))
    return CheckResult(passed=not breaches, breaches=breaches, skipped=skipped)
