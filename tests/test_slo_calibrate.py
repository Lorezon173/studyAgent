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


# ---------- Task 4: _collect_samples ----------

def test_collect_samples_single_round_calls_run_one_per_item(monkeypatch):
    """rounds=1, items=3 → _run_one 被调 3 次，返回 3 个 RunRecord。"""
    from slo.aggregator import RunRecord
    from slo.loader import RegressionItem

    items = [
        RegressionItem(id=f"i{i}", category="factual", user_input="q",
                       topic=None, expects_citations=True)
        for i in range(3)
    ]
    call_count = {"n": 0}

    def fake_run_one(item):
        call_count["n"] += 1
        return RunRecord(
            item_id=item.id, category=item.category, success=True,
            accept_latency_ms=10.0, first_token_latency_ms=200.0,
            completion_latency_ms=1500.0, has_citations=True,
            expected_citations=True, rag_low_evidence=False,
            reply_has_disclaimer=False,
        )

    monkeypatch.setattr(cal, "_run_one", fake_run_one)
    records = cal._collect_samples(items, rounds=1)
    assert len(records) == 3
    assert call_count["n"] == 3


def test_collect_samples_multiple_rounds(monkeypatch):
    from slo.aggregator import RunRecord
    from slo.loader import RegressionItem

    items = [RegressionItem(id="i0", category="factual", user_input="q",
                            topic=None, expects_citations=False)]

    def fake_run_one(item):
        return RunRecord(
            item_id=item.id, category=item.category, success=True,
            accept_latency_ms=0.0, first_token_latency_ms=0.0,
            completion_latency_ms=0.0, has_citations=False,
            expected_citations=False, rag_low_evidence=False,
            reply_has_disclaimer=False,
        )

    monkeypatch.setattr(cal, "_run_one", fake_run_one)
    records = cal._collect_samples(items, rounds=3)
    assert len(records) == 3  # 1 题 × 3 轮


# ---------- Task 4: _extract_sli_value ----------

def test_extract_sli_value_latency_uses_field():
    from slo.aggregator import RunRecord
    rec = RunRecord(
        item_id="i0", category="factual", success=True,
        accept_latency_ms=12.0, first_token_latency_ms=300.0,
        completion_latency_ms=1500.0, has_citations=True,
        expected_citations=True, rag_low_evidence=False,
        reply_has_disclaimer=False,
    )
    assert cal._extract_sli_value("accept_latency_ms", rec) == 12.0
    assert cal._extract_sli_value("first_token_latency_ms", rec) == 300.0
    assert cal._extract_sli_value("completion_latency_ms", rec) == 1500.0


def test_extract_sli_value_rates_return_one_or_zero():
    """ratio 类 SLI 在单条 record 上转成 0/1 样本（计算 p95 时聚合）。"""
    from slo.aggregator import RunRecord
    rec_pass = RunRecord(
        item_id="i0", category="factual", success=True,
        accept_latency_ms=0.0, first_token_latency_ms=0.0,
        completion_latency_ms=0.0, has_citations=True,
        expected_citations=True, rag_low_evidence=True,
        reply_has_disclaimer=True,
    )
    assert cal._extract_sli_value("task_success_rate", rec_pass) == 1.0
    assert cal._extract_sli_value("citation_coverage", rec_pass) == 1.0
    assert cal._extract_sli_value("low_evidence_disclaim_rate", rec_pass) == 1.0

    rec_fail = RunRecord(
        item_id="i1", category="factual", success=False,
        accept_latency_ms=0.0, first_token_latency_ms=0.0,
        completion_latency_ms=0.0, has_citations=False,
        expected_citations=True, rag_low_evidence=True,
        reply_has_disclaimer=False,
    )
    assert cal._extract_sli_value("task_success_rate", rec_fail) == 0.0
    assert cal._extract_sli_value("citation_coverage", rec_fail) == 0.0
    assert cal._extract_sli_value("low_evidence_disclaim_rate", rec_fail) == 0.0


# ---------- Task 5: _build_report ----------

def test_build_report_structure():
    """报表必含 per_sli 6 项 + 顶层元信息。"""
    from slo.aggregator import RunRecord
    from slo.loader import Threshold

    thresholds = [
        Threshold(name="accept_latency_ms", direction="<=",
                  threshold=500.0, aggregation="p95"),
        Threshold(name="first_token_latency_ms", direction="<=",
                  threshold=3000.0, aggregation="p95"),
        Threshold(name="completion_latency_ms", direction="<=",
                  threshold=15000.0, aggregation="p95"),
        Threshold(name="task_success_rate", direction=">=",
                  threshold=0.97, aggregation="ratio"),
        Threshold(name="citation_coverage", direction=">=",
                  threshold=0.85, aggregation="ratio"),
        Threshold(name="low_evidence_disclaim_rate", direction=">=",
                  threshold=0.95, aggregation="ratio"),
    ]
    records = [
        RunRecord(
            item_id=f"i{i}", category="factual", success=True,
            accept_latency_ms=10.0 * (i + 1),
            first_token_latency_ms=200.0 * (i + 1),
            completion_latency_ms=1500.0 * (i + 1),
            has_citations=True, expected_citations=True,
            rag_low_evidence=False, reply_has_disclaimer=False,
        )
        for i in range(5)
    ]

    report = cal._build_report(
        records=records, thresholds=thresholds,
        rounds=1, items_per_round=5, margin=0.20,
    )

    assert report["version"] == "v2-recommended"
    assert report["rounds"] == 1
    assert report["items_per_round"] == 5
    assert report["data_points"] == 5
    assert report["margin"] == 0.20
    assert "generated_at" in report
    assert set(report["per_sli"].keys()) == set(cal.SLI_DIRECTIONS.keys())

    # accept_latency_ms 子项校验
    accept = report["per_sli"]["accept_latency_ms"]
    assert accept["v1_threshold"] == 500.0
    assert accept["direction"] == "<="
    assert len(accept["samples"]) == 5
    assert accept["p50"] == 30.0
    # p95 = 50.0；v2 = max(50*1.2, 500) = 500
    assert accept["p95"] == 50.0
    assert accept["v2_recommended"] == 500.0


def test_build_report_summary_text_present():
    from slo.aggregator import RunRecord
    from slo.loader import Threshold
    thresholds = [
        Threshold(
            name=name, direction=cal.SLI_DIRECTIONS[name],
            threshold=1.0,
            aggregation="ratio" if cal.SLI_DIRECTIONS[name] == ">=" else "p95",
        )
        for name in cal.SLI_DIRECTIONS
    ]
    records = [
        RunRecord(
            item_id="i0", category="factual", success=True,
            accept_latency_ms=0.0, first_token_latency_ms=0.0,
            completion_latency_ms=0.0, has_citations=True,
            expected_citations=True, rag_low_evidence=False,
            reply_has_disclaimer=False,
        )
    ]
    report = cal._build_report(
        records=records, thresholds=thresholds,
        rounds=1, items_per_round=1, margin=0.20,
    )
    assert isinstance(report["summary_text"], str)
    assert "accept_latency_ms" in report["summary_text"]


# ---------- Task 5: _write_report ----------

def test_write_report_creates_file(tmp_path):
    import json as _json
    report = {"version": "v2-recommended", "per_sli": {}}
    out_path = tmp_path / "subdir" / "report.json"
    cal._write_report(report, out_path)
    assert out_path.exists()
    loaded = _json.loads(out_path.read_text(encoding="utf-8"))
    assert loaded["version"] == "v2-recommended"



