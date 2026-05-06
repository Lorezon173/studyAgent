# SLO v2 阈值校准设计

- 日期：2026-05-04
- 适用阶段：Phase 3 收尾后的"指标真实化"小步迭代
- 上游基准：`docs/superpowers/specs/top-007-2026-05-01-phase3-finalization-design.md` §8（SLO 体系）
- 触发：README §9 第 4 项（SLO v1 基线目前通过 stub agent 校准；首次接真实 LLM 后应重调阈值）
- 类型：指标校准 + 工具脚本

---

## 1. 背景与目标

### 1.1 背景

Phase 3c 落地的 `slo/thresholds.yaml` 是"plan 写作时基于直觉给的合理值"。当前 SLO check 的 stub agent 测试场景下：

- `accept_latency_ms` p95 = 0
- `first_token_latency_ms` p95 = 0
- `completion_latency_ms` p95 = 0

退出码恒为 0。**门禁失去意义**。

### 1.2 目标

把 `slo/thresholds.yaml` 升级到 v2：基于真实 LLM 多轮回归数据 + 20% margin 推算，让 SLO check 真实反映系统状态。

### 1.3 非目标

1. 不改 SLI 定义（仍是 6 个）
2. 不改聚合规则（aggregator / checker 不动）
3. 不引入新依赖
4. 不接 Langfuse server 查询（仍用 result state + 本地计时器）
5. 不引入新 SLI（retry_recovery_rate 由 README §9 第 3 项独立处理）
6. 不改回归集 12 题的内容

---

## 2. 选型结论

### 2.1 候选方案

| 方案 | 描述 | 是否选用 |
|---|---|---|
| A | 单独脚本 `slo/calibrate.py` 跑 N 轮 → 输出报表 → 人工审阈值 → 改 yaml | **选用** |
| B | `run_regression.py` 加 `--calibrate` 标志，校准模式打开后自动改 yaml | 否 |
| C | 写一次性 notebook / 临时脚本，跑完即弃 | 否 |

### 2.2 选 A 的理由

1. **职责清晰**：`run_regression` 是门禁工具，`calibrate` 是数据采集工具，不混用
2. **可重复**：未来 LLM 提供商换 / 模型升级时，重跑 calibrate 即可
3. **审阈值人工**：阈值变更必须 PR review，不能让脚本静默改 yaml
4. **报表归档**：`reports/` 目录已存在且被 .gitignore，校准报表可落 `reports/slo-calibration-vN.json` 仅供本地参考

---

## 3. 工具设计：`slo/calibrate.py`

### 3.1 入口

```bash
uv run python -m slo.calibrate --rounds 5 --output reports/slo-calibration-v2.json
```

### 3.2 参数

| 参数 | 默认 | 说明 |
|---|---|---|
| `--rounds N` | 5 | 跑 N 轮完整 12 题回归集（共 12N 个数据点） |
| `--output PATH` | `reports/slo-calibration-{ts}.json` | 报表落盘路径（自动加时间戳避免覆盖） |
| `--margin FLOAT` | 0.20 | v2 阈值 = max(p95 × (1 + margin), v1) |
| `--dry-run` | False | 仅打印，不写报表 |

### 3.3 流程

```
1. load_thresholds(slo/thresholds.yaml) → v1 阈值
2. load_regression_set(slo/regression_set.yaml) → 12 题
3. for round in 1..N:
     for item in items:
         record = _run_one(item)   # 复用 run_regression._run_one
         records.append(record)
4. for sli_name in 6 个 SLI:
     samples = [对应字段 for record in records]
     p50, p95, p99 = percentiles(samples)
     v1 = 当前 v1 阈值
     v2_recommended = max(p95 * (1 + margin), v1)  # le 方向
                    = min(p95 / (1 + margin), v1)  # ge 方向（取严即取小，但为不收紧 → 取 v1 与放宽值的较松者）
5. write report json
6. print summary table
```

### 3.4 ge 方向（task_success_rate / citation_coverage / low_evidence_disclaim_rate）的 v2 推算

ge 指标"越大越好"。margin 在这里的作用是允许 v2 比实测略低，避免抖动导致门禁误报：

```
v2_recommended_ge = min(p95_actual * (1 - margin), v1_threshold)
```

但**绝不允许低于 v1**——否则就是放水。所以最终：

```
v2_ge = max(p95_actual * (1 - margin), v1_ge)
```

（如果 p95_actual × 0.8 仍 ≥ v1，说明指标真的非常稳，可以适度收紧；否则维持 v1）

### 3.5 le 方向（三档时延）的 v2 推算

le 指标"越小越好"。margin 给抖动空间：

```
v2_le = max(p95_actual * (1 + margin), v1_le)
```

不允许低于 v1（不收紧实测做不到的）；高于 v1 则放宽到 p95 × 1.2。

---

## 4. 报表结构

`reports/slo-calibration-v2-2026-05-04T123456.json`：

```json
{
  "version": "v2-recommended",
  "generated_at": "2026-05-04T12:34:56",
  "rounds": 5,
  "items_per_round": 12,
  "data_points": 60,
  "llm_provider": "<from settings.openai_base_url 或 'default'>",
  "llm_model": "<from settings.openai_model>",
  "margin": 0.20,
  "per_sli": {
    "accept_latency_ms": {
      "v1_threshold": 500,
      "direction": "<=",
      "samples": [0.0, 0.0, ...],
      "p50": 0.0,
      "p95": 0.0,
      "p99": 0.0,
      "v2_recommended": 500
    },
    "first_token_latency_ms": {
      "v1_threshold": 3000,
      "direction": "<=",
      "samples": [...],
      "p50": ...,
      "p95": ...,
      "p99": ...,
      "v2_recommended": ...
    },
    ...（共 6 个 SLI）
  },
  "summary_text": "…可读摘要…"
}
```

报表 **仅供本地参考**，不入库（`reports/` 在 .gitignore 中）。

---

## 5. v2 yaml 写入流程（人工驱动）

校准跑完后，人工：

1. `cat reports/slo-calibration-v2-*.json` 看推荐值
2. 决策每个 SLI：保留 v1 还是采纳推荐 v2
3. 改 `slo/thresholds.yaml`
4. 跑一次 `uv run python -m slo.run_regression` 用真实 LLM 验收
5. 提 PR 描述里**逐条说明**：
   - 5 轮数据来源（模型、API、轮次）
   - 每个 SLI 的 v1 → v2 变化
   - 不变的 SLI 也要写理由（"P95 远低于 v1，无需放宽"）

**禁止**：脚本自动覆盖 thresholds.yaml。yaml 是"质量承诺"，承诺变更必须经过 PR review。

---

## 6. 风险与应对

| 风险 | 应对 |
|---|---|
| 5 轮 60 题真实 LLM 调用产生 API 费用 | 用便宜模型（gpt-4o-mini / kimi-8k）；预估 < $0.5 |
| 网络抖动单次极慢污染 p95 | 报表里保留 p50/p95/p99 三档；20% margin 吸收 |
| 真实 LLM 偶发失败导致 task_success_rate 跌破 0.97 | 5 轮 60 题允许 1-2 个失败（成功率仍 ≥ 0.967，接近阈值；如果实测 < 0.97 就**降阈值到 0.95**而非放任） |
| 校准过程中 OpenAI key 限流 | calibrate 的 `_run_one` 已 catch Exception 转 success=False；样本不丢失 |
| 数据不够代表性（12 题 × 5 轮太少） | 报表里显式标注 sample_size；如果用户觉得不够，再加 `--rounds 10` 重跑即可 |

---

## 7. 测试策略

### 7.1 单元测试

- `tests/test_slo_calibrate.py`：
    - mock `_run_one` 返回固定 RunRecord 列表（无真实 LLM）
    - 验证：报表 json 结构正确（`per_sli` 6 项）
    - 验证：v2 推算公式（le / ge 方向各 1 个）
    - 验证：`--dry-run` 不写文件
    - 验证：N=0 / N=1 / N=5 各跑一次（`--rounds` 边界）

### 7.2 集成测试（手动）

- 配 `.env` 真实 key
- `uv run python -m slo.calibrate --rounds 5`
- 检查 reports/ 下输出报表
- 把推荐阈值写入 thresholds.yaml
- `uv run python -m slo.run_regression` 验证退出码 0

### 7.3 回归

不改任何已有源码，回归基线 357/19 维持。

---

## 8. 文件清单

| 文件 | 类型 | 责任 |
|---|---|---|
| `slo/calibrate.py` | 新增 | calibrate CLI 入口 + percentile 计算 + 报表生成 |
| `tests/test_slo_calibrate.py` | 新增 | 单元测试 |
| `slo/thresholds.yaml` | 修改（手动）| 写入 v2 阈值（PR 时与脚本同 PR 或独立 PR 视情况）|
| `reports/slo-calibration-*.json` | 新增（落盘）| 报表（不入库）|
| `.gitignore` | 修改（白名单）| `!tests/test_slo_calibrate.py` |

---

## 9. 子阶段拆分

只有 1 个子阶段：

### 9.1 单一阶段：calibrate 脚本 + v2 阈值

- 实现 `slo/calibrate.py`（约 100 行）
- 实现 `tests/test_slo_calibrate.py`（约 80 行）
- 配 .env + 跑 5 轮真实回归
- 根据报表手动写 thresholds.yaml v2
- 验证：真实 LLM 下 SLO check 退出码 0
- PR 描述附数据表

预算：**约 2-3 小时**（含 LLM 真实调用 15-20 分钟）。

---

## 10. 验收标准

| 项 | 阈值 / 形态 |
|---|---|
| calibrate 工具 | `uv run python -m slo.calibrate --rounds N` 可跑通 |
| 测试 | 单元测试 ≥ 5 个，全绿 |
| 报表 | reports/ 下生成完整 json，per_sli 含 6 项 |
| v2 阈值 | thresholds.yaml 至少 1 个 SLI 阈值变化（如果完全没变说明 v1 已经合理）|
| 真实回归 | `uv run python -m slo.run_regression` 真实 LLM 下退出码 0 |
| 不退化 | 全量 `pytest` 357 PASS / 19 FAIL 维持 |
| PR 文档 | PR 描述含数据表 + 每个 SLI 的 v1→v2 变化说明 |

---

## 11. 与 spec top-007 §8 的差异声明

top-007 §8.2 v1 阈值：

```
accept_latency_ms          ≤ 500
first_token_latency_ms     ≤ 3000
completion_latency_ms      ≤ 15000
task_success_rate          ≥ 0.97
citation_coverage          ≥ 0.85
low_evidence_disclaim_rate ≥ 0.95
```

本 spec 的"v2 推算"不预先承诺最终值——v2 是数据驱动的。但**预期**：

- `accept_latency_ms`：同步路径下恒为 0，**应在 v2 里改为 N/A 或保持 v1**（直到 ASYNC_GRAPH_ENABLED=true 才有意义）
- `first_token_latency_ms` / `completion_latency_ms`：实测值依赖模型与网络；可能放宽到 5000-30000ms 区间
- `task_success_rate`：实测大概率 0.95-1.00；可能微调
- `citation_coverage` / `low_evidence_disclaim_rate`：实测依赖 RAG 链路；预期保持

如果实测让某个阈值大幅放宽（> 2x），需要在 PR 里**显式声明**并解释为何 v1 不切实际。

---

## 12. 后续

本 spec 完成后：

- README §9 第 4 项可标记 ✅
- README §9 第 3 项（retry_recovery_rate）启动新一轮 brainstorming
- README §9 第 2 项（dashboard JSON）等真实 trace 攒够 7 天后启动
