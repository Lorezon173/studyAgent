# RAG 架构评估报告（studyAgent）

## 1. 评估结论摘要

当前项目 RAG 已具备可用的工程化雏形：双轨检索（global/personal）、混合召回（BM25+dense）、RRF 融合、rerank、citations 回传、工具路由联动均已落地。  
核心短板在于底座仍是 JSONL + 内存缓存 + 全量扫描，随着数据规模与并发增长，会在稳定性、性能一致性、可观测性和可维护性上遇到明显瓶颈。

---

## 2. RAG 相关服务与模块全景

### 2.1 接入层

- `app/api/knowledge.py`：知识入库、检索、文件入库（含 source_type/scope/user_id/topic）。
- `app/api/chat.py`：聊天响应中返回 `citations`。
- `app/ui/chainlit_backend.py` + `app/ui/chainlit_app.py`：前端支持 `/kadd`、`/ksearch`。

### 2.2 核心检索层

- `app/services/rag_service.py`：统一门面，封装 ingest/retrieve/retrieve_scoped。
- `app/services/retriever.py`：`Retriever` 协议与默认 `JsonlRagRetriever` 实现。
- `app/services/rag_store.py`：切分、向量化、BM25、dense、RRF、rerank、持久化。
- `app/services/embedding_service.py`：`simple` / `sentence_transformers` embedding。
- `app/services/rerank_service.py`：`simple` / `bge` reranker。
- `app/services/personal_rag_store.py`：个人记忆与 personal chunk 检索融合。

### 2.3 编排与决策层

- `app/services/agent_service.py`：会话主编排；组织 topic context / long-term memory / rag context。
- `app/services/orchestration/context_builder.py`：构造 RAG 证据与 citations。
- `app/services/rag_coordinator.py`：RAG 调度入口（是否调用 + 执行元信息）。
- `app/services/tool_executor.py`：执行 `search_local_textbook` / `search_personal_memory` / `search_web`。
- `app/services/agent_runtime.py`：意图路由和工具路由规则。
- `app/agent/graph_v2.py` + `app/agent/nodes.py`：LangGraph 路径中的 RAG 节点。

---

## 3. 功能实现逻辑（无代码）

### 3.1 入库流程

1. API 接收文本或文件。  
2. 文件型请求先抽取文本（txt/docx/pdf）或执行 OCR。  
3. 文本进入切分器，按 chunk 生成向量。  
4. 每个 chunk 进入内存缓存并追加写入 JSONL。  
5. 返回插入条数与元信息。

### 3.2 检索流程

1. 查询词做 token 化与 query embedding。  
2. 候选集由内存与 JSONL 数据组成，再按 scope/topic/user_id 过滤。  
3. 对候选分别计算 BM25 与 dense 相似度。  
4. 用 RRF 融合排序。  
5. 取候选做 rerank，生成最终 score。  
6. 输出 `items`（含 score、bm25/vector/rrf/rerank 等细分字段）。

### 3.3 Chat 注入流程

1. Agent 层做 intent/topic/tool route。  
2. ContextBuilder 调 rag_coordinator + tool_executor 获取证据。  
3. 命中后拼装 `topic_context` 与 `citations`。  
4. 若工具检索为空，主链路有 legacy fallback 检索补偿。

### 3.4 Personal 轨道融合

`search_personal_memory` 调统一函数，融合 personal chunk 检索结果与 personal_rag 历史条目，去重后按分数输出。

---

## 4. 现有优势

1. 分层清晰：API、服务、检索器、路由、编排边界明确。  
2. 可替换性好：已有 `Retriever` 抽象，便于平滑迁移底座。  
3. 检索链路完整：混合召回 + 融合 + 重排 + 引用字段完善。  
4. 双轨隔离明确：global/personal 在入库与检索均有约束。  
5. 测试覆盖较好：知识 API、工具执行、检索器注入、chat citations 等已有用例。

---

## 5. 主要隐患与风险

### 5.1 重复候选导致评分偏斜

检索候选来源为“内存+磁盘”合并，若同一 chunk 重复出现，可能被重复打分，影响排序可靠性。

### 5.2 `simple` embedding 的一致性风险

基于 Python 内置 hash 的向量映射跨进程可能变化，历史向量与新查询向量空间不稳定，影响可重复性。

### 5.3 V2 路径字段映射不一致

图节点中部分路径按 `content/source` 取值，而核心检索输出主字段为 `text/source_type`，开启 V2 时有潜在上下文丢失风险。

### 5.4 决策分散

intent、是否检索、工具选择存在多点决策，当前缺少统一 DecisionContract 落地，长期易行为漂移。

### 5.5 personal 融合评分量纲不一致

检索相关性分与历史记忆分直接混排，可能导致排序偏差。

### 5.6 JSONL 底座扩展性有限

全量扫描读、追加写模型在高并发与大规模场景下性能和恢复能力不足，坏行处理可观测性弱。

---

## 6. 效果提升建议

### P0（优先）

1. 检索候选按 `chunk_id` 严格去重后再打分。  
2. 对齐 Graph V2 与检索输出字段语义。  
3. personal 融合阶段做分值归一化与来源权重控制。  
4. 加强 JSONL 读写一致性与坏行告警。  
5. 将“是否检索/执行哪些工具”收敛为单一决策合同。

### P1（进阶）

1. 默认 embedding/rerank 切强模型并保持维度一致。  
2. 建立离线检索评测集（Recall@k/MRR/nDCG）。  
3. 逐步迁到更成熟的索引与检索底座（向量库/混合索引）。

---

## 7. 替代框架评估（LlamaIndex）

LlamaIndex 可显著增强索引与检索工程化能力，尤其适合当前项目“保留业务编排、升级检索底座”的目标：

1. 统一 ingestion/index/retrieval 抽象，减少自研管线维护成本。  
2. 多数据源、多后端适配更成熟。  
3. 检索策略迭代（融合、后处理、路由检索）效率更高。  
4. 更便于建立可复现评测与 A/B 比较链路。

不替代的部分：业务意图、学习流程策略、用户隔离规则仍需项目侧继续主导。

---

## 8. 综合判断

当前架构适合中小规模与快速迭代；若目标是“持续提升返回效果并可规模化”，建议采用渐进式迁移：  
先替换 `Retriever` 实现，再逐步替换索引与存储层，最终形成“业务编排不动、检索底座升级”的可控演进路径。

