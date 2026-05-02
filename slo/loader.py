"""SLO YAML 加载器：阈值与回归集的纯解析逻辑。

不依赖 agent_service / langfuse / redis。
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import yaml

Direction = Literal["<=", ">="]
Aggregation = Literal["p50", "p95", "p99", "mean", "ratio"]


@dataclass(frozen=True)
class Threshold:
    name: str
    direction: Direction
    threshold: float
    aggregation: Aggregation


@dataclass(frozen=True)
class RegressionItem:
    id: str
    category: str
    user_input: str
    topic: str | None
    expects_citations: bool


def load_thresholds(path: Path) -> list[Threshold]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    slis = raw.get("slis") or []
    out: list[Threshold] = []
    for item in slis:
        for key in ("name", "direction", "threshold", "aggregation"):
            if key not in item:
                raise ValueError(f"thresholds.yaml: SLI 缺少必填字段 {key}: {item}")
        out.append(
            Threshold(
                name=str(item["name"]),
                direction=item["direction"],
                threshold=float(item["threshold"]),
                aggregation=item["aggregation"],
            )
        )
    return out


def load_regression_set(path: Path) -> list[RegressionItem]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    items = raw.get("items") or []
    out: list[RegressionItem] = []
    for item in items:
        for key in ("id", "category", "user_input", "expects_citations"):
            if key not in item:
                raise ValueError(f"regression_set.yaml: item 缺少字段 {key}: {item}")
        out.append(
            RegressionItem(
                id=str(item["id"]),
                category=str(item["category"]),
                user_input=str(item["user_input"]),
                topic=item.get("topic"),
                expects_citations=bool(item["expects_citations"]),
            )
        )
    return out
