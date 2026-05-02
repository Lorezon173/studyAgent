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
