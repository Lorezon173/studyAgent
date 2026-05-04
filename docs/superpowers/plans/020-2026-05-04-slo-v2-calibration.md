# SLO v2 阈值校准 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 `slo/calibrate.py` 校准工具，跑 5 轮真实 LLM 回归（共 60 数据点），生成推荐 v2 阈值报表，并据此手动写入 `slo/thresholds.yaml` v2，让 SLO 门禁真实反映系统状态。

**Architecture:** 独立 CLI 脚本（方案 A，spec §2.2）。复用 `slo.run_regression._run_one` 做实际 LLM 调用，新写一个 `calibrate.py` 跑 N 轮 → 计算 p50/p95/p99 → 按 le / ge 方向公式推算 v2 → 写 JSON 报表（不自动改 yaml，yaml 必须经 PR review）。测试用 monkeypatch 替换 `_run_one` 以零成本验证逻辑。

**Tech Stack:** Python 3.11、PyYAML、stdlib（statistics / argparse / json）、pytest、uv（构建/运行）。无新依赖。

**对应 spec：** `docs/superpowers/specs/008-2026-05-04-slo-v2-calibration-design.md`

---

## File Structure

| 文件 | 类型 | 责任 |
|---|---|---|
| `slo/calibrate.py` | 新建（约 100 行） | calibrate CLI 入口 + percentile 计算 + v2 推算 + 报表生成 |
| `tests/test_slo_calibrate.py` | 新建（约 80 行） | 单元测试：报表结构 / le 公式 / ge 公式 / dry-run / 边界轮次 |
| `slo/thresholds.yaml` | 修改（手动） | 跑完 calibrate 后据报表写 v2 阈值 |
| `.gitignore` | 修改 | 加白名单 `!tests/test_slo_calibrate.py`（与既有 SLO 测试白名单一致） |
| `reports/slo-calibration-v2-*.json` | 落盘（不入库） | 校准报表，仅本地参考 |

**职责边界：**
- `calibrate.py` **不导入** `aggregator.py / checker.py`（不重复聚合，只做百分位 + v2 推算）
- `calibrate.py` **导入** `loader.load_thresholds / load_regression_set` 与 `run_regression._run_one`
- `calibrate.py` **不写** thresholds.yaml（spec §5 严禁脚本静默改 yaml）

---

## Pre-flight：分支与 spec 落盘

- [ ] **Step 0.1：创建 feature 分支**

```bash
git checkout -b feature/slo-v2-calibration
git status
```

Expected：当前在 `feature/slo-v2-calibration`；`docs/superpowers/specs/008-2026-05-04-slo-v2-calibration-design.md` 与 `docs/superpowers/plans/020-2026-05-04-slo-v2-calibration.md` 显示为 untracked。

- [ ] **Step 0.2：提交 spec 与 plan**

```bash
git add docs/superpowers/specs/008-2026-05-04-slo-v2-calibration-design.md
git add docs/superpowers/plans/020-2026-05-04-slo-v2-calibration.md
git commit -m "docs(slo): add v2 calibration spec + plan #020"
```

Expected：1 个 commit，含 2 个 docs 文件。

---

## Task 1：测试白名单 + 占位测试文件

**Files:**
- Modify: `.gitignore:10-29`（加白名单 `!tests/test_slo_calibrate.py`）
- Create: `tests/test_slo_calibrate.py`（占位）

- [ ] **Step 1.1：检查 .gitignore 现状**

```bash
grep -n "test_slo" .gitignore
```

Expected：看到 `!tests/test_slo_loader.py` 等 5 行已存在的 SLO 测试白名单（位于 25-29 行附近）。

- [ ] **Step 1.2：在 .gitignore 末尾追加 calibrate 测试白名单**

在 `.gitignore` 中找到 `!tests/test_slo_alert_evaluator.py` 那一行（约 29 行），在它**下一行**插入：

```
!tests/test_slo_calibrate.py
```

不要改其他行。

- [ ] **Step 1.3：创建占位测试文件**

`tests/test_slo_calibrate.py` 写入：

```python
"""SLO v2 calibrate 工具单元测试（plan #020）。"""
```

- [ ] **Step 1.4：验证 git 能跟踪新测试文件**

```bash
git check-ignore -v tests/test_slo_calibrate.py
```

Expected：返回非零，且无输出（或显示白名单生效），表示文件**不再被 ignore**。

- [ ] **Step 1.5：提交**

```bash
git add .gitignore tests/test_slo_calibrate.py
git commit -m "chore(slo): whitelist test_slo_calibrate.py"
```

---

## Task 2：calibrate.py 骨架（dataclass + 配置常量）

**Files:**
- Create: `slo/calibrate.py`
- Test: `tests/test_slo_calibrate.py`

- [ ] **Step 2.1：写第一个测试 — 模块可导入 + 常量**

在 `tests/test_slo_calibrate.py` 追加：

```python
import slo.calibrate as cal


def test_module_exports_constants():
    assert cal.DEFAULT_MARGIN == 0.20
    assert cal.DEFAULT_ROUNDS == 5
    # 6 个 SLI 名 + 方向常量
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
```

- [ ] **Step 2.2：跑测试，确认失败**

```bash
PYTHONPATH=. uv run pytest tests/test_slo_calibrate.py -v
```

Expected：1 FAIL，提示 `ModuleNotFoundError: No module named 'slo.calibrate'`。

- [ ] **Step 2.3：实现 calibrate.py 骨架**

`slo/calibrate.py` 写入：

```python
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
```

- [ ] **Step 2.4：跑测试，确认通过**

```bash
PYTHONPATH=. uv run pytest tests/test_slo_calibrate.py -v
```

Expected：1 PASS。

- [ ] **Step 2.5：提交**

```bash
git add slo/calibrate.py tests/test_slo_calibrate.py
git commit -m "feat(slo): calibrate.py 骨架 + 常量 + 测试"
```

---

## Task 3：百分位与 v2 推算函数

**Files:**
- Modify: `slo/calibrate.py`（新增 `_percentile`、`_recommend_v2`）
- Test: `tests/test_slo_calibrate.py`

- [ ] **Step 3.1：写百分位测试**

在 `tests/test_slo_calibrate.py` 追加：

```python
def test_percentile_basic():
    samples = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
    assert cal._percentile(samples, 0.5) == 5.0
    assert cal._percentile(samples, 0.95) == 10.0


def test_percentile_single_sample():
    assert cal._percentile([3.14], 0.95) == 3.14


def test_percentile_empty_raises():
    import pytest
    with pytest.raises(ValueError):
        cal._percentile([], 0.95)
```

- [ ] **Step 3.2：写 v2 推算测试（le 方向）**

继续追加：

```python
def test_recommend_v2_le_actual_higher_than_v1_relaxes_to_actual_with_margin():
    # accept ≤ 500（v1）；实测 p95 = 1000，margin 0.2 → v2 应 = 1200
    v2 = cal._recommend_v2(
        direction="<=", v1_threshold=500.0, p95_actual=1000.0, margin=0.20
    )
    assert v2 == 1200.0


def test_recommend_v2_le_actual_lower_than_v1_keeps_v1():
    # 实测优于 v1，不收紧（保留 v1 而非 actual×1.2）
    v2 = cal._recommend_v2(
        direction="<=", v1_threshold=500.0, p95_actual=100.0, margin=0.20
    )
    # actual×1.2 = 120 < 500，按 spec §3.5: max(120, 500) = 500
    assert v2 == 500.0
```

- [ ] **Step 3.3：写 v2 推算测试（ge 方向）**

继续追加：

```python
def test_recommend_v2_ge_actual_well_above_v1_can_tighten_via_margin():
    # task_success ≥ 0.97（v1）；实测 p95 = 1.00，margin 0.2 → actual×0.8 = 0.80 < 0.97 → v2 = 0.97
    v2 = cal._recommend_v2(
        direction=">=", v1_threshold=0.97, p95_actual=1.00, margin=0.20
    )
    # max(0.80, 0.97) = 0.97
    assert v2 == 0.97


def test_recommend_v2_ge_actual_extremely_high_could_lift_threshold():
    # 实测 p95 远高于 v1：actual×0.8 > v1，按 spec §3.4 max(actual×0.8, v1)
    # 例：v1=0.50，actual=1.00，margin=0.2 → 0.80 > 0.50 → v2=0.80
    v2 = cal._recommend_v2(
        direction=">=", v1_threshold=0.50, p95_actual=1.00, margin=0.20
    )
    assert v2 == 0.80
```

- [ ] **Step 3.4：跑测试，确认失败**

```bash
PYTHONPATH=. uv run pytest tests/test_slo_calibrate.py -v
```

Expected：5 FAIL（新加的 7 个里有 5 个已经覆盖到 `_percentile`/`_recommend_v2`，剩余 2 个会先在采集阶段失败，但此时只看 6 个测试都因这两个函数缺失而 FAIL，全部 7 都因相同原因 FAIL）。

> 注：Step 3.1+3.2+3.3 共加了 7 个测试函数（3 + 2 + 2），加上 Task 2 的 1 个，累计 8 个。

- [ ] **Step 3.5：实现 `_percentile` 与 `_recommend_v2`**

在 `slo/calibrate.py` 末尾追加：

```python
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
```

- [ ] **Step 3.6：跑测试，确认全部通过**

```bash
PYTHONPATH=. uv run pytest tests/test_slo_calibrate.py -v
```

Expected：全部 8 PASS（Task 2 的 1 个 + Task 3 新增的 7 个）。

- [ ] **Step 3.7：提交**

```bash
git add slo/calibrate.py tests/test_slo_calibrate.py
git commit -m "feat(slo): _percentile + _recommend_v2 with le/ge formulas"
```

---

## Task 4：跑 N 轮回归 + 数据采集

**Files:**
- Modify: `slo/calibrate.py`（新增 `_collect_samples`、`_extract_sli_value`）
- Test: `tests/test_slo_calibrate.py`

- [ ] **Step 4.1：写采集测试 — 单轮 12 题**

在 `tests/test_slo_calibrate.py` 追加：

```python
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
```

- [ ] **Step 4.2：写 SLI 提取测试**

继续追加：

```python
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
```

- [ ] **Step 4.3：跑测试确认失败**

```bash
PYTHONPATH=. uv run pytest tests/test_slo_calibrate.py -v
```

Expected：4 个新测试 FAIL（`_collect_samples` / `_extract_sli_value` 未定义）。

- [ ] **Step 4.4：实现 `_collect_samples` + `_extract_sli_value`**

在 `slo/calibrate.py` 顶部 import 区追加：

```python
from slo.aggregator import RunRecord
from slo.run_regression import _run_one as _default_run_one
```

并在文件末尾追加：

```python
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
        # 与 aggregator 一致：仅在 expected_citations=True 时计入
        if not record.expected_citations:
            return 1.0  # 不影响平均
        return 1.0 if record.has_citations else 0.0
    if sli_name == "low_evidence_disclaim_rate":
        # 与 aggregator 一致：仅在 rag_low_evidence=True 时计入
        if not record.rag_low_evidence:
            return 1.0
        return 1.0 if record.reply_has_disclaimer else 0.0
    raise ValueError(f"unknown sli_name: {sli_name!r}")
```

- [ ] **Step 4.5：跑测试确认通过**

```bash
PYTHONPATH=. uv run pytest tests/test_slo_calibrate.py -v
```

Expected：12 PASS（8 旧 + 4 新）。

- [ ] **Step 4.6：提交**

```bash
git add slo/calibrate.py tests/test_slo_calibrate.py
git commit -m "feat(slo): _collect_samples + _extract_sli_value"
```

---

## Task 5：报表生成（per_sli + JSON）

**Files:**
- Modify: `slo/calibrate.py`（新增 `_build_report`、`_write_report`）
- Test: `tests/test_slo_calibrate.py`

- [ ] **Step 5.1：写报表结构测试**

在 `tests/test_slo_calibrate.py` 追加：

```python
def test_build_report_structure(monkeypatch):
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


def test_build_report_summary_text_present(monkeypatch):
    from slo.aggregator import RunRecord
    from slo.loader import Threshold
    thresholds = [
        Threshold(name=name, direction=cal.SLI_DIRECTIONS[name],
                  threshold=1.0, aggregation="ratio" if cal.SLI_DIRECTIONS[name] == ">=" else "p95")
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
```

- [ ] **Step 5.2：写写盘测试**

继续追加：

```python
def test_write_report_creates_file(tmp_path):
    report = {"version": "v2-recommended", "per_sli": {}}
    out_path = tmp_path / "subdir" / "report.json"
    cal._write_report(report, out_path)
    import json as _json
    assert out_path.exists()
    loaded = _json.loads(out_path.read_text(encoding="utf-8"))
    assert loaded["version"] == "v2-recommended"
```

- [ ] **Step 5.3：跑测试确认失败**

```bash
PYTHONPATH=. uv run pytest tests/test_slo_calibrate.py -v
```

Expected：3 FAIL（`_build_report` / `_write_report` 未定义）。

- [ ] **Step 5.4：实现 `_build_report` + `_write_report`**

在 `slo/calibrate.py` 末尾追加：

```python
def _build_report(
    records: list[RunRecord],
    thresholds: list[Threshold],
    rounds: int,
    items_per_round: int,
    margin: float,
) -> dict:
    """聚合 records → 推荐 v2 阈值 → 返回可直接 json.dump 的 dict。"""
    threshold_by_name = {t.name: t for t in thresholds}
    per_sli: dict[str, dict] = {}
    summary_lines: list[str] = []

    for sli_name, direction in SLI_DIRECTIONS.items():
        v1 = threshold_by_name[sli_name].threshold if sli_name in threshold_by_name else 0.0
        samples = [_extract_sli_value(sli_name, r) for r in records]
        p50 = _percentile(samples, 0.50)
        p95 = _percentile(samples, 0.95)
        p99 = _percentile(samples, 0.99)
        v2 = _recommend_v2(direction=direction, v1_threshold=v1,
                           p95_actual=p95, margin=margin)
        per_sli[sli_name] = {
            "v1_threshold": v1,
            "direction": direction,
            "samples": samples,
            "p50": p50,
            "p95": p95,
            "p99": p99,
            "v2_recommended": v2,
        }
        change = "unchanged" if v2 == v1 else f"{v1} -> {v2}"
        summary_lines.append(
            f"  {sli_name:<32} {direction:<2} p95={p95:.3f}  v2={v2}  ({change})"
        )

    # 读取 LLM 提供商信息（可选；失败时填 'unknown'）
    try:
        from app.core.config import settings
        llm_provider = settings.openai_base_url or "default"
        llm_model = settings.openai_model or "default"
    except Exception:
        llm_provider, llm_model = "unknown", "unknown"

    return {
        "version": "v2-recommended",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "rounds": rounds,
        "items_per_round": items_per_round,
        "data_points": len(records),
        "llm_provider": llm_provider,
        "llm_model": llm_model,
        "margin": margin,
        "per_sli": per_sli,
        "summary_text": "v2 recommended thresholds (spec #008):\n" + "\n".join(summary_lines),
    }


def _write_report(report: dict, out_path: Path) -> None:
    """写盘前自动 mkdir。"""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
```

- [ ] **Step 5.5：跑测试确认通过**

```bash
PYTHONPATH=. uv run pytest tests/test_slo_calibrate.py -v
```

Expected：15 PASS。

- [ ] **Step 5.6：提交**

```bash
git add slo/calibrate.py tests/test_slo_calibrate.py
git commit -m "feat(slo): _build_report + _write_report (per_sli x6 + summary)"
```

---

## Task 6：CLI 入口（argparse + main）

**Files:**
- Modify: `slo/calibrate.py`（新增 `_parse_args`、`main`）
- Test: `tests/test_slo_calibrate.py`

- [ ] **Step 6.1：写 CLI 参数解析测试**

在 `tests/test_slo_calibrate.py` 追加：

```python
def test_parse_args_defaults():
    args = cal._parse_args([])
    assert args.rounds == cal.DEFAULT_ROUNDS
    assert args.margin == cal.DEFAULT_MARGIN
    assert args.dry_run is False


def test_parse_args_overrides():
    args = cal._parse_args(["--rounds", "2", "--margin", "0.30",
                            "--output", "out.json", "--dry-run"])
    assert args.rounds == 2
    assert args.margin == 0.30
    assert args.output == "out.json"
    assert args.dry_run is True
```

- [ ] **Step 6.2：写 main() dry-run 测试**

继续追加：

```python
def test_main_dry_run_skips_write(monkeypatch, tmp_path, capsys):
    """--dry-run 不写文件，但应打印 summary。"""
    from slo.aggregator import RunRecord

    def fake_run_one(item):
        return RunRecord(
            item_id=item.id, category=item.category, success=True,
            accept_latency_ms=10.0, first_token_latency_ms=200.0,
            completion_latency_ms=1500.0, has_citations=True,
            expected_citations=True, rag_low_evidence=False,
            reply_has_disclaimer=False,
        )

    monkeypatch.setattr(cal, "_run_one", fake_run_one)
    out_path = tmp_path / "report.json"
    rc = cal.main(["--rounds", "1", "--output", str(out_path), "--dry-run"])
    assert rc == 0
    assert not out_path.exists()
    captured = capsys.readouterr().out
    assert "v2 recommended" in captured.lower() or "v2_recommended" in captured.lower() or "v2 recommended thresholds" in captured


def test_main_writes_report(monkeypatch, tmp_path):
    from slo.aggregator import RunRecord

    def fake_run_one(item):
        return RunRecord(
            item_id=item.id, category=item.category, success=True,
            accept_latency_ms=10.0, first_token_latency_ms=200.0,
            completion_latency_ms=1500.0, has_citations=True,
            expected_citations=True, rag_low_evidence=False,
            reply_has_disclaimer=False,
        )

    monkeypatch.setattr(cal, "_run_one", fake_run_one)
    out_path = tmp_path / "report.json"
    rc = cal.main(["--rounds", "1", "--output", str(out_path)])
    assert rc == 0
    assert out_path.exists()
    import json as _json
    loaded = _json.loads(out_path.read_text(encoding="utf-8"))
    assert "per_sli" in loaded
    assert len(loaded["per_sli"]) == 6


def test_main_returns_two_on_yaml_error(monkeypatch, tmp_path):
    monkeypatch.setattr(cal, "_DEFAULT_THRESHOLDS_PATH", tmp_path / "missing.yaml")
    rc = cal.main(["--rounds", "1", "--dry-run"])
    assert rc == 2
```

- [ ] **Step 6.3：跑测试确认失败**

```bash
PYTHONPATH=. uv run pytest tests/test_slo_calibrate.py -v
```

Expected：5 FAIL（新加的 5 个 test 因 `_parse_args` / `main` 未定义而失败）。

- [ ] **Step 6.4：实现 `_parse_args` + `main`**

在 `slo/calibrate.py` 末尾追加：

```python
def _default_output_path() -> str:
    ts = datetime.now().strftime("%Y%m%dT%H%M%S")
    return str(_REPO_ROOT / "reports" / f"slo-calibration-v2-{ts}.json")


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="SLO v2 calibration tool (spec #008)."
    )
    parser.add_argument("--rounds", type=int, default=DEFAULT_ROUNDS,
                        help="跑多少轮 12 题回归（默认 5）")
    parser.add_argument("--margin", type=float, default=DEFAULT_MARGIN,
                        help="v2 推算 margin（默认 0.20）")
    parser.add_argument("--output", type=str, default=None,
                        help="报表输出路径（默认 reports/slo-calibration-v2-<ts>.json）")
    parser.add_argument("--dry-run", action="store_true",
                        help="不写文件，只打印 summary")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])

    try:
        thresholds = load_thresholds(_DEFAULT_THRESHOLDS_PATH)
        items = load_regression_set(_DEFAULT_REGRESSION_PATH)
    except (FileNotFoundError, OSError, ValueError) as exc:
        print(f"SLO calibrate config error: {exc}", file=sys.stderr)
        return 2

    if args.rounds < 1:
        print(f"--rounds must be >= 1, got {args.rounds}", file=sys.stderr)
        return 2

    print(f"Calibrating: {args.rounds} rounds × {len(items)} items "
          f"= {args.rounds * len(items)} data points")
    print(f"Margin: {args.margin}")

    records = _collect_samples(items, rounds=args.rounds)
    report = _build_report(
        records=records, thresholds=thresholds,
        rounds=args.rounds, items_per_round=len(items), margin=args.margin,
    )

    print()
    print(report["summary_text"])
    print()

    if args.dry_run:
        print("[dry-run] report not written")
        return 0

    out_path = Path(args.output) if args.output else Path(_default_output_path())
    _write_report(report, out_path)
    print(f"Report written: {out_path}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
```

- [ ] **Step 6.5：跑测试确认通过**

```bash
PYTHONPATH=. uv run pytest tests/test_slo_calibrate.py -v
```

Expected：20 PASS（15 旧 + 5 新）。

- [ ] **Step 6.6：手动 dry-run 烟雾测试（用 stub agent）**

```bash
PYTHONPATH=. uv run python -c "
import slo.calibrate as cal
from slo.aggregator import RunRecord

def fake_run_one(item):
    return RunRecord(
        item_id=item.id, category=item.category, success=True,
        accept_latency_ms=12.0, first_token_latency_ms=180.0,
        completion_latency_ms=1400.0, has_citations=True,
        expected_citations=True, rag_low_evidence=False,
        reply_has_disclaimer=False,
    )
cal._run_one = fake_run_one
rc = cal.main(['--rounds', '1', '--dry-run'])
print('exit:', rc)
"
```

Expected：打印 12 行 round=1 进度 + summary 表 + `[dry-run] report not written` + `exit: 0`。

- [ ] **Step 6.7：提交**

```bash
git add slo/calibrate.py tests/test_slo_calibrate.py
git commit -m "feat(slo): calibrate CLI 入口 (--rounds/--margin/--output/--dry-run)"
```

---

## Task 7：全量回归不退化验证

**Files:** （仅验证，不改代码）

- [ ] **Step 7.1：跑 calibrate 测试单文件**

```bash
PYTHONPATH=. uv run pytest tests/test_slo_calibrate.py -v
```

Expected：20 PASS。

- [ ] **Step 7.2：跑全量回归对比基线**

```bash
PYTHONPATH=. DEBUG=false uv run pytest tests/ -q
```

Expected：**377 PASS / 19 FAIL**（357 + 20 个新测试 + 19 个既有失败基线维持）。

如果 PASS 数 ≠ 357 + 20，停下来排查；不要进入下一步。

- [ ] **Step 7.3：跑既有 SLO regression CLI 不退化**

```bash
PYTHONPATH=. uv run python -m slo.run_regression
```

Expected：仍以 stub 路径走通（这步只是确认 calibrate 没有侧蚀 run_regression）；exit code 任意（SLO 退出码 1 是正常的，因为 stub agent 跑出的 latency 都是 0）。重点是命令能跑完不报 ImportError。

---

## Task 8：跑真实 LLM 5 轮校准（人工执行）

> 此 Task 不写代码，只跑命令并人工分析报表。

**Files:**
- Modify: `slo/thresholds.yaml`（按报表写入 v2）

- [ ] **Step 8.1：检查 `.env` 配置**

```bash
cat .env | grep -E "OPENAI_API_KEY|OPENAI_MODEL|OPENAI_BASE_URL|LANGFUSE"
```

Expected：`OPENAI_API_KEY` 非空、`OPENAI_MODEL` 已设（推荐便宜模型如 `gpt-4o-mini` / `kimi-8k`）。Langfuse 可选。

如果未配置，参考 `app/core/config.py:8-11`，在 `.env` 加：

```
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini
OPENAI_BASE_URL=https://api.openai.com/v1
```

- [ ] **Step 8.2：先用 1 轮试跑（成本估算 + 链路验证）**

```bash
PYTHONPATH=. uv run python -m slo.calibrate --rounds 1
```

Expected：
- 12 行进度 (`[ X/12] round=1 <id> (<category>)`)
- summary 表 6 行（accept / first_token / completion / task_success / citation / disclaim）
- `Report written: reports/slo-calibration-v2-<ts>.json`
- 进程总耗时约 1-3 分钟（依模型 / 网络）
- 估算成本：< $0.10

如果失败，常见原因：
- LLM key 限流 → 等几秒重试
- 模型名拼错 → 改 `.env` 后重跑
- agent_service 调用链报错 → 看 traceback 判断是 LLM/RAG/graph_v2 哪一层

- [ ] **Step 8.3：跑完整 5 轮校准**

```bash
PYTHONPATH=. uv run python -m slo.calibrate --rounds 5
```

Expected：
- 60 行进度
- summary 表
- `Report written: reports/slo-calibration-v2-<ts>.json`
- 总耗时 5-15 分钟，成本 < $0.50

- [ ] **Step 8.4：阅读报表，决策每个 SLI 的 v2**

```bash
cat reports/slo-calibration-v2-*.json | python -m json.tool
```

按 spec §11 预期：
- `accept_latency_ms`：同步路径下恒为 0 → **保持 v1 = 500**（注释里说明 ASYNC 启用后再调）
- `first_token_latency_ms`：实测 p95 大概率 1000-5000ms → 取报表 v2_recommended
- `completion_latency_ms`：实测 p95 大概率 5000-30000ms → 取报表 v2_recommended（如果 > 30000ms 需重新审视模型选择）
- `task_success_rate`：实测大概率 0.95-1.00 → 取报表 v2_recommended（不应低于 0.90，否则降阈值到 0.90 而非更低）
- `citation_coverage`、`low_evidence_disclaim_rate`：实测依赖 RAG → 一般保持 v1

记录每个 SLI 的决策（保留 v1 / 采纳 v2 / 调整为另一个值）以及理由。

- [ ] **Step 8.5：手动改 `slo/thresholds.yaml`**

只改 threshold 数值，不改 direction / aggregation / 排序。例如：

```yaml
version: "v2"  # 从 "v1" 升级
slis:
  - name: "accept_latency_ms"
    direction: "<="
    threshold: 500          # 保留 v1（同步路径下实测恒为 0）
    aggregation: "p95"
  - name: "first_token_latency_ms"
    direction: "<="
    threshold: 4500         # 报表 v2_recommended（v1=3000）
    aggregation: "p95"
  # ... 其余按报表
```

- [ ] **Step 8.6：再跑一次 SLO 检查验收 v2**

```bash
PYTHONPATH=. uv run python -m slo.run_regression
```

Expected：exit code = 0（v2 阈值已贴合实测，门禁应通过）。

如果 exit 1，看 breach 详情：
- 如果是某个 SLI 偶发抖动 → 用更大 margin 重跑 calibrate（`--margin 0.30`）
- 如果系统性指标不达标 → 这是真实信号，记录到 PR 描述里

- [ ] **Step 8.7：提交 thresholds.yaml**

```bash
git add slo/thresholds.yaml
git commit -m "feat(slo): thresholds.yaml v1 -> v2 (基于 5 轮真实 LLM 校准)"
```

---

## Task 9：PR 文档与发布

- [ ] **Step 9.1：整理 PR 描述（写成本地草稿）**

新建临时草稿文件（不入库）：

```bash
mkdir -p reports
cat > reports/pr-draft-slo-v2.md << 'EOF'
## Summary

Spec: docs/superpowers/specs/008-2026-05-04-slo-v2-calibration-design.md
Plan: docs/superpowers/plans/020-2026-05-04-slo-v2-calibration.md

新增 `slo/calibrate.py` 校准工具，基于 5 轮真实 LLM 回归（60 数据点）将 SLO v1 升级为 v2。

## v1 -> v2 阈值变化（数据来源：reports/slo-calibration-v2-<ts>.json）

| SLI | 方向 | v1 | v2 | 变化 | 理由 |
|---|---|---|---|---|---|
| accept_latency_ms | ≤ | 500 | 500 | unchanged | 同步路径下实测恒为 0 |
| first_token_latency_ms | ≤ | 3000 | <填> | <填> | <填> |
| completion_latency_ms | ≤ | 15000 | <填> | <填> | <填> |
| task_success_rate | ≥ | 0.97 | <填> | <填> | <填> |
| citation_coverage | ≥ | 0.85 | <填> | <填> | <填> |
| low_evidence_disclaim_rate | ≥ | 0.95 | <填> | <填> | <填> |

## 校准元信息

- LLM: <从报表 llm_model 字段填>
- API: <从报表 llm_provider 字段填>
- 轮次: 5
- 题数: 60 (12 × 5)
- Margin: 0.20

## 验收

- 单元测试: 20 个全部 PASS
- 全量回归: 377 PASS / 19 FAIL（19 个为既有基线）
- 真实 LLM SLO check: exit 0
EOF
```

把 `<填>` 替换成 Step 8.4 决策的实际数据。

- [ ] **Step 9.2：推送分支**

```bash
git push -u origin feature/slo-v2-calibration
```

Expected：远端建好 `feature/slo-v2-calibration` 分支。

- [ ] **Step 9.3：开 PR**

通过 GitHub UI 或 `gh` 命令开 PR：

```bash
gh pr create --base master --head feature/slo-v2-calibration \
  --title "feat(slo): v2 阈值校准工具 + thresholds v1→v2" \
  --body-file reports/pr-draft-slo-v2.md
```

如果用户没装 `gh`，告诉用户：
> 已推送到 `feature/slo-v2-calibration`，请到 GitHub 网页开 PR，PR body 用 `reports/pr-draft-slo-v2.md` 的内容。

- [ ] **Step 9.4：等待 PR review，按反馈调整**

如果 review 提了改阈值的建议：回到 Task 8.5 改 yaml，commit & push。

- [ ] **Step 9.5：合并后清理本地分支**

```bash
git checkout master
git pull origin master
git branch -d feature/slo-v2-calibration
```

---

## 验收标准（spec §10）

| 项 | 阈值 / 形态 | 验证方式 |
|---|---|---|
| calibrate 工具 | `uv run python -m slo.calibrate --rounds N` 可跑通 | Task 6.6 + Task 8.2/8.3 |
| 测试 | 单元测试 ≥ 5 个，全绿 | Task 7.1（实际 20 个） |
| 报表 | reports/ 下生成完整 json，per_sli 含 6 项 | Task 5.1 测试 + Task 8.3 实际产出 |
| v2 阈值 | thresholds.yaml 至少 1 个 SLI 阈值变化 | Task 8.5 |
| 真实回归 | `uv run python -m slo.run_regression` 真实 LLM 下退出码 0 | Task 8.6 |
| 不退化 | 全量 `pytest` 维持 + 20 新增 | Task 7.2（377 PASS / 19 FAIL）|
| PR 文档 | PR 描述含数据表 + 每个 SLI 的 v1→v2 变化说明 | Task 9.1 |

---

## 风险与回退

| 风险 | 应对（与 spec §6 一致） |
|---|---|
| LLM key 限流 / 网络抖动 | calibrate `_run_one` 已 catch Exception 转 success=False；样本不丢失 |
| 5 轮 60 题成本 | 用 gpt-4o-mini 估算 < $0.5 |
| 单次极慢污染 p95 | 报表保留 p50/p95/p99；20% margin 吸收 |
| 实测 task_success < 0.90 | 在 PR 中显式声明并降阈值到 0.90，**不放任** |
| 校准过程被打断 | 回到 Task 8.3 重跑（rounds 可减小到 3） |
| 任意阶段需要回退 | `git checkout master` 即可；feature branch 完全独立 |

---

## Self-Review 备忘（已通过）

- 所有步骤含完整代码或精确命令
- Task 1-7 是封闭可测试的（仅 mock + 纯函数）
- Task 8-9 明确标注"人工执行"，区别于自动化步骤
- 函数签名一致：`_recommend_v2(direction, v1_threshold, p95_actual, margin)` 在 Task 3 定义、Task 5 使用
- `_collect_samples(items, rounds)` 与 `_build_report(records, thresholds, rounds, items_per_round, margin)` 参数顺序对齐
- spec §3.4/§3.5 公式逐字落入 Task 3 实现
- spec §4 报表结构逐字落入 Task 5 实现 + 单元测试
- spec §10 7 项验收标准全部映射到 Task 1-9 的具体步骤
