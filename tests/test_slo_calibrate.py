"""SLO v2 calibrate 工具单元测试（plan #020）。"""
import pytest

import slo.calibrate as cal


def test_module_exports_constants():
    assert cal.DEFAULT_MARGIN == 0.20
    assert cal.DEFAULT_ROUNDS == 5
    assert set(cal.SLI_DIRECTIONS.keys()) == {
        "accept_latency_ms",
        "first_token_latency_ms",
        "completion_latency_ms",
        "task_success_rate",
        "citation_coverage",
        "low_evidence_disclaim_rate",
    }
    assert cal.SLI_DIRECTIONS["accept_latency_ms"] == "<="
    assert cal.SLI_DIRECTIONS["task_success_rate"] == ">="


# ---------- Task 3: _percentile ----------

def test_percentile_basic():
    samples = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
    assert cal._percentile(samples, 0.5) == 5.0
    assert cal._percentile(samples, 0.95) == 10.0


def test_percentile_single_sample():
    assert cal._percentile([3.14], 0.95) == 3.14


def test_percentile_empty_raises():
    with pytest.raises(ValueError):
        cal._percentile([], 0.95)


# ---------- Task 3: _recommend_v2 (le direction) ----------

def test_recommend_v2_le_actual_higher_than_v1_relaxes_to_actual_with_margin():
    # accept ≤ 500（v1）；实测 p95 = 1000，margin 0.2 → v2 应 = 1200
    v2 = cal._recommend_v2(
        direction="<=", v1_threshold=500.0, p95_actual=1000.0, margin=0.20
    )
    assert v2 == 1200.0


def test_recommend_v2_le_actual_lower_than_v1_keeps_v1():
    # 实测优于 v1，不收紧（保留 v1 而非 actual×1.2）
    # actual×1.2 = 120 < 500，按 spec §3.5: max(120, 500) = 500
    v2 = cal._recommend_v2(
        direction="<=", v1_threshold=500.0, p95_actual=100.0, margin=0.20
    )
    assert v2 == 500.0


# ---------- Task 3: _recommend_v2 (ge direction) ----------

def test_recommend_v2_ge_actual_well_above_v1_can_tighten_via_margin():
    # task_success ≥ 0.97（v1）；实测 p95 = 1.00，margin 0.2 → actual×0.8 = 0.80 < 0.97 → v2 = 0.97
    v2 = cal._recommend_v2(
        direction=">=", v1_threshold=0.97, p95_actual=1.00, margin=0.20
    )
    assert v2 == 0.97


def test_recommend_v2_ge_actual_extremely_high_could_lift_threshold():
    # 实测 p95 远高于 v1：actual×0.8 > v1，按 spec §3.4 max(actual×0.8, v1)
    # 例：v1=0.50，actual=1.00，margin=0.2 → 0.80 > 0.50 → v2=0.80
    v2 = cal._recommend_v2(
        direction=">=", v1_threshold=0.50, p95_actual=1.00, margin=0.20
    )
    assert v2 == 0.80

