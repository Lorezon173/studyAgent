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
