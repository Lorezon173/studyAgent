# RAG 实现现状详解（基于当前代码）

本文基于当前代码实现梳理，不包含 MCP 方案讨论，聚焦你项目里已经落地的 RAG 能力、链路、算法、边界与已知问题。

---

## 1. 总体结论（先看这个）

当前 RAG 已从“单一路径文本检索”演进到“**双轨隔离 + 混合检索 + 工具化执行**”阶段，具备以下能力：

- 支持 `text/image` 入库，图片走 OCR 文本化后统一切块入库。
- 支持 `global/personal` 双轨知识，`personal` 强制 `user_id`。
- 检索核心算法为：**BM25 + Dense + RRF + rerank**。
- Chat 侧已接入 RAG 引用（citations）并回传多维打分字段。
- 检索入口已工具化（`search_local_textbook / search_personal_memory / search_web`），并由 `tool_route` 选择执行。
- 为兼容历史行为，Agent 里保留了旧 `rag_service` 回退路径（当工具执行无结果时触发）。

---

## 2. 模块结构与职责

### 2.1 API 与契约层

- `app/api/knowledge.py`
  - `POST /knowledge/ingest`
  - `POST /knowledge/retrieve`
  - 参数异常统一返回 `400`。

- `app/rag/schemas.py`
  - 入参：`source_type, scope, user_id, topic, chunk_size, chunk_overlap...`
  - 出参：`score + lexical/bm25/vector/rrf/hybrid/rerank` 等打分字段
  - 支持返回 `scope/user_id`（双轨可解释）

### 2.2 服务层

- `app/services/rag_service.py`
  - 对外统一服务入口：
    - `ingest(...)`
    - `retrieve(...)`
    - `retrieve_scoped(...)`
  - OCR 在这里做预处理（`source_type=image`）。
  - 检索通过可注入 `Retriever` 执行（已解耦）。

- `app/services/retriever.py`
  - `Retriever` 协议（接口抽象）
  - 默认 `JsonlRagRetriever`（调用 `rag_store`）
  - 作用：后续可替换向量底座而不改业务调用层。

- `app/services/rag_store.py`
  - 当前检索与存储核心实现（JSONL + 内存）
  - 包含切块、token 化、BM25、Dense、RRF、rerank、双轨过滤。

### 2.3 工具执行与上下文注入

- `app/skills/builtin.py`
  - `search_local_textbook`（global）
  - `search_personal_memory`（personal）
  - `search_web`（web provider 可插拔，默认 stub）

- `app/services/tool_executor.py`
  - 根据 `tool_route` 调用技能并合并结果
  - 有 `user_id` 时会自动补充另一条轨道，保持召回稳定
  - 对结果按 `score` 排序、按 `chunk_id` 去重、截断 `top_k`

- `app/services/orchestration/context_builder.py`
  - `build_rag_context(...)` 将检索结果拼到 prompt
  - 形成 `[知识检索|tools=...]` 证据段
  - 生成 citations（含 `tool/scope/user_id` 等元数据）

- `app/services/agent_service.py`
  - 主流程中接入 `tool_route`
  - 先走 `ContextBuilder.build_rag_context(...)`
  - 若工具链路无结果，回退旧 `rag_service` 路径（兼容）

---

## 3. 数据流（端到端）

### 3.1 入库链路（knowledge ingest）

1. `POST /knowledge/ingest`
2. `rag_service.ingest(...)`
3. 若 `source_type=image` -> `ocr_extract_text(...)`
4. `rag_store.ingest_knowledge(...)`：
   - 文本规范化 + 切块（chunk + overlap）
   - 计算 embedding
   - 写入内存与 `data/knowledge_chunks.jsonl`

### 3.2 检索链路（knowledge retrieve）

1. `POST /knowledge/retrieve`
2. `rag_service.retrieve_scoped(...)`
3. `retriever.retrieve_scoped(...)`
4. `rag_store.retrieve_knowledge_by_scope(...)`：
   - `scope/user_id/topic` 过滤
   - BM25 与 Dense 双路打分
   - RRF 融合
   - rerank 二次排序
   - 输出 top_k

### 3.3 Chat 注入链路

1. `/chat` 进入 `agent_service.run(...)`
2. `route_tool(...)` 选择工具（local/personal/web）
3. `ContextBuilder.build_rag_context(...)` 执行工具检索并拼装证据
4. 结果写入 `state.topic_context` 与 `state.citations`
5. LLM 回答时带证据上下文，响应中返回 citations

---

## 4. 检索算法细节（当前实现）

### 4.1 Token 化（中文重点）

- 英文：`[0-9a-z]+` 且长度 >=2
- 中文：连续中文片段做 `2-gram + 3-gram`
- 目标：避免“中文整句一个 token”导致召回失败（此前问题已修复）

### 4.2 词法分数

- `lexical_score`：query token 与 chunk token 的 overlap 比例（解释性）
- `bm25_score`：标准 BM25（含 `idf/tf/doc_len/avg_doc_len`）

### 4.3 语义分数

- `vector_score`：query embedding 与 chunk embedding 的 cosine，相似度归一到 `[0,1]`

### 4.4 融合与重排

- 双路候选：BM25 排名 + Dense 排名
- 融合：RRF（`1/(k+rank)`）
  - `rrf_score`
  - `rrf_bm25`
  - `rrf_dense`
- 重排：`rerank_items(...)`
- 最终分数：`score = 0.8 * rrf_score + 0.2 * rerank_norm`
- 兼容字段：`hybrid_score` 当前语义对齐 `rrf_score`

---

## 5. 双轨隔离实现（global/personal）

### 5.1 写入约束

- `scope` 仅允许 `global/personal`
- `scope=personal` 必须提供 `user_id`
- `scope=global` 时会清空 `user_id`

### 5.2 检索约束

- `global`：仅检索全局轨道
- `personal`：仅检索 `scope=personal AND user_id=当前用户`
- `topic` 可选过滤（只匹配同 topic 或空 topic）

### 5.3 Chat 侧效果

- citations 可同时出现 global 与 personal 证据
- 每条 citation 带 `scope/user_id`，便于审计与前端展示

---

## 6. 工具化检索现状（非 MCP）

当前 RAG 已有三类工具入口：

- `search_local_textbook`：本地教材/全局知识轨道
- `search_personal_memory`：用户私域记忆（含 personal rag + personal memory）
- `search_web`：外部检索入口（provider 可插拔）

工具执行器现状：

- 主工具来自 `tool_route`
- 若有 `user_id`，自动补充另一轨检索，避免召回波动
- 输出含 `tool` 标签，已用于 citations 可解释

---

## 7. 配置项现状（关键）

位于 `app/core/config.py`：

- RAG 开关与路径
  - `rag_enabled`
  - `rag_store_path`
- 切块
  - `rag_default_chunk_size`
  - `rag_default_chunk_overlap`
- 检索
  - `rag_retrieve_top_k`
  - `rag_rrf_k`
  - `rag_rrf_rank_window_size`
  - `rag_rerank_top_n`
- OCR/Embedding/Rerank provider
  - `rag_ocr_engine`
  - `rag_embedding_provider`
  - `rag_rerank_provider`
- Web 检索 provider
  - `web_search_provider`（`stub/mock`）

---

## 8. 测试覆盖现状

### 已覆盖

- `tests/test_knowledge_api.py`
  - text ingest + retrieve
  - image ingest(OCR) + retrieve
  - personal 必填 user_id
  - personal 用户隔离
  - 打分字段存在性

- `tests/test_chat_flow.py`
  - chat citations 注入与字段验证
  - 工具路由参与检索（`tools=` 标签）

- `tests/test_tool_executor.py`
  - 主工具与补充工具执行
  - web 路由执行

- `tests/test_tool_skills.py`
  - `search_local_textbook / search_personal_memory / search_web` 行为

### 仍建议补充

- 工具链路无结果 -> Agent 回退旧 rag_service 的显式测试
- 高并发下 JSONL 读写一致性测试
- 检索效果评测（NDCG/MRR）自动化测试

---

## 9. 当前实现的优势与短板

### 优势

- 业务闭环完整：API -> 检索 -> Chat 注入 -> 引用回传
- 算法组合合理：BM25 + Dense + RRF + rerank
- 多用户隔离有硬约束
- 工具化入口已落地，后续扩展成本低

### 短板

- 存储仍是 JSONL + 内存，规模化与并发能力有限
- 工具执行器当前为规则调度，尚非图内原生 ToolNode
- web 检索默认 stub，生产可用性依赖后续 provider 实现
- 缺系统化离线评测集与线上检索质量监控

---

## 10. 建议的下一步（不涉及 MCP）

1. 完善“工具无结果回退”与“权限边界”回归测试。
2. 引入检索评测基线（NDCG@k / MRR）并固化为 CI 指标。
3. 将 JSONL 检索底座替换到专用引擎（保留 Retriever 接口不变）。
4. 收敛 Agent 与 ContextBuilder 中的兼容分支，减少双路径维护成本。

---

## 11. 你可以用来验收的最小清单

- `/knowledge/ingest` 与 `/knowledge/retrieve` 在 text/image/global/personal 全场景可用
- `/chat` 返回 citations，且含 `scope/user_id/tool`
- `search_local_textbook / search_personal_memory / search_web` 均可被技能中心发现
- personal 用户之间检索互不可见

