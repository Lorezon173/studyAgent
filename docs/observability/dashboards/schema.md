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
