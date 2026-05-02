"""Phase 3c Task 1：SLO loader 解析 YAML。"""
from pathlib import Path
import pytest

from slo.loader import (
    Threshold,
    RegressionItem,
    load_thresholds,
    load_regression_set,
)


REPO_ROOT = Path(__file__).resolve().parent.parent


def test_load_thresholds_returns_six_v1_slis():
    thresholds = load_thresholds(REPO_ROOT / "slo" / "thresholds.yaml")
    assert len(thresholds) == 6
    names = {t.name for t in thresholds}
    assert names == {
        "accept_latency_ms",
        "first_token_latency_ms",
        "completion_latency_ms",
        "task_success_rate",
        "citation_coverage",
        "low_evidence_disclaim_rate",
    }


def test_load_thresholds_parses_direction_and_aggregation():
    thresholds = load_thresholds(REPO_ROOT / "slo" / "thresholds.yaml")
    by_name = {t.name: t for t in thresholds}
    assert by_name["completion_latency_ms"].direction == "<="
    assert by_name["completion_latency_ms"].aggregation == "p95"
    assert by_name["completion_latency_ms"].threshold == 15000
    assert by_name["task_success_rate"].direction == ">="
    assert by_name["task_success_rate"].aggregation == "ratio"
    assert by_name["task_success_rate"].threshold == 0.97


def test_load_regression_set_returns_twelve_items_in_four_categories():
    items = load_regression_set(REPO_ROOT / "slo" / "regression_set.yaml")
    assert len(items) == 12
    categories = {it.category for it in items}
    assert categories == {"factual", "compare", "summary", "planning"}


def test_load_regression_item_carries_expects_citations():
    items = load_regression_set(REPO_ROOT / "slo" / "regression_set.yaml")
    fact_items = [it for it in items if it.category == "factual"]
    summary_items = [it for it in items if it.category == "summary"]
    assert all(it.expects_citations is True for it in fact_items)
    assert all(it.expects_citations is False for it in summary_items)


def test_load_thresholds_raises_on_missing_required_key(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "version: v1\nslis:\n  - name: foo\n    threshold: 100\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="direction"):
        load_thresholds(bad)


def test_threshold_dataclass_is_frozen():
    """Threshold 不可变，避免 aggregator/checker 误改。"""
    t = Threshold(name="x", direction="<=", threshold=1.0, aggregation="p95")
    with pytest.raises((AttributeError, TypeError)):
        t.threshold = 2.0  # type: ignore
