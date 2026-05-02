# Phase 3c：SLO 门禁实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立可量化、可执行的 SLO 门禁脚本：固定 12-15 题回归集 → 跑 chat graph → 聚合 7 个 SLI → 比对 `slo/thresholds.yaml` → 退出码 0/1。本地一键执行 `uv run python -m slo.run_regression`，未来可挂 pre-push hook 或 CI。

**Architecture:** 新增 `slo/` 顶层包：阈值与回归集为 YAML 数据文件、逻辑分三层（loader / aggregator / runner）。runner 不直接调 graph，而是复用现有 `agent_service.run` 同步路径以避免 Redis/Celery 依赖；保持 SLO 检查能在裸机本地跑通。Langfuse trace 暂不作为 SLI 源（采样查询太重），用 result state + 本地计时器作为 v1 数据源；预留 `LangfuseSliSource` 接口位以便未来切换。

**Tech Stack:** Python 3.12 + pyyaml（已在传递依赖中）+ pytest。

**Spec 来源：** [docs/superpowers/specs/top-007-2026-05-01-phase3-finalization-design.md](../specs/top-007-2026-05-01-phase3-finalization-design.md) §8（SLO 体系）+ §11.3（子阶段 3c 交付）。

**前置：** Phase 3a/3b 已交付（PR #1 已合，PR #2 已开）。本计划不依赖 3b 的异步路径，运行时强制 `ASYNC_GRAPH_ENABLED=False`，简化测试流程。

---

## Spec 与本计划的差异声明（务实版）

`top-007 §8.1` 列了 7 个 SLI，但其中 `retry_recovery_rate` 在没有真实 LLM 失败注入或 Langfuse server 查询时无法测得。本计划处理方式：

| SLI | 数据源 | 本计划是否实现 |
|---|---|---|
| `accept_latency_ms` | 本地计时器：dispatch 调用前到 `accepted` 事件 | 异步语境特有；同步语境下记为常量 0（标注） |
| `first_token_latency_ms` | 本地计时器：调用 `agent_service.run` 到首个 LLM token 回调 | ✅ 实现 |
| `completion_latency_ms` | 本地计时器：调用 `agent_service.run` 到 return | ✅ 实现 |
| `task_success_rate` | result.stage 是否在合法集合内 | ✅ 实现 |
| `retry_recovery_rate` | 缺真实 retry 数据 | ⚠️ v1 占位（aggregator 跳过、报告中标注 N/A） |
| `citation_coverage` | result.citations 非空 / 应有引用 | ✅ 实现 |
| `low_evidence_disclaim_rate` | result.rag_low_evidence=true 且 reply 含声明语 | ✅ 实现 |

7 中 5 项实测、1 项常量、1 项占位。spec 验收口径在 `top-007 §11.3` 是 **"`make slo-check` 在主线代码上达标"**，本计划把入口改为 **`uv run python -m slo.run_regression`**（无 make 依赖更适合 Windows 本地）。spec 措辞将在 Phase 3 收尾的 Progress Note 里同步更新。

---

## File Structure

| 文件 | 类型 | 责任 | 边界 |
|---|---|---|---|
| `slo/__init__.py` | 新增 | 顶层包入口（空） | — |
| `slo/thresholds.yaml` | 新增 | 7 个 SLI 阈值（v1 单人本地基线） | 纯数据 |
| `slo/regression_set.yaml` | 新增 | 12 个回归问题（4 类 × 3 题） | 纯数据 |
| `slo/loader.py` | 新增 | YAML 解析 + 数据类（Threshold / RegressionItem） | 不依赖 agent_service |
| `slo/aggregator.py` | 新增 | 把 RunRecord 列表聚合为 SliReport（P95 / 比率） | 纯函数，可单测 |
| `slo/run_regression.py` | 新增 | 跑回归集 → 调 agent_service.run → 收集 RunRecord → 聚合 → 比对阈值 → 退出码 | CLI 入口 |
| `slo/checker.py` | 新增 | 阈值比对：`SliReport + Threshold[] -> CheckResult(passed, breaches)` | 纯函数 |
| `tests/test_slo_loader.py` | 新增 | YAML → 数据类正确解析；缺字段抛错 | — |
| `tests/test_slo_aggregator.py` | 新增 | P95 / 比率计算用 fixture 数据正确 | — |
| `tests/test_slo_checker.py` | 新增 | 阈值比对方向（≤ vs ≥）、breaches 列表正确 | — |
| `tests/test_slo_run_regression.py` | 新增 | runner 集成：mock agent_service.run，验证脚本 main 退出码 | — |

**边界原则：**

1. `loader / aggregator / checker` 是纯函数，无 IO 副作用，单测覆盖率 100%
2. `run_regression.py` 是唯一做 IO（YAML 读、agent 调用、终端打印、sys.exit）的模块
3. spec §8.5 里"未来加 GitHub Actions 三步即可"的钩子位由 runner 退出码语义保证（0 = 全过、1 = 任一阈值违反、2 = 配置错误/IO错误）

---

## Task 1：新增 thresholds.yaml + regression_set.yaml + loader（TDD）

### Files
- Create: `slo/__init__.py`
- Create: `slo/thresholds.yaml`
- Create: `slo/regression_set.yaml`
- Create: `slo/loader.py`
- Test: `tests/test_slo_loader.py`
- Modify: `.gitignore`（加 SLO 测试白名单）

### 数据契约

```yaml
# thresholds.yaml
version: "v1"
slis:
  - name: "accept_latency_ms"
    direction: "<="     # 越小越好
    threshold: 500
    aggregation: "p95"   # p50 / p95 / p99 / mean / ratio
  - name: "first_token_latency_ms"
    direction: "<="
    threshold: 3000
    aggregation: "p95"
  - name: "completion_latency_ms"
    direction: "<="
    threshold: 15000
    aggregation: "p95"
  - name: "task_success_rate"
    direction: ">="     # 越大越好
    threshold: 0.97
    aggregation: "ratio"
  - name: "citation_coverage"
    direction: ">="
    threshold: 0.85
    aggregation: "ratio"
  - name: "low_evidence_disclaim_rate"
    direction: ">="
    threshold: 0.95
    aggregation: "ratio"
  # retry_recovery_rate 暂占位，aggregator 在 3d 接 langfuse 后实测
  # - name: "retry_recovery_rate"
  #   direction: ">="
  #   threshold: 0.70
  #   aggregation: "ratio"
```

```yaml
# regression_set.yaml
version: "v1"
items:
  # 类别 1：事实问答
  - id: "fact-1"
    category: "factual"
    user_input: "什么是导数？"
    topic: "math"
    expects_citations: true
  - id: "fact-2"
    category: "factual"
    user_input: "Python 中 list 和 tuple 的区别？"
    topic: "python"
    expects_citations: true
  - id: "fact-3"
    category: "factual"
    user_input: "二战的爆发时间？"
    topic: "history"
    expects_citations: true
  # 类别 2：对比分析
  - id: "compare-1"
    category: "compare"
    user_input: "递归和迭代的优劣对比？"
    topic: "python"
    expects_citations: true
  - id: "compare-2"
    category: "compare"
    user_input: "微分和积分的应用场景对比？"
    topic: "math"
    expects_citations: true
  - id: "compare-3"
    category: "compare"
    user_input: "牛顿力学和相对论在弱场下的区别？"
    topic: "physics"
    expects_citations: true
  # 类别 3：总结复习
  - id: "summary-1"
    category: "summary"
    user_input: "帮我总结一下今天学的导数概念。"
    topic: "math"
    expects_citations: false
  - id: "summary-2"
    category: "summary"
    user_input: "复习一下 Python 装饰器的核心要点。"
    topic: "python"
    expects_citations: false
  - id: "summary-3"
    category: "summary"
    user_input: "整理我这周学过的二战知识点。"
    topic: "history"
    expects_citations: false
  # 类别 4：学习规划
  - id: "plan-1"
    category: "planning"
    user_input: "我想 4 周内掌握线性代数，怎么规划？"
    topic: "math"
    expects_citations: false
  - id: "plan-2"
    category: "planning"
    user_input: "Python 入门到能写 web 后端，给我一个学习路径。"
    topic: "python"
    expects_citations: false
  - id: "plan-3"
    category: "planning"
    user_input: "理解量子力学需要的前置数学和物理基础？"
    topic: "physics"
    expects_citations: false
```

### Steps

- [ ] **Step 1：创建空包初始化**

Create `slo/__init__.py`（空文件）。

- [ ] **Step 2：创建 thresholds.yaml**

Create `slo/thresholds.yaml`：把上面的 thresholds YAML 完整粘贴。

- [ ] **Step 3：创建 regression_set.yaml**

Create `slo/regression_set.yaml`：把上面的 regression YAML 完整粘贴。

- [ ] **Step 4：写失败测试**

Create `tests/test_slo_loader.py`:

```python
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
```

- [ ] **Step 5：运行测试，确认失败**

Run: `uv run pytest tests/test_slo_loader.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'slo.loader'`。

- [ ] **Step 6：实现 loader**

Create `slo/loader.py`:

```python
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
```

- [ ] **Step 7：在 .gitignore 加白名单**

Edit `.gitignore`，在测试白名单段尾追加：

```
!tests/test_slo_loader.py
!tests/test_slo_aggregator.py
!tests/test_slo_checker.py
!tests/test_slo_run_regression.py
```

注意：`slo/` 目录默认就在版本控制内（不在 `tests/*` 黑名单里）。

- [ ] **Step 8：运行测试，确认通过**

Run: `uv run pytest tests/test_slo_loader.py -v`
Expected: 6 PASS / 0 FAIL.

- [ ] **Step 9：Commit**

```bash
git add slo/__init__.py slo/thresholds.yaml slo/regression_set.yaml slo/loader.py \
  tests/test_slo_loader.py .gitignore
git commit -m "feat(slo): add thresholds + regression set + loader (phase 3c task 1)"
```

---

## Task 2：实现 aggregator（TDD）

### Files
- Create: `slo/aggregator.py`
- Test: `tests/test_slo_aggregator.py`

### 数据契约

```python
@dataclass(frozen=True)
class RunRecord:
    item_id: str
    category: str
    success: bool                  # stage 在 {"explained","followup_generated","planned"} 中
    accept_latency_ms: float       # 同步语境下恒为 0.0
    first_token_latency_ms: float  # 首 token 到 sink 的耗时；无 token 时取 completion 时长
    completion_latency_ms: float   # run() 返回总耗时
    has_citations: bool
    expected_citations: bool       # 来自 RegressionItem.expects_citations
    rag_low_evidence: bool
    reply_has_disclaimer: bool     # reply 是否含"证据不足/缺乏"等声明语

@dataclass(frozen=True)
class SliReport:
    sli_name: str
    aggregation: str
    value: float
    sample_size: int
```

### 聚合规则

- **p95** / p50 / p99：对所有 RunRecord 取对应 SLI 字段排序后取分位
- **ratio (task_success_rate)**：`sum(success) / total`
- **ratio (citation_coverage)**：`sum(has_citations and expected_citations) / sum(expected_citations)`（避免对不需引用的题目惩罚）
- **ratio (low_evidence_disclaim_rate)**：`sum(rag_low_evidence and reply_has_disclaimer) / sum(rag_low_evidence)`；`sum(rag_low_evidence)==0` 时返回 1.0（无应声明，覆盖率视为完全达成）

### Steps

- [ ] **Step 1：写失败测试**

Create `tests/test_slo_aggregator.py`:

```python
"""Phase 3c Task 2：SLO aggregator 计算。"""
import pytest

from slo.aggregator import RunRecord, aggregate, SliReport


def _make_record(**overrides) -> RunRecord:
    base = dict(
        item_id="x",
        category="factual",
        success=True,
        accept_latency_ms=0.0,
        first_token_latency_ms=100.0,
        completion_latency_ms=1000.0,
        has_citations=True,
        expected_citations=True,
        rag_low_evidence=False,
        reply_has_disclaimer=False,
    )
    base.update(overrides)
    return RunRecord(**base)


def test_aggregate_p95_completion_latency():
    records = [
        _make_record(completion_latency_ms=v) for v in
        [100, 200, 300, 400, 500, 600, 700, 800, 900, 1000,
         1100, 1200, 1300, 1400, 1500, 1600, 1700, 1800, 1900, 2000]
    ]
    reports = {r.sli_name: r for r in aggregate(records)}
    p95 = reports["completion_latency_ms"]
    assert p95.aggregation == "p95"
    # 20 个样本 P95 = index 18 (0-based) = 1900
    assert p95.value == 1900.0
    assert p95.sample_size == 20


def test_aggregate_task_success_rate():
    records = [_make_record(success=s) for s in [True] * 9 + [False]]
    reports = {r.sli_name: r for r in aggregate(records)}
    assert reports["task_success_rate"].value == 0.9


def test_citation_coverage_only_counts_expected_items():
    """规划题/总结题 expected_citations=False，不应拉低分母。"""
    records = [
        _make_record(expected_citations=True, has_citations=True),  # 命中
        _make_record(expected_citations=True, has_citations=False),  # 漏
        _make_record(expected_citations=False, has_citations=False),  # 不计
        _make_record(expected_citations=False, has_citations=False),  # 不计
    ]
    reports = {r.sli_name: r for r in aggregate(records)}
    # 分母 2（仅 expected=True 的 2 个），分子 1（仅 1 个真有 citations）
    assert reports["citation_coverage"].value == 0.5


def test_low_evidence_disclaim_rate_with_zero_low_evidence_returns_one():
    """无任何低证据样本时，覆盖率视为 1.0（vacuously true）。"""
    records = [_make_record(rag_low_evidence=False) for _ in range(5)]
    reports = {r.sli_name: r for r in aggregate(records)}
    assert reports["low_evidence_disclaim_rate"].value == 1.0


def test_low_evidence_disclaim_rate_partial():
    records = [
        _make_record(rag_low_evidence=True, reply_has_disclaimer=True),
        _make_record(rag_low_evidence=True, reply_has_disclaimer=True),
        _make_record(rag_low_evidence=True, reply_has_disclaimer=False),
        _make_record(rag_low_evidence=False),
    ]
    reports = {r.sli_name: r for r in aggregate(records)}
    # 3 个 low_evidence，2 个声明 → 2/3
    assert abs(reports["low_evidence_disclaim_rate"].value - 2 / 3) < 1e-9


def test_aggregate_emits_six_reports():
    records = [_make_record() for _ in range(3)]
    reports = aggregate(records)
    names = {r.sli_name for r in reports}
    assert names == {
        "accept_latency_ms",
        "first_token_latency_ms",
        "completion_latency_ms",
        "task_success_rate",
        "citation_coverage",
        "low_evidence_disclaim_rate",
    }


def test_aggregate_raises_on_empty_records():
    with pytest.raises(ValueError, match="empty"):
        aggregate([])
```

- [ ] **Step 2：运行测试，确认失败**

Run: `uv run pytest tests/test_slo_aggregator.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'slo.aggregator'`。

- [ ] **Step 3：实现 aggregator**

Create `slo/aggregator.py`:

```python
"""SLO 聚合：把 RunRecord 列表聚合为 SliReport 列表。

纯函数，无 IO。聚合规则文档化在 docs/superpowers/plans/017-... 计划文件。
"""
from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class RunRecord:
    item_id: str
    category: str
    success: bool
    accept_latency_ms: float
    first_token_latency_ms: float
    completion_latency_ms: float
    has_citations: bool
    expected_citations: bool
    rag_low_evidence: bool
    reply_has_disclaimer: bool


@dataclass(frozen=True)
class SliReport:
    sli_name: str
    aggregation: str
    value: float
    sample_size: int


def _percentile(sorted_values: list[float], pct: float) -> float:
    """nearest-rank percentile（与 Python statistics 默认 inclusive 一致的简化版）。"""
    if not sorted_values:
        raise ValueError("percentile on empty list")
    # rank = ceil(pct * n) - 1，clamp 到 [0, n-1]
    n = len(sorted_values)
    idx = max(0, min(n - 1, math.ceil(pct * n) - 1))
    return float(sorted_values[idx])


def aggregate(records: list[RunRecord]) -> list[SliReport]:
    if not records:
        raise ValueError("aggregate(records) called on empty list")

    n = len(records)
    accept = sorted(r.accept_latency_ms for r in records)
    first_tok = sorted(r.first_token_latency_ms for r in records)
    complete = sorted(r.completion_latency_ms for r in records)

    success_rate = sum(1 for r in records if r.success) / n

    expected_total = sum(1 for r in records if r.expected_citations)
    cited_hits = sum(1 for r in records if r.expected_citations and r.has_citations)
    citation_coverage = (cited_hits / expected_total) if expected_total > 0 else 1.0

    low_ev_total = sum(1 for r in records if r.rag_low_evidence)
    disclaim_hits = sum(
        1 for r in records if r.rag_low_evidence and r.reply_has_disclaimer
    )
    disclaim_rate = (disclaim_hits / low_ev_total) if low_ev_total > 0 else 1.0

    return [
        SliReport("accept_latency_ms", "p95", _percentile(accept, 0.95), n),
        SliReport("first_token_latency_ms", "p95", _percentile(first_tok, 0.95), n),
        SliReport("completion_latency_ms", "p95", _percentile(complete, 0.95), n),
        SliReport("task_success_rate", "ratio", success_rate, n),
        SliReport("citation_coverage", "ratio", citation_coverage, n),
        SliReport("low_evidence_disclaim_rate", "ratio", disclaim_rate, n),
    ]
```

- [ ] **Step 4：运行测试，确认通过**

Run: `uv run pytest tests/test_slo_aggregator.py -v`
Expected: 7 PASS / 0 FAIL.

- [ ] **Step 5：Commit**

```bash
git add slo/aggregator.py tests/test_slo_aggregator.py
git commit -m "feat(slo): aggregate RunRecord into SliReport with p95 / ratio rules (phase 3c task 2)"
```

---

## Task 3：实现 checker（阈值比对）（TDD）

### Files
- Create: `slo/checker.py`
- Test: `tests/test_slo_checker.py`

### 数据契约

```python
@dataclass(frozen=True)
class Breach:
    sli_name: str
    direction: str
    threshold: float
    actual: float

@dataclass(frozen=True)
class CheckResult:
    passed: bool
    breaches: list[Breach]
    skipped: list[str]   # 阈值文件里有但 SliReport 缺失的（aggregator 未实现的，比如 retry_recovery_rate）
```

### Steps

- [ ] **Step 1：写失败测试**

Create `tests/test_slo_checker.py`:

```python
"""Phase 3c Task 3：SLO checker 比对阈值。"""
from slo.aggregator import SliReport
from slo.loader import Threshold
from slo.checker import check, CheckResult, Breach


def test_all_within_threshold_passes():
    thresholds = [
        Threshold("completion_latency_ms", "<=", 15000, "p95"),
        Threshold("task_success_rate", ">=", 0.97, "ratio"),
    ]
    reports = [
        SliReport("completion_latency_ms", "p95", 12000, 12),
        SliReport("task_success_rate", "ratio", 0.99, 12),
    ]
    result = check(reports, thresholds)
    assert isinstance(result, CheckResult)
    assert result.passed is True
    assert result.breaches == []


def test_le_breach_when_actual_above_threshold():
    thresholds = [Threshold("completion_latency_ms", "<=", 15000, "p95")]
    reports = [SliReport("completion_latency_ms", "p95", 18000, 12)]
    result = check(reports, thresholds)
    assert result.passed is False
    assert result.breaches == [
        Breach("completion_latency_ms", "<=", 15000, 18000)
    ]


def test_ge_breach_when_actual_below_threshold():
    thresholds = [Threshold("task_success_rate", ">=", 0.97, "ratio")]
    reports = [SliReport("task_success_rate", "ratio", 0.85, 12)]
    result = check(reports, thresholds)
    assert result.passed is False
    assert result.breaches[0].sli_name == "task_success_rate"


def test_missing_sli_is_recorded_in_skipped_not_breach():
    """阈值定义了但 aggregator 没产出 → 计入 skipped，不算违反。"""
    thresholds = [
        Threshold("retry_recovery_rate", ">=", 0.70, "ratio"),
        Threshold("task_success_rate", ">=", 0.97, "ratio"),
    ]
    reports = [SliReport("task_success_rate", "ratio", 0.99, 12)]
    result = check(reports, thresholds)
    assert result.passed is True
    assert result.breaches == []
    assert result.skipped == ["retry_recovery_rate"]


def test_multiple_breaches_all_collected():
    thresholds = [
        Threshold("completion_latency_ms", "<=", 15000, "p95"),
        Threshold("task_success_rate", ">=", 0.97, "ratio"),
    ]
    reports = [
        SliReport("completion_latency_ms", "p95", 18000, 12),
        SliReport("task_success_rate", "ratio", 0.85, 12),
    ]
    result = check(reports, thresholds)
    assert result.passed is False
    assert len(result.breaches) == 2
```

- [ ] **Step 2：运行测试，确认失败**

Run: `uv run pytest tests/test_slo_checker.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'slo.checker'`。

- [ ] **Step 3：实现 checker**

Create `slo/checker.py`:

```python
"""SLO 阈值比对：把 SliReport + Threshold 列表对齐 → CheckResult。

纯函数，无 IO。
"""
from __future__ import annotations

from dataclasses import dataclass

from slo.aggregator import SliReport
from slo.loader import Threshold


@dataclass(frozen=True)
class Breach:
    sli_name: str
    direction: str
    threshold: float
    actual: float


@dataclass(frozen=True)
class CheckResult:
    passed: bool
    breaches: list[Breach]
    skipped: list[str]


def check(reports: list[SliReport], thresholds: list[Threshold]) -> CheckResult:
    by_name = {r.sli_name: r for r in reports}
    breaches: list[Breach] = []
    skipped: list[str] = []
    for t in thresholds:
        report = by_name.get(t.name)
        if report is None:
            skipped.append(t.name)
            continue
        actual = report.value
        ok = (
            actual <= t.threshold if t.direction == "<="
            else actual >= t.threshold
        )
        if not ok:
            breaches.append(Breach(t.name, t.direction, t.threshold, actual))
    return CheckResult(passed=not breaches, breaches=breaches, skipped=skipped)
```

- [ ] **Step 4：运行测试，确认通过**

Run: `uv run pytest tests/test_slo_checker.py -v`
Expected: 5 PASS / 0 FAIL.

- [ ] **Step 5：Commit**

```bash
git add slo/checker.py tests/test_slo_checker.py
git commit -m "feat(slo): threshold checker with breach + skipped reporting (phase 3c task 3)"
```

---

## Task 4：实现 run_regression CLI（TDD）

### Files
- Create: `slo/run_regression.py`
- Test: `tests/test_slo_run_regression.py`

### 设计契约

- 入口：`python -m slo.run_regression`
- 流程：
    1. `load_thresholds` + `load_regression_set`
    2. for each item：调 `agent_service.run(...)` 同步路径，包一层计时器与 sink 收集 token
    3. 把每条 result 转成 `RunRecord`
    4. `aggregate` → `check`
    5. 打印报告（人类可读 + 关键数字）
    6. exit 0（passed）/ 1（breach）/ 2（IO 异常）
- **强制同步路径**：函数内 `monkey-patch settings.async_graph_enabled = False`，避免依赖 Redis/Celery
- **首 token 计时器**：使用 `progress_sink` 在收到第一个 `("token", piece)` 时记录时间戳；若整次没 token 事件（非流式纯返回），则取 `completion_latency_ms` 作为 fallback
- **disclaimer 检测**：用一组中文关键词列表 `["证据不足", "信息有限", "无法确定", "建议进一步查阅"]`；reply 包含任一即视为有声明语

### Steps

- [ ] **Step 1：写失败测试**

Create `tests/test_slo_run_regression.py`:

```python
"""Phase 3c Task 4：run_regression CLI 行为。"""
from pathlib import Path
import pytest

import slo.run_regression as rr


@pytest.fixture
def stub_agent_pass(monkeypatch):
    """全部 12 题都成功、有 citations、低延迟，预期 SLO 全部达标。"""
    counter = {"n": 0}

    def fake_run(session_id, topic, user_input, user_id=None,
                 stream_output=False, progress_sink=None):
        counter["n"] += 1
        if progress_sink:
            progress_sink("token", "tok-1")
        return {
            "session_id": session_id,
            "stage": "explained",
            "reply": "回答内容",
            "citations": [{"chunk_id": "c1"}],
            "rag_low_evidence": False,
        }

    from app.services import agent_service as agent_mod
    monkeypatch.setattr(agent_mod.agent_service, "run", fake_run)
    return counter


@pytest.fixture
def stub_agent_breach(monkeypatch):
    """全部失败，预期 task_success_rate < 0.97。"""
    def fake_run(**kwargs):
        return {
            "session_id": kwargs["session_id"],
            "stage": "unknown",
            "reply": "",
        }

    from app.services import agent_service as agent_mod
    monkeypatch.setattr(agent_mod.agent_service, "run", fake_run)


def test_run_regression_returns_zero_when_all_pass(stub_agent_pass):
    exit_code = rr.main(argv=[])
    assert exit_code == 0
    assert stub_agent_pass["n"] == 12  # 12 题全跑完


def test_run_regression_returns_one_when_any_breach(stub_agent_breach):
    exit_code = rr.main(argv=[])
    assert exit_code == 1


def test_disclaimer_detector_recognizes_keywords():
    assert rr._reply_has_disclaimer("当前证据不足，建议进一步查阅资料。") is True
    assert rr._reply_has_disclaimer("信息有限，无法确定准确答案。") is True
    assert rr._reply_has_disclaimer("这是一道明确的数学题。") is False


def test_run_regression_returns_two_on_yaml_error(monkeypatch, tmp_path):
    """阈值文件路径错误时 exit code = 2。"""
    monkeypatch.setattr(rr, "_DEFAULT_THRESHOLDS_PATH", tmp_path / "missing.yaml")
    exit_code = rr.main(argv=[])
    assert exit_code == 2
```

- [ ] **Step 2：运行测试，确认失败**

Run: `uv run pytest tests/test_slo_run_regression.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'slo.run_regression'`。

- [ ] **Step 3：实现 runner**

Create `slo/run_regression.py`:

```python
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
    except Exception as exc:
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
```

- [ ] **Step 4：运行测试，确认通过**

Run: `uv run pytest tests/test_slo_run_regression.py -v`
Expected: 4 PASS / 0 FAIL.

- [ ] **Step 5：Commit**

```bash
git add slo/run_regression.py tests/test_slo_run_regression.py
git commit -m "feat(slo): add run_regression CLI with exit-code SLO gate (phase 3c task 4)"
```

---

## Task 5：v1 基线建立 + 验证门禁有效性

### Files
- 无（仅运行验证 + 记录基线）

### Steps

- [ ] **Step 1：跑 SLO 检查（注入 stub agent，不调真实 LLM）**

由于本地真实 LLM 调用受 OpenAI key 限制，先用一个临时脚本注入 stub agent 验证 runner 能跑通：

Run（创建临时 fixture 脚本）:

```bash
cat > /tmp/slo_smoke.py <<'EOF'
"""临时烟雾测试：用 stub agent 跑一次 SLO，确认基线能 PASS。"""
import sys
sys.path.insert(0, ".")

from app.services import agent_service as agent_mod
from slo.run_regression import main


def fake_run(session_id, topic, user_input, user_id=None,
             stream_output=False, progress_sink=None):
    if progress_sink:
        progress_sink("token", "stub")
    return {
        "session_id": session_id,
        "stage": "explained",
        "reply": "stub 回答",
        "citations": [{"chunk_id": "c1"}],
        "rag_low_evidence": False,
    }


agent_mod.agent_service.run = fake_run
sys.exit(main([]))
EOF
```

Run: `uv run python /tmp/slo_smoke.py`
Expected: stdout 显示 12 题全跑完，状态 PASS，退出码 0。

- [ ] **Step 2：故意把阈值调严，验证门禁有效**

Run（临时修改阈值）:

```bash
# 备份
cp slo/thresholds.yaml slo/thresholds.yaml.bak

# 把 task_success_rate 调到 1.01（不可达）
sed -i 's/threshold: 0.97/threshold: 1.01/' slo/thresholds.yaml

# 跑 smoke 应失败
uv run python /tmp/slo_smoke.py; echo "exit=$?"

# 还原
mv slo/thresholds.yaml.bak slo/thresholds.yaml
```

Expected: 输出含 `task_success_rate: 1.000 >= 1.01 VIOLATED`，退出码 1。

- [ ] **Step 3：跑 Phase 3c 全套测试**

Run: `uv run pytest tests/test_slo_loader.py tests/test_slo_aggregator.py tests/test_slo_checker.py tests/test_slo_run_regression.py -v`
Expected: 22 PASS / 0 FAIL（6 + 7 + 5 + 4）。

- [ ] **Step 4：跑全量回归**

Run: `PYTHONPATH=. DEBUG=false uv run pytest tests/ -q`
Expected: ≥ `346 passed / 19 failed`（324 PASS 基线 + 22 SLO 新增 = 346；失败数维持 19）。

- [ ] **Step 5：清理临时文件**

```bash
rm -f /tmp/slo_smoke.py
```

- [ ] **Step 6：Commit（仅 Phase 3c 执行日志摘要，不含临时脚本）**

由于本步无文件改动，跳过 commit。如果你想把基线写进 plans/，单独一次 commit：

```bash
# 可选：写一份执行日志
git status
# 若 working tree 干净，跳过；若你想加执行日志按 phase 7 模式追加：
# docs/superpowers/plans/018-2026-05-02-phase3c-execution-log.md
```

---

## 验收清单（Phase 3c 整体）

| 项 | 阈值 / 验证方式 |
|---|---|
| 阈值文件 | `slo/thresholds.yaml` 含 6 个 SLI（v1 单人本地基线，retry_recovery_rate 暂不实施） |
| 回归集 | `slo/regression_set.yaml` 含 12 题，4 类 × 3 题 |
| Loader | YAML → 数据类正确解析；缺字段抛 ValueError |
| Aggregator | p95 / ratio 规则覆盖；citation_coverage 用"应引用"作分母；low_evidence 全 false 时返回 1.0 |
| Checker | breach / skipped 区分；多 breach 全收集 |
| Runner | exit 0 PASS / 1 breach / 2 IO 错误；强制同步路径不依赖 Redis/Celery |
| 回归 | ≥ 346 PASS / 19 FAIL（不退化） |
| 入口 | `uv run python -m slo.run_regression` 可一键跑 |

---

## Self-Review 备注

1. **Spec §11.3 交付清单**：
    - `slo/thresholds.yaml` → Task 1 ✓
    - `slo/regression_set.yaml` → Task 1 ✓
    - `slo/run_regression.py` → Task 4 ✓
    - `Makefile` `make slo-check` → **改为 `uv run python -m slo.run_regression`**（差异已在 plan 头部声明）
    - `tests/test_slo_threshold_loader.py` → Task 1（命名用 `test_slo_loader.py`）✓
    - `tests/test_slo_aggregator.py` → Task 2 ✓

   补充：`tests/test_slo_checker.py`（Task 3）+ `tests/test_slo_run_regression.py`（Task 4）+ `slo/checker.py` 把阈值比对从 runner 中独立出来，便于单测。

2. **Spec §8 数据源差异**：spec 计划 SLI 从 Langfuse trace 派生；本计划 v1 改为从 result state + 本地计时器派生。理由：
    - 本地 SLO 检查应能在裸机跑通（不依赖 Langfuse server 可达）
    - Langfuse v4 的查询 API 在当前依赖版本未稳定
    - aggregator/checker 是纯函数，将来切到 Langfuse 数据源只需替换 `_run_one`

3. **类型一致性**：
    - `Threshold.direction` 全程 `Literal["<=", ">="]`
    - `Threshold.aggregation` 全程 `Literal["p50","p95","p99","mean","ratio"]`
    - `RunRecord` / `SliReport` / `Breach` / `CheckResult` 全部 `frozen=True`，避免被外部误改

4. **Placeholders**：本计划无 TBD/TODO；retry_recovery_rate 的"占位"是显式设计决策（CheckResult.skipped 列表），不是计划级 placeholder。

5. **回归测试影响**：本计划仅新增 `slo/` 目录与对应 `tests/test_slo_*.py`，不改任何既有源码或测试。失败基线 19 不会被本计划扰动。
