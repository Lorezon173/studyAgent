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
