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
from slo.aggregator import RunRecord
from slo.run_regression import _run_one as _default_run_one

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


# 间接绑定，便于测试 monkeypatch
_run_one = _default_run_one


def _collect_samples(items: list[RegressionItem], rounds: int) -> list[RunRecord]:
    """跑 rounds 轮 12 题回归，返回 rounds × len(items) 条 RunRecord。"""
    records: list[RunRecord] = []
    total = rounds * len(items)
    n = 0
    for round_idx in range(rounds):
        for item in items:
            n += 1
            print(f"  [{n:3d}/{total}] round={round_idx + 1} {item.id} ({item.category})")
            records.append(_run_one(item))
    return records


def _extract_sli_value(sli_name: str, record: RunRecord) -> float:
    """从单条 RunRecord 提取该 SLI 的样本值。

    时延类直接取字段；ratio 类按 1/0 规则展开（与 aggregator 的 ratio 语义一致）。
    """
    if sli_name == "accept_latency_ms":
        return float(record.accept_latency_ms)
    if sli_name == "first_token_latency_ms":
        return float(record.first_token_latency_ms)
    if sli_name == "completion_latency_ms":
        return float(record.completion_latency_ms)
    if sli_name == "task_success_rate":
        return 1.0 if record.success else 0.0
    if sli_name == "citation_coverage":
        # 与 aggregator 一致：仅在 expected_citations=True 时计入；其余记 1.0 不影响
        if not record.expected_citations:
            return 1.0
        return 1.0 if record.has_citations else 0.0
    if sli_name == "low_evidence_disclaim_rate":
        # 与 aggregator 一致：仅在 rag_low_evidence=True 时计入
        if not record.rag_low_evidence:
            return 1.0
        return 1.0 if record.reply_has_disclaimer else 0.0
    raise ValueError(f"unknown sli_name: {sli_name!r}")
