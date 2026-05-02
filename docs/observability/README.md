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
