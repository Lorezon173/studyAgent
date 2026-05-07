# Phase 3d：看板 / 告警 / runbook 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 Phase 3 收尾：把 trace + SLO 能力升级为可运营的"看板 + 告警 + runbook + on-call 文档"四件套，让一个独立运维者能用本仓库的资产完成启停、回滚、容量、故障定位、发布检查。

**Architecture:** 不引入定时器/守护进程。alert_evaluator 是纯函数 `(reports, thresholds, rules) -> list[Alert]`，由 `run_regression.py` 在每次跑回归时直接驱动；rules 文件 `slo/alert_rules.yaml` 用 breach-count 分级（不依赖时序数据，未来扩展时间维度只需追加字段）。Dashboard 不强求 Langfuse 实际配置，而是仓库内沉淀 schema + 导出脚本占位 + README 入口。Runbook 是 markdown 文档但内容必须可直接执行（明示命令）。

**Tech Stack:** Python 3.12 + pyyaml（已在依赖中）+ pytest。无新增运行时依赖。

**Spec 来源：** [docs/superpowers/specs/top-007-2026-05-01-phase3-finalization-design.md](../specs/top-007-2026-05-01-phase3-finalization-design.md) §9（可观测运营化）+ §10（Runbook）+ §11.4（子阶段 3d 交付）。

**前置：** Phase 3a/3b/3c 已交付（PR #1/#2/#3 已合，Phase 3c 本地已合）。本计划不修改 SLO 任何已存在文件，仅追加新模块 + 新文档。

---

## Spec 与本计划的差异声明（务实版）

| Spec 描述 | 本计划做法 | 理由 |
|---|---|---|
| WARN：SLI 连续 5 分钟超阈值 | 改为 breach-count 分级（一次 check 内的 breach 数量） | v1 无时序数据持久化；时间维度留给云上扩展 |
| `alert_evaluator` 周期性读 SLI | 改为纯函数，由 `run_regression.py` 一次性调用 | YAGNI；不引入守护进程 |
| 4 个 Langfuse dashboard JSON | 仅落 schema 文档 + 导出脚本占位 | Langfuse v4 dashboard 创建 API 不稳定；JSON 必须从真实 Langfuse 实例手动导出 |
| Langfuse 内置 alert | 仅在 alert_rules.yaml 里注释钩子位 | 同上；本地无 Langfuse server 持续运行 |
| `notify-send` 桌面通知 | 在 alert_evaluator 里仅打 log（CRIT 级），不依赖系统调用 | Windows 没 notify-send；保持纯 Python |

spec 验收口径在 §11.4 的"6 个 runbook 文件 + 4 个 dashboard JSON"将被本计划改为：
- 6 份 runbook + 1 份 on-call（spec §10 已修正过 = 7 份 markdown）
- dashboard 4 份 → schema 1 份（覆盖 4 类面板的字段定义）+ README 入口 1 份

差异在 PR 描述中显式声明。

---

## File Structure

| 文件 | 类型 | 责任 | 边界 |
|---|---|---|---|
| `slo/alert_rules.yaml` | 新增 | 告警规则数据 | 纯数据 |
| `slo/alert_evaluator.py` | 新增 | 纯函数：reports + rules → Alert 列表 + 写日志 | 不调度、不通知 |
| `tests/test_slo_alert_evaluator.py` | 新增 | breach 分级、日志写入、CRIT 触发的单元测试 | — |
| `slo/run_regression.py` | 修改 | 在 _print_report 后调用 alert_evaluator | 仅追加 alert 段落 |
| `tests/test_slo_run_regression.py` | 修改 | 增 1 个测试：runner 输出含 alert 段落 | — |
| `docs/observability/README.md` | 新增 | 看板入口；列 4 类面板 + 手动导入指引 | — |
| `docs/observability/dashboards/schema.md` | 新增 | 4 类面板字段说明（latency/stability/quality/链路） | — |
| `docs/observability/dashboards/export_template.json` | 新增 | Langfuse dashboard 导出模板占位（含字段标记） | — |
| `docs/runbook/00_index.md` | 新增 | 决策树 + 入口 | — |
| `docs/runbook/01_startup_shutdown.md` | 新增 | Redis → Celery worker → uvicorn 启停顺序 | — |
| `docs/runbook/02_rollback.md` | 新增 | feature flag 关 → 进程重启 → 验证 | — |
| `docs/runbook/03_capacity.md` | 新增 | worker 并发 / 队列优先级 / Redis 容量 | — |
| `docs/runbook/04_troubleshooting.md` | 新增 | 5 类故障：worker 卡住 / 队列积压 / broker 失联 / SSE 断流 / LLM 限流 | — |
| `docs/runbook/05_release_checklist.md` | 新增 | 全量回归 / SLO 门禁 / 阈值差比 / 变更影响 | — |
| `docs/runbook/oncall_response.md` | 新增 | 3 场景响应矩阵 | — |
| `README.md` 顶部 | 修改 | 增加"运维入口"链接 → runbook + observability | — |

**边界原则：**

1. `alert_evaluator` 是纯函数；写日志的 IO 在 evaluator 内部但与决策逻辑分离（私有 `_write_log` 可注入 mock）。
2. Runbook 文档每份必须**至少 2 个具体场景**，每个场景有明确命令或决策步骤；不写"应该考虑"之类的虚词。
3. 不修改 spec、不修改 plan #017、不动 chat.py / agent_service.py / worker。

---

## Task 1：alert_rules.yaml + alert_evaluator（TDD）

### Files
- Create: `slo/alert_rules.yaml`
- Create: `slo/alert_evaluator.py`
- Test: `tests/test_slo_alert_evaluator.py`
- Modify: `.gitignore`

### 数据契约

```yaml
# slo/alert_rules.yaml
version: "v1"
log_path: "logs/slo_alerts.log"   # 相对仓库根
severity_rules:
  # INFO：有 1 个 SLI 接近阈值（actual 在阈值的 90%-100% 区间内）
  - severity: "INFO"
    trigger: "near_threshold"
    margin: 0.10                   # 距阈值 10% 内
  # WARN：有 1 个或多个 SLI 实际超出阈值
  - severity: "WARN"
    trigger: "any_breach"
  # CRIT：task_success_rate < 0.90（硬指标，绕过 thresholds.yaml）
  - severity: "CRIT"
    trigger: "hard_breach"
    sli: "task_success_rate"
    direction: "<"
    value: 0.90
# 云上钩子位（v1 不启用）
# webhook_url: ""
```

```python
# alert_evaluator API
@dataclass(frozen=True)
class Alert:
    severity: str       # "INFO" | "WARN" | "CRIT"
    sli_name: str
    actual: float
    rule_summary: str   # "actual 1.85s within 10% of 2.0s threshold"

def evaluate(
    reports: list[SliReport],
    thresholds: list[Threshold],
    rules: list[dict],
    log_path: Path | None = None,
) -> list[Alert]
```

### 触发逻辑（明确说清楚）

对每条 `severity_rule`：

- **`near_threshold`（INFO）**：遍历每个 (report, threshold) 对，如果 actual 已经 breach 则跳过（让 WARN 接走），否则按方向算"接近度"：
    - direction `<=`：actual / threshold ≥ (1 - margin) 即触发，即 actual 在 [threshold * 0.9, threshold] 区间内
    - direction `>=`：actual / threshold ≤ (1 + margin) 即触发，即 actual 在 [threshold, threshold / (1 - margin)] 区间内（阈值的 1.11 倍以内）
- **`any_breach`（WARN）**：使用 checker 的 breach 列表，每个 breach 产出一个 Alert
- **`hard_breach`（CRIT）**：找到 `sli=task_success_rate` 的 report，actual `<` 0.90 时触发

写日志：把所有 Alert 用 `[<timestamp>] <severity> <sli_name>: <rule_summary>` 格式 append 到 `log_path`（创建父目录），每条一行。

### Steps

- [ ] **Step 1：创建 alert_rules.yaml**

Create `slo/alert_rules.yaml`：

```yaml
version: "v1"
log_path: "logs/slo_alerts.log"
severity_rules:
  - severity: "INFO"
    trigger: "near_threshold"
    margin: 0.10
  - severity: "WARN"
    trigger: "any_breach"
  - severity: "CRIT"
    trigger: "hard_breach"
    sli: "task_success_rate"
    direction: "<"
    value: 0.90
```

- [ ] **Step 2：写失败测试**

Create `tests/test_slo_alert_evaluator.py`:

```python
"""Phase 3d Task 1：alert_evaluator 触发与日志。"""
from pathlib import Path
import pytest

from slo.aggregator import SliReport
from slo.loader import Threshold
from slo.alert_evaluator import Alert, evaluate, load_alert_rules


REPO_ROOT = Path(__file__).resolve().parent.parent


def _info_rule():
    return [{"severity": "INFO", "trigger": "near_threshold", "margin": 0.10}]


def _warn_rule():
    return [{"severity": "WARN", "trigger": "any_breach"}]


def _crit_rule():
    return [
        {
            "severity": "CRIT",
            "trigger": "hard_breach",
            "sli": "task_success_rate",
            "direction": "<",
            "value": 0.90,
        }
    ]


def test_load_alert_rules_from_yaml():
    rules_data = load_alert_rules(REPO_ROOT / "slo" / "alert_rules.yaml")
    assert rules_data["version"] == "v1"
    assert "severity_rules" in rules_data
    severities = {r["severity"] for r in rules_data["severity_rules"]}
    assert severities == {"INFO", "WARN", "CRIT"}


def test_no_alert_when_all_within_safe_zone():
    """所有 actual 距阈值 > 10%，不触发任何 alert。"""
    thresholds = [Threshold("completion_latency_ms", "<=", 1000, "p95")]
    reports = [SliReport("completion_latency_ms", "p95", 500, 12)]
    alerts = evaluate(reports, thresholds, _info_rule() + _warn_rule())
    assert alerts == []


def test_info_when_near_le_threshold():
    """direction <= 时 actual 在 [threshold*0.9, threshold] 内触发 INFO。"""
    thresholds = [Threshold("completion_latency_ms", "<=", 1000, "p95")]
    reports = [SliReport("completion_latency_ms", "p95", 950, 12)]  # 95% 利用率
    alerts = evaluate(reports, thresholds, _info_rule())
    assert len(alerts) == 1
    assert alerts[0].severity == "INFO"
    assert alerts[0].sli_name == "completion_latency_ms"


def test_info_when_near_ge_threshold():
    """direction >= 时 actual 在 [threshold, threshold*1.11] 内触发 INFO。"""
    thresholds = [Threshold("task_success_rate", ">=", 0.97, "ratio")]
    reports = [SliReport("task_success_rate", "ratio", 0.975, 12)]  # 略高于阈值，但靠近
    alerts = evaluate(reports, thresholds, _info_rule())
    # 0.975 / 0.97 = 1.005，在 [1.0, 1.0/(1-0.10)=1.111] 内 → INFO
    assert len(alerts) == 1
    assert alerts[0].severity == "INFO"


def test_warn_when_any_breach():
    """超阈值的 SLI 触发 WARN（不再触发 INFO）。"""
    thresholds = [
        Threshold("completion_latency_ms", "<=", 1000, "p95"),
        Threshold("task_success_rate", ">=", 0.97, "ratio"),
    ]
    reports = [
        SliReport("completion_latency_ms", "p95", 1500, 12),  # breach
        SliReport("task_success_rate", "ratio", 0.99, 12),     # safe
    ]
    alerts = evaluate(reports, thresholds, _info_rule() + _warn_rule())
    severities = [a.severity for a in alerts]
    assert "WARN" in severities
    # breach 的 SLI 不应再被 INFO 触发
    breached = [a for a in alerts if a.sli_name == "completion_latency_ms"]
    assert {a.severity for a in breached} == {"WARN"}


def test_crit_when_task_success_rate_below_hard_threshold():
    """task_success_rate < 0.90 触发 CRIT，绕过 thresholds.yaml。"""
    thresholds = [Threshold("task_success_rate", ">=", 0.97, "ratio")]
    reports = [SliReport("task_success_rate", "ratio", 0.85, 12)]
    alerts = evaluate(reports, thresholds, _warn_rule() + _crit_rule())
    severities = [a.severity for a in alerts]
    assert "CRIT" in severities
    assert "WARN" in severities  # CRIT 与 WARN 同时触发（独立判断）


def test_evaluator_writes_log(tmp_path):
    """alerts 写日志（每条一行）。"""
    log = tmp_path / "alerts.log"
    thresholds = [Threshold("completion_latency_ms", "<=", 1000, "p95")]
    reports = [SliReport("completion_latency_ms", "p95", 1500, 12)]
    alerts = evaluate(reports, thresholds, _warn_rule(), log_path=log)
    assert len(alerts) == 1
    contents = log.read_text(encoding="utf-8")
    assert "WARN" in contents
    assert "completion_latency_ms" in contents
    # 时间戳格式：[YYYY-MM-DD HH:MM:SS]
    assert contents.strip().startswith("[")


def test_evaluator_creates_log_parent_dir(tmp_path):
    """log_path 父目录不存在时应自动创建。"""
    log = tmp_path / "deep" / "nested" / "alerts.log"
    thresholds = [Threshold("task_success_rate", ">=", 0.97, "ratio")]
    reports = [SliReport("task_success_rate", "ratio", 0.85, 12)]
    evaluate(reports, thresholds, _warn_rule(), log_path=log)
    assert log.exists()


def test_evaluator_returns_empty_when_no_rules():
    thresholds = [Threshold("completion_latency_ms", "<=", 1000, "p95")]
    reports = [SliReport("completion_latency_ms", "p95", 1500, 12)]
    alerts = evaluate(reports, thresholds, [])
    assert alerts == []
```

- [ ] **Step 3：运行测试，确认失败**

Run: `uv run pytest tests/test_slo_alert_evaluator.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'slo.alert_evaluator'`。

- [ ] **Step 4：实现 alert_evaluator**

Create `slo/alert_evaluator.py`:

```python
"""SLO 告警评估器。

纯函数：把 SliReport + Threshold + alert_rules 列表 → Alert 列表，
可选写入日志。无定时器、无守护进程。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from slo.aggregator import SliReport
from slo.checker import check
from slo.loader import Threshold


@dataclass(frozen=True)
class Alert:
    severity: str
    sli_name: str
    actual: float
    rule_summary: str


def load_alert_rules(path: Path) -> dict[str, Any]:
    """加载 alert_rules.yaml 顶层结构。"""
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _is_near_le(actual: float, threshold: float, margin: float) -> bool:
    """direction <= 时，actual 在 [threshold * (1-margin), threshold] 内即接近。"""
    if actual > threshold:
        return False
    return actual >= threshold * (1 - margin)


def _is_near_ge(actual: float, threshold: float, margin: float) -> bool:
    """direction >= 时，actual 在 [threshold, threshold/(1-margin)] 内即接近。"""
    if actual < threshold:
        return False
    upper = threshold / (1 - margin) if margin < 1 else float("inf")
    return actual <= upper


def evaluate(
    reports: list[SliReport],
    thresholds: list[Threshold],
    rules: list[dict],
    log_path: Path | None = None,
) -> list[Alert]:
    by_name_report = {r.sli_name: r for r in reports}
    by_name_threshold = {t.name: t for t in thresholds}
    breach_set = {b.sli_name for b in check(reports, thresholds).breaches}

    alerts: list[Alert] = []
    for rule in rules:
        severity = rule.get("severity", "INFO")
        trigger = rule.get("trigger", "")
        if trigger == "near_threshold":
            margin = float(rule.get("margin", 0.10))
            for t in thresholds:
                if t.name in breach_set:
                    continue
                report = by_name_report.get(t.name)
                if report is None:
                    continue
                near = (
                    _is_near_le(report.value, t.threshold, margin)
                    if t.direction == "<="
                    else _is_near_ge(report.value, t.threshold, margin)
                )
                if near:
                    summary = (
                        f"actual {report.value:.3f} within {int(margin * 100)}% "
                        f"of {t.direction} {t.threshold} threshold"
                    )
                    alerts.append(Alert(severity, t.name, report.value, summary))
        elif trigger == "any_breach":
            for sli_name in breach_set:
                report = by_name_report.get(sli_name)
                t = by_name_threshold.get(sli_name)
                if report is None or t is None:
                    continue
                summary = (
                    f"actual {report.value:.3f} {t.direction} {t.threshold} VIOLATED"
                )
                alerts.append(Alert(severity, sli_name, report.value, summary))
        elif trigger == "hard_breach":
            sli_name = rule.get("sli", "")
            direction = rule.get("direction", "<")
            value = float(rule.get("value", 0.0))
            report = by_name_report.get(sli_name)
            if report is None:
                continue
            triggered = (
                report.value < value if direction == "<"
                else report.value > value if direction == ">"
                else False
            )
            if triggered:
                summary = f"hard breach: {report.value:.3f} {direction} {value}"
                alerts.append(Alert(severity, sli_name, report.value, summary))

    if log_path is not None and alerts:
        log_path = Path(log_path)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with log_path.open("a", encoding="utf-8") as f:
            for a in alerts:
                f.write(f"[{ts}] {a.severity} {a.sli_name}: {a.rule_summary}\n")

    return alerts
```

- [ ] **Step 5：在 .gitignore 加白名单**

Edit `.gitignore`，在 SLO 测试白名单段尾追加：

```
!tests/test_slo_alert_evaluator.py
```

- [ ] **Step 6：运行测试，确认通过**

Run: `uv run pytest tests/test_slo_alert_evaluator.py -v`
Expected: 9 PASS / 0 FAIL。

- [ ] **Step 7：Commit**

```bash
git add slo/alert_rules.yaml slo/alert_evaluator.py tests/test_slo_alert_evaluator.py .gitignore
git commit -m "feat(slo): add alert_evaluator with INFO/WARN/CRIT severity rules (phase 3d task 1)"
```

---

## Task 2：把 alert_evaluator 接入 run_regression（TDD）

### Files
- Modify: `slo/run_regression.py`
- Modify: `tests/test_slo_run_regression.py`

### 设计契约

`run_regression.main()` 在 `_print_report` 之后：
1. 加载 `slo/alert_rules.yaml`
2. 调 `evaluate(reports, thresholds, rules['severity_rules'], log_path=log_path)`
3. 把 alerts 数量打印到终端（`Alerts: 1 INFO, 0 WARN, 0 CRIT`），不影响退出码

如果 alert_rules.yaml 不存在或解析失败：**不要让整个 SLO check 失败**，仅打印 `Alerts: skipped (rules unavailable)`。

### Steps

- [ ] **Step 1：写失败测试**

Edit `tests/test_slo_run_regression.py`，在文件末尾追加：

```python
def test_run_regression_emits_alert_summary(stub_agent_pass, capsys):
    """通过路径下 alert 数量为 0 但应打印 Alerts: 段落。"""
    rr.main(argv=[])
    out = capsys.readouterr().out
    assert "Alerts:" in out


def test_run_regression_alert_skipped_when_rules_missing(
    stub_agent_pass, capsys, monkeypatch, tmp_path
):
    """alert_rules.yaml 不存在时 alert 段落应显示 skipped，不影响退出码。"""
    monkeypatch.setattr(rr, "_DEFAULT_ALERT_RULES_PATH", tmp_path / "missing.yaml")
    exit_code = rr.main(argv=[])
    assert exit_code == 0  # 阈值都达标，仍 PASS
    out = capsys.readouterr().out
    assert "Alerts: skipped" in out
```

- [ ] **Step 2：运行测试，确认失败**

Run: `uv run pytest tests/test_slo_run_regression.py::test_run_regression_emits_alert_summary tests/test_slo_run_regression.py::test_run_regression_alert_skipped_when_rules_missing -v`
Expected: FAIL，`AttributeError: module 'slo.run_regression' has no attribute '_DEFAULT_ALERT_RULES_PATH'` 或 alert 段落不存在。

- [ ] **Step 3：修改 run_regression.py**

Edit `slo/run_regression.py`：

在文件顶部 import 段加：

```python
from slo.alert_evaluator import Alert, evaluate as evaluate_alerts, load_alert_rules
```

在 `_DEFAULT_REGRESSION_PATH` 后加：

```python
_DEFAULT_ALERT_RULES_PATH = _REPO_ROOT / "slo" / "alert_rules.yaml"
```

在 `_print_report` 函数之后（main 之前）增加：

```python
def _print_alerts(alerts: list[Alert] | None) -> None:
    if alerts is None:
        print("  Alerts: skipped (rules unavailable)")
        return
    by_severity = {"INFO": 0, "WARN": 0, "CRIT": 0}
    for a in alerts:
        by_severity[a.severity] = by_severity.get(a.severity, 0) + 1
    print(
        f"  Alerts: {by_severity['INFO']} INFO, "
        f"{by_severity['WARN']} WARN, {by_severity['CRIT']} CRIT"
    )
    for a in alerts:
        print(f"    [{a.severity}] {a.sli_name}: {a.rule_summary}")
```

修改 `main` 函数，在 `_print_report(reports, result)` 之后插入 alert 调用：

```python
    # 加载 alert rules（失败不影响 SLO 退出码）
    alerts: list[Alert] | None
    try:
        rules_data = load_alert_rules(_DEFAULT_ALERT_RULES_PATH)
        rules = rules_data.get("severity_rules", [])
        log_path_str = rules_data.get("log_path")
        log_path = _REPO_ROOT / log_path_str if log_path_str else None
        alerts = evaluate_alerts(reports, thresholds, rules, log_path=log_path)
    except (FileNotFoundError, OSError, ValueError):
        alerts = None
    _print_alerts(alerts)

    return 0 if result.passed else 1
```

- [ ] **Step 4：运行测试，确认通过**

Run: `uv run pytest tests/test_slo_run_regression.py -v`
Expected: 6 PASS / 0 FAIL（原 4 + 新 2）。

- [ ] **Step 5：Commit**

```bash
git add slo/run_regression.py tests/test_slo_run_regression.py
git commit -m "feat(slo): wire alert_evaluator into run_regression CLI (phase 3d task 2)"
```

---

## Task 3：observability dashboards schema + README

### Files
- Create: `docs/observability/README.md`
- Create: `docs/observability/dashboards/schema.md`
- Create: `docs/observability/dashboards/export_template.json`

### Steps

- [ ] **Step 1：创建 dashboard schema 文档**

Create `docs/observability/dashboards/schema.md`：

```markdown
# Langfuse Dashboard Schema（Phase 3d）

本文件定义 Phase 3 顶层 spec §9.1 中 4 类面板的字段口径，便于在 Langfuse v4 实例上手动配置 + 导出 JSON 入库。

## 1. 时延面板（latency）

**目的**：监控 SLO 时延三档的 P50/P95/P99 时序，红线为阈值。

**Trace 字段依赖**：
- `metadata.session_id` 用作 group-by
- span name `learning_session` 的 duration 作为完成时延
- span name 包含 `token` 的最早 timestamp 作为首 token 时延（异步链路下）

**面板布局**：
- 三个时序图，分别对应 accept_latency / first_token_latency / completion_latency
- 每个图叠加水平红线 = 当前 thresholds.yaml 中对应 P95 阈值

## 2. 稳定面板（stability）

**目的**：成功率、重试恢复率、错误码分布。

**Trace 字段依赖**：
- span level（ERROR vs DEFAULT）作为 success 派生
- span metadata 中的 retry attempt 数（v1 由 retry_policy span 自带）
- span input/output 中的 error 字段，按 `app/services/error_classifier.py` 分类

**面板布局**：
- 折线图：成功率 / 重试恢复率
- 堆叠柱状图：按错误码分类

## 3. 质量面板（quality）

**目的**：引用覆盖率、低证据声明率，按 query_mode 切片。

**Trace 字段依赖**：
- root span output 的 `citations` 字段长度
- root span output 的 `rag_low_evidence` 布尔
- root span metadata 的 `query_mode`（query_planner 节点写入）

**面板布局**：
- 折线图：citation_coverage（按 query_mode 着色）
- 折线图：low_evidence_disclaim_rate

## 4. 链路面板（pipeline）

**目的**：节点级 span 耗时占比，定位慢节点。

**Trace 字段依赖**：
- 所有 `@node` 装饰器产生的 span（NodeRegistry._wrap_with_span）
- span name 即 node name

**面板布局**：
- 堆叠面积图：各节点耗时占总耗时的比例
- Top-N 表：最近 24 小时最慢的 10 次 trace（按 completion_latency 排序）

---

## 导入步骤

1. 在 Langfuse 实例上根据本文件手动配置 4 个 dashboard
2. 使用 Langfuse "Export dashboard" 功能导出为 JSON
3. 把 JSON 命名为 `01_latency.json` / `02_stability.json` / `03_quality.json` / `04_pipeline.json` 放入本目录
4. 在 PR 中说明 Langfuse 实例版本（dashboard JSON 是版本绑定的）

> v1 注：本目录暂仅含 schema 与 export_template.json 占位。实际 4 份 dashboard JSON 由首次 Langfuse 部署的运维者补提。
```

- [ ] **Step 2：创建导出模板占位**

Create `docs/observability/dashboards/export_template.json`：

```json
{
  "_comment": "Langfuse v4 dashboard 导出格式占位。实际内容由 Langfuse Export 生成。",
  "_required_fields_per_panel": [
    "name",
    "type",
    "metric",
    "groupBy",
    "filter",
    "timeWindow"
  ],
  "_v1_status": "未实际生成；schema.md 列出了 4 类面板的字段依赖"
}
```

- [ ] **Step 3：创建 observability README**

Create `docs/observability/README.md`：

```markdown
# Observability（可观测性入口）

本目录是 Phase 3d 的可观测运营化资产入口。

## 内容

| 路径 | 说明 |
|---|---|
| `dashboards/schema.md` | 4 类 Langfuse dashboard 的字段定义 |
| `dashboards/export_template.json` | 导出格式占位 |
| `dashboards/01_latency.json` 等 | 实际 dashboard 导出（首次部署后补） |

## 与 SLO 的关系

| 资产 | 入口 | 用途 |
|---|---|---|
| 阈值 | `slo/thresholds.yaml` | 6 个 SLI 的 v1 基线 |
| 回归集 | `slo/regression_set.yaml` | 12 题，4 类 |
| 门禁脚本 | `slo/run_regression.py` | `uv run python -m slo.run_regression` |
| 告警规则 | `slo/alert_rules.yaml` | INFO/WARN/CRIT 三级 |
| 看板 | `docs/observability/dashboards/` | trace 可视化 |
| Runbook | `docs/runbook/` | 启停 / 回滚 / 容量 / 故障 / 发布 |

## 触发链路

```
trace（Langfuse）
   ↓ 解析（v1 由 SLO runner 直读 result state，不查 langfuse server）
SLI（aggregator.py）
   ↓ 比对
breach（checker.py）
   ↓ 评估
alert（alert_evaluator.py）
   ↓ 写日志 / 触发 runbook
on-call（docs/runbook/oncall_response.md）
```

> 单人本地形态下 trace 入 Langfuse 是可观测能力的"未来钩子位"，v1 SLO 检查不依赖 Langfuse 可达。
```

- [ ] **Step 4：Commit**

```bash
git add docs/observability/
git commit -m "docs(observability): add dashboard schema + README entry (phase 3d task 3)"
```

---

## Task 4：Runbook 6 份核心文档

每份 markdown 至少 2 个具体场景，明示命令。

### Files
- Create: `docs/runbook/00_index.md`
- Create: `docs/runbook/01_startup_shutdown.md`
- Create: `docs/runbook/02_rollback.md`
- Create: `docs/runbook/03_capacity.md`
- Create: `docs/runbook/04_troubleshooting.md`
- Create: `docs/runbook/05_release_checklist.md`

### Steps

- [ ] **Step 1：创建 00_index.md**

Create `docs/runbook/00_index.md`:

```markdown
# Runbook 索引

Phase 3d 沉淀的运维手册。当系统出问题或要发布时，按本索引找对应文档。

## 决策树

```
问题发生？
├─ 系统起不来 / 要停服 → 01_startup_shutdown.md
├─ 上线后回退 → 02_rollback.md
├─ 慢 / 卡 / 资源不够 → 03_capacity.md
├─ 报错 / 异常 → 04_troubleshooting.md
└─ 准备发布 → 05_release_checklist.md

需要值班响应？→ oncall_response.md
```

## 各文档摘要

| 文档 | 主题 | 场景数 |
|---|---|---|
| `01_startup_shutdown.md` | 启停顺序与命令 | 2（本地 / 单机 Docker） |
| `02_rollback.md` | feature flag + 进程重启回退 | 2（async flag / 代码 revert） |
| `03_capacity.md` | worker 并发 / 队列 / Redis 容量 | 2（CPU 满载 / Redis OOM） |
| `04_troubleshooting.md` | 5 类典型故障 | 5 |
| `05_release_checklist.md` | 发布前检查清单 | 4 步检查 |
| `oncall_response.md` | on-call 响应 | 3（看板红 / 门禁失败 / async 异常） |

## 配套资产

- SLO 门禁：`slo/run_regression.py`
- 告警规则：`slo/alert_rules.yaml`
- 告警日志：`logs/slo_alerts.log`（运行 SLO check 后产生）
- 看板入口：`docs/observability/README.md`
```

- [ ] **Step 2：创建 01_startup_shutdown.md**

Create `docs/runbook/01_startup_shutdown.md`:

```markdown
# 启停顺序

## 场景 1：本地开发（默认同步路径）

启动顺序：

```bash
# 1. 拉取依赖
uv sync

# 2. 启动 uvicorn（同步路径，不需要 Redis/Celery）
PYTHONPATH=. uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 1900
```

停止：`Ctrl+C` 即可。

## 场景 2：本地异步路径（验证 Phase 3a/3b）

启动顺序（必须按序）：

```bash
# 1. 启动 Redis（Docker 推荐）
docker run -d --name study-agent-redis -p 6379:6379 redis:7-alpine

# 2. 验证 Redis 可达
docker exec study-agent-redis redis-cli ping  # 期望 PONG

# 3. 启动 Celery worker（新终端）
PYTHONPATH=. ASYNC_GRAPH_ENABLED=true \
  uv run celery -A app.worker.celery_app worker --loglevel=info

# 4. 启动 uvicorn（再新终端）
PYTHONPATH=. ASYNC_GRAPH_ENABLED=true \
  uv run uvicorn app.main:app --host 127.0.0.1 --port 1900

# 5. 验证（新终端）
curl -N -X POST http://127.0.0.1:1900/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"session_id": "smoke-1", "topic": "math", "user_input": "什么是导数"}'
# 期望看到 event: accepted → event: token (多条) → event: stage → event: done
```

停止顺序（与启动相反）：

```bash
# 1. 停 uvicorn（Ctrl+C）
# 2. 停 Celery worker（Ctrl+C，等任务结束 ~5s）
# 3. 停 Redis
docker stop study-agent-redis && docker rm study-agent-redis
```
```

- [ ] **Step 3：创建 02_rollback.md**

Create `docs/runbook/02_rollback.md`:

```markdown
# 回滚

## 场景 1：异步链路异常 → 关 flag 回退到同步

**触发**：Celery worker 卡住、Redis 失联、SSE token 中断。

**步骤**：

```bash
# 1. 把 ASYNC_GRAPH_ENABLED 设为 false（环境变量或 .env）
export ASYNC_GRAPH_ENABLED=false

# 2. 重启 uvicorn（Celery / Redis 不需要）
# 在 uvicorn 终端 Ctrl+C 后重启：
PYTHONPATH=. uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 1900

# 3. 验证同步路径（不会有 accepted 事件）
curl -N -X POST http://127.0.0.1:1900/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"session_id": "rollback-test", "topic": "math", "user_input": "test"}'
# 期望：event: token → event: stage → event: done（无 accepted）
```

回退后 `tests/test_chat_sync_fallback.py` 覆盖的同步路径完全可用。

## 场景 2：代码回滚到上一个 commit

**触发**：刚刚的 commit 造成回归（SLO 门禁失败 / 测试退化）。

**步骤**：

```bash
# 1. 看最近 commit
git log --oneline -5

# 2. 创建撤销 commit（推荐，不破坏历史）
git revert HEAD

# 3. 跑全量回归 + SLO 门禁验证回滚生效
PYTHONPATH=. DEBUG=false uv run pytest tests/ -q
uv run python -m slo.run_regression
```

> 不推荐 `git reset --hard`：会丢失 commit 历史，多人协作时几乎一定出事。
```

- [ ] **Step 4：创建 03_capacity.md**

Create `docs/runbook/03_capacity.md`:

```markdown
# 容量治理

## 场景 1：CPU 满载（uvicorn 或 worker）

**症状**：响应慢、SLO completion_latency P95 > 15s。

**诊断**：

```bash
# Windows: 任务管理器
# Linux/macOS:
top -p $(pgrep -f uvicorn)
top -p $(pgrep -f celery)
```

**调优**（无 worker 主线 → 调 uvicorn）：

```bash
# 增加 uvicorn worker 数（默认 1，CPU 核心数 N → 设 N）
PYTHONPATH=. uv run uvicorn app.main:app --workers 4 --host 127.0.0.1 --port 1900
```

**调优**（有 worker → 调 Celery 并发）：

```bash
# Celery worker --concurrency 默认 = CPU 核心数；想限制：
uv run celery -A app.worker.celery_app worker --concurrency=2 --loglevel=info
```

## 场景 2：Redis OOM 或队列积压

**症状**：worker 任务等待时间长、Redis `INFO memory` 接近 maxmemory。

**诊断**：

```bash
# 看 Redis 内存
docker exec study-agent-redis redis-cli INFO memory | grep used_memory_human

# 看 Celery 队列长度
docker exec study-agent-redis redis-cli LLEN celery
```

**应对**：

```bash
# 1. 临时清队列（**会丢任务**，仅在确认积压无意义时用）
docker exec study-agent-redis redis-cli DEL celery

# 2. 限制 Redis 内存上限 + 淘汰策略
docker run -d --name study-agent-redis -p 6379:6379 redis:7-alpine \
  redis-server --maxmemory 256mb --maxmemory-policy allkeys-lru

# 3. 临时切回同步路径降压（见 02_rollback.md 场景 1）
```

## 队列优先级（暂不启用）

Phase 3d 不启用 Celery routing。未来如分"在线对话 / 离线分析"队列，参考：
- 在 `app/worker/celery_app.py` `task_routes` 配置
- 启动 worker 时 `-Q chat,offline` 指定监听队列
```

- [ ] **Step 5：创建 04_troubleshooting.md**

Create `docs/runbook/04_troubleshooting.md`:

```markdown
# 故障排查（5 类典型）

## 1. Worker 卡住（任务长时间不完成）

**症状**：`/chat/stream` 收到 `accepted` 后无 token / done 事件。

**排查**：

```bash
# 1. 看 worker 日志最近一条任务
# 在 Celery worker 终端检查输出，是否卡在某个节点

# 2. 看任务状态（如果 Celery 启用了 result backend）
uv run python -c "
from app.worker.celery_app import celery_app
i = celery_app.control.inspect()
print('active:', i.active())
print('reserved:', i.reserved())
"

# 3. 强制结束 worker（任务会被 Celery 标记为 failed）
# Celery worker 终端 Ctrl+C
```

**修复后**：跑 `uv run python -m slo.run_regression` 验证。

## 2. 队列积压

**症状**：worker active task 数量 ≈ concurrency，reserved 队列持续增长。

**步骤**：见 `03_capacity.md` 场景 2。

## 3. Broker（Redis）失联

**症状**：worker 启动报错 `redis.exceptions.ConnectionError`。

**排查**：

```bash
# 1. Redis 容器是否在跑
docker ps | grep redis

# 2. Redis 是否监听 6379
docker exec study-agent-redis redis-cli ping

# 3. REDIS_URL 是否正确
echo $REDIS_URL  # 期望 redis://localhost:6379/0
```

**应急**：切回同步路径（见 `02_rollback.md` 场景 1）。

## 4. SSE 断流（chat/stream 中途断开）

**症状**：浏览器 / curl 在收到部分 token 后连接关闭。

**排查**：

- 异步路径下 → 检查 `pubsub.subscribe` 超时（`celery_task_timeout_s + 5`）
- 同步路径下 → 检查 `agent_service.run` 是否抛异常（看 uvicorn 日志）
- 反向代理（如 nginx）→ 确认 keepalive、proxy_read_timeout

**临时绕过**：用 `POST /chat`（非流式）替代 `/chat/stream`。

## 5. LLM 限流 / 超时

**症状**：`agent_service.run` 抛 `openai.RateLimitError` 或 `openai.APITimeoutError`。

**应对**：

- 检查 `LLM_TIMEOUT_SECONDS`（默认 30，必要时调到 60）
- 检查 `LLM_MAX_RETRIES`（默认 2）
- Phase 7 的 `RETRY_POLICIES_MAP` 已经按节点配置 retry，限流时通常会自动重试 1-2 次
- 长期：在 `app/services/llm.py` 加 token bucket 限流（不在本 phase 范围）
```

- [ ] **Step 6：创建 05_release_checklist.md**

Create `docs/runbook/05_release_checklist.md`:

```markdown
# 发布检查清单

按顺序执行，任一步失败 → 不允许发布。

## Step 1：全量回归（不退化）

```bash
PYTHONPATH=. DEBUG=false uv run pytest tests/ -q
```

**通过条件**：
- passed >= 上次 release 基线
- failed <= 上次 release 基线（19 是 Phase 7 起的既有失败基线）

## Step 2：SLO 门禁

```bash
uv run python -m slo.run_regression
```

**通过条件**：退出码 0；`Status: PASS`；`Alerts: 0 WARN, 0 CRIT`（INFO 可有）。

## Step 3：阈值差比

如果本次发布修改了 `slo/thresholds.yaml`：

```bash
git diff master -- slo/thresholds.yaml
```

确认：
- 任何放宽（threshold 变松）必须在 PR 描述里**明确解释**
- 任何收紧必须有近 7 天数据支撑（manual review）

## Step 4：变更影响声明

PR 描述里必须含：
- [ ] 修改了哪些已有 API / 配置
- [ ] 是否破坏向后兼容（feature flag 是否覆盖回退路径）
- [ ] 是否新增运行时依赖（pyproject.toml 改了吗）
- [ ] 测试覆盖：新代码是否有单元测试 + 集成测试

## Step 5：合并

只有 1-4 全过才允许 merge。merge 后立即在 origin/master 跑一次 SLO check，确认无意外。
```

- [ ] **Step 7：Commit（本任务一次性 commit 6 份文档）**

```bash
git add docs/runbook/00_index.md docs/runbook/01_startup_shutdown.md \
  docs/runbook/02_rollback.md docs/runbook/03_capacity.md \
  docs/runbook/04_troubleshooting.md docs/runbook/05_release_checklist.md
git commit -m "docs(runbook): add 6 core runbook documents (phase 3d task 4)"
```

---

## Task 5：on-call 响应文档

### Files
- Create: `docs/runbook/oncall_response.md`

### Steps

- [ ] **Step 1：创建 oncall_response.md**

Create `docs/runbook/oncall_response.md`:

```markdown
# On-Call 响应

本文档定义 3 个值班响应场景。单人本地形态下 on-call 即"开发者自己"，但保留响应矩阵以便上云后切到 webhook 通知。

## 场景 1：看板红了（SLI 超阈值）

**告警来源**：Langfuse dashboard 红线 / `logs/slo_alerts.log` WARN 或 CRIT 行。

**响应步骤**：

1. 看 `logs/slo_alerts.log` 最近 10 行，定位红线 SLI 名
2. 跑 `uv run python -m slo.run_regression` 确认 SLI 当前值
3. 按 SLI 类型查 runbook：
   - `*_latency_ms` 超阈值 → `03_capacity.md`
   - `task_success_rate` 跌 → `04_troubleshooting.md`
   - `citation_coverage` / `low_evidence_disclaim_rate` 跌 → 对照 git log 看是否最近改了 RAG 链路
4. 修复后再跑 SLO check 验证恢复

**升级条件**：CRIT alert（task_success_rate < 0.90）连续 2 次出现 → 立即关 ASYNC_GRAPH_ENABLED 切同步路径。

## 场景 2：全量回归门禁失败（PR 阻塞）

**告警来源**：PR pipeline 失败 / `pytest tests/ -q` failed > 19。

**响应步骤**：

1. 对比当前失败列表 vs 既有失败基线（Phase 7 起 19 个固定失败）
2. 如果失败 > 19，找出**新增**的失败：
   ```bash
   PYTHONPATH=. DEBUG=false uv run pytest tests/ -q 2>&1 | grep FAILED > /tmp/now.txt
   git stash && PYTHONPATH=. DEBUG=false uv run pytest tests/ -q 2>&1 | grep FAILED > /tmp/before.txt
   git stash pop
   diff /tmp/before.txt /tmp/now.txt
   ```
3. 按错误码定位：
   - `TypeError: ... got an unexpected keyword argument` → 调用方与被调方签名不匹配（最近改了 service 层 API？）
   - `ModuleNotFoundError` → 漏 commit 文件 / 漏更新 .gitignore 白名单
   - `AssertionError` → 业务逻辑变化导致期望值过期，需双向确认
4. 不允许 merge 前用 `git revert` 撤销引入失败的 commit；或在 PR 中提供修复 commit

## 场景 3：异步链路异常（worker 卡住 / Redis 失联）

**告警来源**：手动观察（用户报告）/ Celery worker 退出。

**响应步骤**（按顺序，能快就快）：

1. **立即降级**：把 `ASYNC_GRAPH_ENABLED` 设为 false，重启 uvicorn（见 `02_rollback.md` 场景 1）
2. **取证**：在切之前抓一份 Celery worker 日志、Redis `INFO`、最近 5 条 `chat:*` pubsub 消息
3. **修复**：参考 `04_troubleshooting.md` 第 1/3 节
4. **回归**：修复后切 `ASYNC_GRAPH_ENABLED=true`，跑：
   ```bash
   uv run pytest tests/test_chat_async_api.py tests/test_worker_tasks_real_graph.py -q
   ```
5. **复盘**：把根因写到本文件下方"已知 incident"段（首次 incident 时新建）

## 升级矩阵（云上预留）

| 严重度 | 当前响应 | 上云后扩展 |
|---|---|---|
| INFO | 仅记日志 | 仍仅记日志 |
| WARN | 看日志手动检查 | 推 Slack `#slo-warn` 频道 |
| CRIT | 立即降级 | 推 Slack `#slo-crit` + 寻呼 on-call |

切换方式：在 `slo/alert_rules.yaml` 启用 `webhook_url` 字段（v1 已注释占位）。
```

- [ ] **Step 2：Commit**

```bash
git add docs/runbook/oncall_response.md
git commit -m "docs(runbook): add on-call response matrix with 3 scenarios (phase 3d task 5)"
```

---

## Task 6：在 README 顶部加运维入口

### Files
- Modify: `plan/README.md`（pyproject readme 入口）OR Create: `README.md`（仓库根）

由于 `pyproject.toml` 引用的是 `plan/README.md`，本计划的"运维入口链接"加到这里以便发布时被打包/可见。

### Steps

- [ ] **Step 1：检查 plan/README.md 是否存在**

Run: `ls plan/README.md`

如果不存在，跳到 Step 3 改用仓库根 README.md。

- [ ] **Step 2（plan/README.md 存在时）：在文件顶部插入运维入口段**

Edit `plan/README.md`，在文件最顶端（标题之后）插入：

```markdown
## 运维入口（Phase 3d）

- [Runbook 索引](../docs/runbook/00_index.md)：启停 / 回滚 / 容量 / 故障 / 发布检查
- [Observability 入口](../docs/observability/README.md)：看板 schema 与 SLO 资产链路
- [On-Call 响应](../docs/runbook/oncall_response.md)：3 个值班场景
- SLO 一键检查：`uv run python -m slo.run_regression`
```

- [ ] **Step 3（plan/README.md 不存在或不便修改时）：在仓库根创建 README.md**

Create `README.md`（仅在 Step 2 不可行时执行）：

```markdown
# StudyAgent

> 用 LangGraph + FastAPI 实现的多轮费曼学习 Agent。

## 快速开始

```bash
uv sync
PYTHONPATH=. uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 1900
```

## 运维入口（Phase 3d）

- [Runbook 索引](docs/runbook/00_index.md)：启停 / 回滚 / 容量 / 故障 / 发布检查
- [Observability 入口](docs/observability/README.md)：看板 schema 与 SLO 资产链路
- [On-Call 响应](docs/runbook/oncall_response.md)：3 个值班场景
- SLO 一键检查：`uv run python -m slo.run_regression`

## Phase 路线

详见 `docs/superpowers/specs/`：
- `004-...framework-evolution-design.md`：12 周顶层蓝图
- `top-007-...phase3-finalization-design.md`：Phase 3 收尾设计
```

- [ ] **Step 4：Commit**

```bash
# 根据 Step 2 / Step 3 选择实际改的文件
git add plan/README.md   # 或 README.md
git commit -m "docs: add runbook + observability entry points (phase 3d task 6)"
```

---

## Task 7：全量回归 + Phase 3 收尾验收

### Files
- 无新增

### Steps

- [ ] **Step 1：跑 Phase 3d 新测试**

Run: `uv run pytest tests/test_slo_alert_evaluator.py tests/test_slo_run_regression.py -v`
Expected: ≥ 15 PASS（9 + 6）。

- [ ] **Step 2：跑 SLO check（含 alert 段落）**

Run（用临时 stub agent，与 Task 5 of plan #017 同款）:

```bash
uv run python -c "
import sys
sys.path.insert(0, '.')
from app.services import agent_service as agent_mod
from slo.run_regression import main

def fake_run(session_id, topic, user_input, user_id=None, stream_output=False, progress_sink=None):
    if progress_sink:
        progress_sink('token', 'stub')
    return {'session_id': session_id, 'stage': 'explained', 'reply': '回答', 'citations': [{'chunk_id': 'c1'}], 'rag_low_evidence': False}

agent_mod.agent_service.run = fake_run
sys.exit(main([]))
"
```

Expected：终端输出含 `Status: PASS` 与 `Alerts: 0 INFO, 0 WARN, 0 CRIT`，退出码 0。

- [ ] **Step 3：跑全量回归**

Run: `PYTHONPATH=. DEBUG=false uv run pytest tests/ -q`
Expected: ≥ `361 passed / 19 failed`（346 + 15 = 361；失败维持 19）。

- [ ] **Step 4：手动检查 runbook 完整度**

Run:

```bash
ls docs/runbook/
wc -l docs/runbook/*.md
ls docs/observability/dashboards/
```

Expected：7 份 runbook（含 oncall_response.md）+ schema.md + export_template.json。

- [ ] **Step 5：合并 commit（可选 squash）**

如果想压缩历史，把 Task 1-6 的 commits 合成一个：

```bash
git log --oneline origin/master..HEAD  # 看本分支的 commit 列表
# 不 squash 直接进入下一步即可
```

---

## 验收清单（Phase 3d 整体）

| 项 | 阈值 / 验证方式 |
|---|---|
| alert_rules.yaml | 含 INFO/WARN/CRIT 三级，云上 webhook 钩子位注释存在 |
| alert_evaluator | 9 个测试覆盖 near / breach / hard_breach / 日志写入 |
| run_regression 集成 | 终端输出含 `Alerts:` 段落；rules 缺失时 graceful skipped |
| Dashboard schema | 4 类面板字段定义齐全；export_template 占位存在 |
| Runbook | 7 份 markdown（6 核心 + 1 on-call），每份场景数 ≥ 2 |
| README 入口 | 顶部含 runbook + observability + SLO 链接 |
| 回归 | ≥ 361 PASS / 19 FAIL（不退化） |
| 不变量 | chat.py / agent_service.py / worker / SLO loader/aggregator/checker 均未修改 |

---

## Self-Review 备注

1. **Spec §11.4 交付清单覆盖**：
   - 4 个 dashboard JSON → **改为 schema.md + export_template.json**（差异已声明） — Task 3 ✓
   - `slo/alert_rules.yaml` → Task 1 ✓
   - `app/monitoring/alert_evaluator.py` → **改路径为 `slo/alert_evaluator.py`**（与 SLO 同包，更内聚） — Task 1 ✓
   - 6 份 runbook → Task 4 ✓
   - `oncall_response.md` → Task 5 ✓
   - `tests/test_alert_evaluator.py` → **路径 `tests/test_slo_alert_evaluator.py`**（前缀对齐 SLO 测试族） — Task 1 ✓
   - README 入口 → Task 6 ✓

2. **路径差异**（vs spec）：alert_evaluator 从 `app/monitoring/` 移到 `slo/`。理由：
   - 它是 SLO 数据消费者，不是 trace 数据生产者
   - 与 loader/aggregator/checker 同包便于查找
   - `app/monitoring/` 保持纯 trace 职责（Langfuse 客户端 + desensitize）

3. **WARN 触发条件差异**：从 spec 的"连续 5 分钟超阈值"改为"任一 breach 即触发"。云上扩展时新增 rule type `time_window_breach` 即可，本计划不引入。

4. **类型一致性**：
   - `Alert.severity` 全程 `Literal["INFO","WARN","CRIT"]` 字符串
   - `evaluate(...)` 返回 `list[Alert]`（与 `aggregate` / `check` 一致用 list 而非 generator）
   - `load_alert_rules` 返回 `dict`（不强类型，便于 yaml 直接落）

5. **Placeholders**：本计划无 TBD/TODO；dashboard 4 份 JSON 的"占位"是显式声明的差异（schema.md 替代），不是计划级 placeholder。

6. **回归测试影响**：本计划仅新增 `slo/alert_*`、`docs/runbook/`、`docs/observability/` 与 README 段落；不改任何既有源码。失败基线 19 不会被本计划扰动。
