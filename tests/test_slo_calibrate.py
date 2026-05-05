"""SLO v2 calibrate 工具单元测试（plan #020）。"""
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
