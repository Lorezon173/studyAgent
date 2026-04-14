# RAG 检测报告（Codex）

## 1. 执行结论（TL;DR）

当前 RAG 架构是可运行的，且具备 **global/personal 双轨、BM25+Dense+RRF+rerank、citations 回传、工具路由接入** 的完整闭环。  
但在“稳定性与可控性”上存在中高风险点：**检索数据源重复加载、排序融合策略偏弱、topic 过滤偏硬、工具路由与检索耦合过强、可观测与限流在生产 CLI 上不足**。

---

## 2. 代码覆盖范围

本报告基于以下核心文件：

- 入库/切分/召回/融合：`app/services/rag_store.py`
- RAG 服务层：`app/services/rag_service.py`
- Retriever 抽象：`app/services/retriever.py`
- 向量化：`app/services/embedding_service.py`
- 重排：`app/services/rerank_service.py`
- 工具执行与路由：`app/services/tool_executor.py`、`app/services/agent_runtime.py`
- 上下文注入：`app/services/orchestration/context_builder.py`
- 主链路调用：`app/services/agent_service.py`
- personal 记忆：`app/services/personal_rag_store.py`
- API 入库：`app/api/knowledge.py`
- 调试脚本：`tests/rag_manual_observer.py`
- 配置：`app/core/config.py`、`.env.example`

---

## 3. 现状分析（按链路）

### 3.1 入库（Ingest）

**现状**
- 支持 `text/image`，scope 支持 `global/personal`，personal 强制 `user_id`。
- 文件入库（txt/docx/pdf/png/jpg/jpeg）走 `knowledge/ingest-file`，PDF 用 `pypdf`，图片走 OCR。
- 每个 chunk 同步写内存列表 + JSONL 文件。

**评价**
- 优点：功能完整、实现清晰、校验严格（source/scope/user_id/content）。
- 风险：内存与磁盘双写但无统一去重键，重复入库后检索候选会膨胀。

---

### 3.2 切分（Chunking）

**现状**
- 字符级窗口切分（`chunk_size`/`chunk_overlap`），默认 500/100。
- 对异常参数有安全修正（overlap >= size 时回退）。

**评价**
- 优点：简单稳定，便于快速落地。
- 风险：纯字符切分对 PDF/中文段落语义边界不友好，易切断关键句。

---

### 3.3 向量化（Embedding）

**现状**
- provider: `simple`（默认 hash-bow）或 `sentence_transformers`（bge-m3）。
- simple 模式可离线运行、成本低。

**评价**
- 优点：在无模型依赖场景可用。
- 风险：`simple` 对语义召回能力有限，尤其跨表达/长句检索时会弱于语义模型。

---

### 3.4 召回（Retrieve）

**现状**
- token 化后同时算 lexical overlap + BM25 + dense cosine。
- BM25 与 dense 分别排序后做 RRF 融合，再 rerank。
- scope 过滤：
  - global 只看 global
  - personal 要求 user_id 严格匹配
- topic 过滤：`topic in {None, "", topic}`。

**评价**
- 优点：标准混合检索链路齐全；personal 隔离逻辑正确。
- 风险：
1. 候选集合来自 `_MEMORY_KNOWLEDGE_CHUNKS + _load_disk_chunks()`，同一进程内可能重复（内存已有 + 磁盘再读）。
2. topic 过滤较硬，用户 query 正确但 topic 漂移时容易 0 命中。
3. rerank 前候选上限依赖 `rag_rerank_top_n`，对复杂查询可能过早截断。

---

### 3.5 重排（Rerank）

**现状**
- provider: `simple`（token overlap）或 `bge`（cross-encoder）。
- 最终分数：`0.8 * rrf + 0.2 * normalized_rerank`。

**评价**
- 优点：融合逻辑清晰、可替换 provider。
- 风险：当 rerank provider= simple 时，和 BM25/token 重叠性高度同源，增益有限。

---

### 3.6 调用与注入（Agent Runtime）

**现状**
- `ContextBuilder.build_rag_context()` 通过工具链路触发检索，生成 `context + citations`。
- `AgentService._build_rag_context()` 在工具无结果时回退旧 `rag_service` 直查。
- tool_route 会在用户有 user_id 时倾向 personal，并在 `execute_retrieval_tools()` 中补跑另一轨道。

**评价**
- 优点：具备回退，避免单一路径失效；citations 字段完整。
- 风险：
1. 工具路由与 RAG 耦合较深，route 偏差会直接影响检索轨道。
2. `qa_direct` 等分支下 stage 与检索预期可能错位，易产生“RAG未触发”的体感问题。
3. 某些轮次不触发工具时，`tool_calls` 为空是正常行为，但容易被误判为失败。

---

### 3.7 global / personal 设计评估

**结论：方向正确，隔离逻辑基本合理。**

- `global`：通用知识，user_id 置空。
- `personal`：严格要求 user_id，检索时严格匹配。
- 额外 `personal_rag_store` 用于长期学习记忆（与知识 chunk 并存）。

**主要问题**
- 存在“两套 personal 来源”（chunk 检索 + personal memory）并行，融合策略偏弱，可能出现证据排序不稳定。

---

## 4. 你提到的问题核对

### 4.1 “RAG 默认未开启”

核对结果：问题成立（历史默认 `False`）。  
当前状态：已改为默认开启（`rag_enabled=True`，`.env.example` 同步为 `RAG_ENABLED=true`）。

### 4.2 “CLI 入库后输出过大导致崩溃”

核对结果：问题成立（长文本/PDF提取文本直接回显风险高）。  
当前状态：`tests/rag_manual_observer.py` 已增加输出截断与限流命令（preview/trace/llm）。

---

## 5. 风险清单与级别

### 高风险
1. **候选重复加载导致召回排序噪声**  
   来源：内存列表 + 磁盘全量合并。

2. **RAG触发路径受 tool_route 偏差影响大**  
   当 route 偏到不检索分支，用户体感为“RAG没用”。

### 中风险
3. **topic 过滤过硬导致误杀召回**  
   建议增加 topic 退化策略（strict->relaxed）。

4. **simple embedding + simple rerank 语义能力偏弱**  
   离线可用但质量上限明显。

### 低风险
5. **切分策略过于通用**  
   后续可升级为段落/标题感知切分。

---

## 6. 优先级改进建议（仅 RAG 部分）

### P0（建议立即）
1. 候选去重前移：在 `_load_disk_chunks` 合并时按 `chunk_id` 去重，避免重复候选。
2. 增加“RAG触发判定日志”：记录每轮是否触发检索、使用哪个工具、0命中原因。
3. topic 过滤增加回退：strict 无命中时自动 relaxed 再检索一次。

### P1
4. personal 双源融合显式化：`personal_chunk` 与 `personal_memory` 统一评分融合。
5. 引入最小召回保障：若工具路由为空或结果为空，强制一次 `global+personal` 兜底检索。

### P2
6. 升级切分策略（段落/标题感知 + PDF 页面元信息）。
7. 生产切换更强 embedding/reranker，并保留 simple 作为 fallback。

---

## 7. 建议的 RAG 验收指标

1. `retrieval_trigger_rate`：每轮检索触发率  
2. `non_empty_citation_rate`：有引用轮次占比  
3. `personal_isolation_violation_rate`：必须为 0  
4. `top1_topic_match_rate`：Top1 topic 命中率  
5. `fallback_activation_rate`：工具空结果兜底触发率  

---

## 8. 总结

你的 RAG 设计在“功能闭环”上是合理的，尤其双轨与 citations 结构完整；  
当前主要短板不是“有没有 RAG”，而是“**触发一致性、候选去重、主题过滤回退、双源融合策略**”。  
如果按 P0->P1 顺序收敛，上线稳定性和可解释性会明显提升。
