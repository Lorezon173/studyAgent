"""SLO 回归 CLI 入口。

Usage:
    uv run python -m slo.run_regression

Exit codes:
    0  - 所有阈值达标
    1  - 任一 SLI 违反阈值
    2  - 配置/IO 错误（YAML 解析失败、文件缺失等）
"""
from __future__ import annotations

import sys
import time
import uuid
from pathlib import Path

from slo.aggregator import RunRecord, SliReport, aggregate
from slo.checker import check, CheckResult
from slo.loader import RegressionItem, Threshold, load_regression_set, load_thresholds


_REPO_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_THRESHOLDS_PATH = _REPO_ROOT / "slo" / "thresholds.yaml"
_DEFAULT_REGRESSION_PATH = _REPO_ROOT / "slo" / "regression_set.yaml"

_DISCLAIMER_KEYWORDS = (
    "证据不足",
    "信息有限",
    "无法确定",
    "建议进一步查阅",
    "尚未掌握",
    "暂无可靠资料",
)


def _reply_has_disclaimer(reply: str) -> bool:
    return any(kw in reply for kw in _DISCLAIMER_KEYWORDS)


def _run_one(item: RegressionItem) -> RunRecord:
    """同步调用 agent_service.run 并采集 RunRecord。"""
    from app.services.agent_service import agent_service
    from app.core.config import settings

    # 强制同步路径：避免 SLO 检查依赖 Redis/Celery
    prev_async = getattr(settings, "async_graph_enabled", False)
    settings.async_graph_enabled = False

    session_id = f"slo-{item.id}-{uuid.uuid4().hex[:6]}"
    first_token_ts: list[float] = []
    start = time.monotonic()

    def sink(event: str, data: str) -> None:
        if event == "token" and not first_token_ts:
            first_token_ts.append(time.monotonic())

    try:
        result = agent_service.run(
            session_id=session_id,
            topic=item.topic,
            user_input=item.user_input,
            progress_sink=sink,
        )
    except Exception:
        end = time.monotonic()
        return RunRecord(
            item_id=item.id,
            category=item.category,
            success=False,
            accept_latency_ms=0.0,
            first_token_latency_ms=(end - start) * 1000,
            completion_latency_ms=(end - start) * 1000,
            has_citations=False,
            expected_citations=item.expects_citations,
            rag_low_evidence=False,
            reply_has_disclaimer=False,
        )
    finally:
        settings.async_graph_enabled = prev_async

    end = time.monotonic()
    completion_ms = (end - start) * 1000
    first_tok_ms = (
        (first_token_ts[0] - start) * 1000 if first_token_ts else completion_ms
    )

    valid_stages = {"explained", "followup_generated", "planned", "summarized"}
    success = str(result.get("stage", "")) in valid_stages

    citations = result.get("citations") or []
    reply = str(result.get("reply", ""))

    return RunRecord(
        item_id=item.id,
        category=item.category,
        success=success,
        accept_latency_ms=0.0,
        first_token_latency_ms=first_tok_ms,
        completion_latency_ms=completion_ms,
        has_citations=bool(citations),
        expected_citations=item.expects_citations,
        rag_low_evidence=bool(result.get("rag_low_evidence", False)),
        reply_has_disclaimer=_reply_has_disclaimer(reply),
    )


def _print_report(reports: list[SliReport], result: CheckResult) -> None:
    print("=" * 60)
    print("SLO Regression Report")
    print("=" * 60)
    for r in reports:
        unit = "ms" if "_ms" in r.sli_name else ""
        print(f"  {r.sli_name:<32} {r.aggregation:<6} = {r.value:8.3f}{unit}  (n={r.sample_size})")
    if result.skipped:
        print(f"\n  Skipped (not yet implemented): {', '.join(result.skipped)}")
    print("-" * 60)
    if result.passed:
        print(f"  Status: PASS  (0 breaches, {len(result.skipped)} skipped)")
    else:
        print(f"  Status: FAIL  ({len(result.breaches)} breaches)")
        for b in result.breaches:
            print(f"    - {b.sli_name}: {b.actual:.3f} {b.direction} {b.threshold} VIOLATED")
    print("=" * 60)


def main(argv: list[str] | None = None) -> int:
    try:
        thresholds = load_thresholds(_DEFAULT_THRESHOLDS_PATH)
        items = load_regression_set(_DEFAULT_REGRESSION_PATH)
    except (FileNotFoundError, OSError, ValueError) as exc:
        print(f"SLO config error: {exc}", file=sys.stderr)
        return 2

    print(f"Running {len(items)} regression items...")
    records: list[RunRecord] = []
    for i, item in enumerate(items, 1):
        print(f"  [{i:2d}/{len(items)}] {item.id} ({item.category})")
        records.append(_run_one(item))

    reports = aggregate(records)
    result = check(reports, thresholds)
    _print_report(reports, result)
    return 0 if result.passed else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
