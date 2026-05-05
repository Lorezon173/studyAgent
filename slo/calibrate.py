"""SLO v2 阈值校准工具（plan #020）。

跑 N 轮真实 LLM 回归 -> 计算 p50/p95/p99 -> 按 le/ge 方向推算 v2 阈值 -> 写报表 JSON。

不自动改 thresholds.yaml；yaml 变更必须经 PR review（spec §5）。

Usage:
    uv run python -m slo.calibrate --rounds 5 --output reports/slo-calibration-v2.json
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal

from slo.loader import RegressionItem, Threshold, load_regression_set, load_thresholds

DEFAULT_MARGIN = 0.20
DEFAULT_ROUNDS = 5

# SLI -> 方向。le = 越小越好（时延），ge = 越大越好（成功率/覆盖率）。
SLI_DIRECTIONS: dict[str, Literal["<=", ">="]] = {
    "accept_latency_ms": "<=",
    "first_token_latency_ms": "<=",
    "completion_latency_ms": "<=",
    "task_success_rate": ">=",
    "citation_coverage": ">=",
    "low_evidence_disclaim_rate": ">=",
}

_REPO_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_THRESHOLDS_PATH = _REPO_ROOT / "slo" / "thresholds.yaml"
_DEFAULT_REGRESSION_PATH = _REPO_ROOT / "slo" / "regression_set.yaml"


def _percentile(samples: list[float], pct: float) -> float:
    """与 slo.aggregator._percentile 一致的算法（向上取整 - 1）。

    保持算法一致性，避免 calibrate 推算值和 aggregator 实测值漂移。
    """
    if not samples:
        raise ValueError("percentile on empty list")
    sorted_vals = sorted(samples)
    n = len(sorted_vals)
    idx = max(0, min(n - 1, math.ceil(pct * n) - 1))
    return float(sorted_vals[idx])


def _recommend_v2(
    direction: Literal["<=", ">="],
    v1_threshold: float,
    p95_actual: float,
    margin: float,
) -> float:
    """根据方向与 margin 推算 v2 阈值（spec §3.4 / §3.5）。

    le（"<="）: v2 = max(p95_actual * (1 + margin), v1)  — 不收紧实测做不到的
    ge（">="）: v2 = max(p95_actual * (1 - margin), v1)  — 不允许低于 v1（不放水）
    """
    if direction == "<=":
        relaxed = p95_actual * (1.0 + margin)
        return max(relaxed, v1_threshold)
    elif direction == ">=":
        tightened = p95_actual * (1.0 - margin)
        return max(tightened, v1_threshold)
    else:
        raise ValueError(f"unknown direction: {direction!r}")
