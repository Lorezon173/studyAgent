# RAG 图文统一检索实施方案（面向整本书）

## 1. 目标与范围

本方案目标是在现有 `learning-agent` 中落地可生产演进的 RAG 能力，支持：

- 文字资料检索：PDF / Markdown / TXT / 网页正文
- 图片资料检索：图片先 OCR 转文本，再进入统一检索链路
- 面向“整本书”规模的数据处理、引用回溯与答案可解释

不在本阶段范围内：

- 多模态向量（图像特征向量）端到端检索
- 跨租户复杂权限系统
- 在线增量训练 embedding 模型

---

## 2. 为什么采用“图文统一文本化”策略

你的核心业务是学习辅导，问答最终都要回到“可讲解、可引用、可追问”的文本证据。  
把图片先 OCR 成文本后统一处理，能直接复用同一套：

- 清洗与切块策略
- embedding 与检索链路
- 引用标注（章节/页码/图片ID）
- 评测指标（命中率、可解释性）

相比单独维护“图片检索 + 文字检索”两条链路，统一文本化可大幅降低系统复杂度和运维成本。

---

## 3. 框架选型与原因

## 3.1 RAG 编排框架：LlamaIndex（推荐）

推荐选择：`LlamaIndex`

原因：

- 文档 ingest、分块、索引、检索、重排的组件化程度高，适合快速落地
- 对“文档知识库”场景抽象成熟，数据连接器与元数据处理能力更强
- 更容易做“引用回溯 + 来源展示”
- 后续如果你希望保留 LangGraph 主流程，也能把检索封装为 skill/tool 嵌入现有架构

备选：LangChain。  
不选为主方案的原因：你当前项目已经有 LangGraph 编排，RAG 层用 LlamaIndex 可更快获得稳态检索能力；两者组合成本可控。

解释：
核心结论：不是“技术冲突”，而是“编排边界冲突”。
你文档里把 LlamaIndex 当“RAG编排框架”（第3.1节），而你已有 LangGraph 也在做编排，容易出现“双大脑”。

主要冲突点：

流程控制重复：检索、重排、回答阶段两边都可调度，职责重叠。
状态模型不一致：LangGraph用显式 state；RAG链常是黑箱调用，状态难追踪。
工具路由冲突：LangGraph 决策是否检索；LlamaIndex 又可能内部自动检索。
引用契约不一致：你要求 citations[] 强约束，若链路封装过深会丢字段。
错误与重试语义不同：Graph 节点级重试 vs RAG 内部重试，容易重复或漏补偿。
观测链路割裂：日志、trace、指标分散，难定位召回/生成责任边界。
建议：LangGraph做总编排，RAG仅做“可调用技能”（文档第44行思路是对的）。定义稳定 I/O（query in, chunks+citations out），禁用RAG侧二次编排。

## 3.2 OCR：PaddleOCR（中文优先推荐）

推荐选择：`PaddleOCR`

原因：

- 中文识别效果通常优于通用 Tesseract 默认配置
- 对教材、扫描件、截图类场景更稳
- 生态成熟，工程落地案例多

备选：Tesseract。  
适合轻量和纯英文场景；若以中文书籍为主，首选 PaddleOCR。

## 3.3 向量数据库：PostgreSQL + pgvector

推荐选择：`PostgreSQL + pgvector`

原因：

- 与你 `bluegraph` 规划一致，长期架构方向统一
- 一套数据库同时承载业务数据与向量数据，减少系统碎片化
- SQL 可直接做 metadata 过滤（书名、章节、页码、来源类型）
- 迁移与运维门槛相对可控

备选：Qdrant/Weaviate。  
若后续检索规模显著增长可评估迁移；当前阶段 pgvector 足够。

## 3.4 Embedding 与 Rerank

Embedding 推荐：

- 本地/开源优先：`bge-m3`（中英混合、长文本场景表现稳）
- 云服务优先：OpenAI text-embedding 系列（运维简单）

Rerank 推荐：

- `bge-reranker`（提升 top-k 相关性，降低“看起来像但不相关”的片段）

---

## 4. 目标架构（与现有项目融合）

建议新增模块（不破坏现有 API/Agent 主流程）：

- `app/rag/ingest/`：解析、OCR、清洗、切块
- `app/rag/index/`：embedding、入库、索引维护
- `app/rag/retrieve/`：检索、重排、引用组装
- `app/rag/schemas.py`：RAG 数据模型
- `app/api/knowledge.py`：资料导入/索引管理/检索调试端点
- `app/skills/retrieve_skill.py`：供 Agent 调用的检索 skill

与现有层次关系：

1. API 触发 ingest/index  
2. 检索能力作为 skill 注入 AgentService / graph 节点  
3. 最终回复包含 citation（来源、章节、页码、图片ID）

---

## 5. 数据模型设计（关键字段）

建议核心表（PostgreSQL）：

1) `knowledge_documents`
- `id`
- `book_id`
- `source_type`（pdf/md/txt/web/image_ocr）
- `source_uri`
- `title`
- `created_at`

2) `knowledge_chunks`
- `id`
- `document_id`
- `book_id`
- `chapter`
- `page_no`
- `image_id`（如果来源是图片 OCR）
- `chunk_text`
- `chunk_tokens`
- `embedding`（vector）
- `metadata_json`
- `created_at`

3) `knowledge_ingest_jobs`
- `id`
- `book_id`
- `status`
- `total_files`
- `processed_files`
- `error_message`
- `created_at`
- `updated_at`

说明：  
`book_id + chapter + page_no + image_id` 是后续可解释引用的关键。

---

## 6. 端到端处理流程

## 6.1 Ingest 流程

1. 上传书籍文件（文本与图片）  
2. 文件类型识别  
3. 文本文件直接抽取正文  
4. 图片文件执行 OCR 得到文本  
5. 统一清洗（去水印、去页眉页脚噪声、规范空白）  
6. 结构化切块（章节优先 + token 窗口）

## 6.2 Index 流程

1. 对 chunk 生成 embedding  
2. 写入 `knowledge_chunks`  
3. 建立向量索引与 metadata 索引  
4. 记录 ingest job 状态

## 6.3 Retrieve 流程

1. Query embedding 检索 top-k  
2. BM25 关键词召回（可选）  
3. 融合排序（Hybrid）  
4. Rerank 精排  
5. 返回片段 + 引用元数据

## 6.4 Answer 生成

1. 将 top 证据片段注入 prompt  
2. 约束模型“只依据证据回答”  
3. 输出 `answer + citations[]`

---

## 7. 切块策略（整本书场景）

推荐参数（首版）：

- chunk size：300~800 tokens
- overlap：80~120 tokens
- 优先按“章节标题 -> 段落”切分，再按 token 补切

为什么：

- 过小 chunk：语义不完整，召回后难回答
- 过大 chunk：向量语义稀释，召回精度下降
- 章节优先能更稳定保留教学上下文

---

## 8. OCR 质量控制策略

建议在 OCR 后增加：

- 置信度阈值过滤（低置信文本打标）
- 版面噪声清理（页眉、页脚、页码重复）
- 同页重复行去重
- 保留原图坐标/页码映射（方便后续回溯）

验收基线（建议）：

- 样本页字符识别准确率达到可检索可读水平
- 关键术语召回正确（尤其章节标题、定义、公式说明）

---

## 9. API 设计建议（最小可用）

新增：

- `POST /knowledge/ingest`：提交导入任务
- `GET /knowledge/ingest/{job_id}`：查询任务状态
- `POST /knowledge/retrieve`：检索调试（返回 chunks + scores）
- `POST /knowledge/answer`：问答（返回 citations）

回答结构建议：

```json
{
  "answer": "......",
  "citations": [
    {
      "book_id": "book_python_001",
      "chapter": "第3章",
      "page_no": 57,
      "image_id": "img_0032",
      "snippet": "......"
    }
  ]
}
```

---

## 10. 实施分阶段计划（可直接执行）

## Phase A：最小可跑通（1-2 个迭代）

- 建立 `app/rag` 目录与基础 schema
- 接入文本文件 ingest + 切块 + pgvector 入库
- 实现 `retrieve` 与 `/knowledge/retrieve`
- 将检索 skill 接到 `/chat` 的可控分支（先开关控制）

交付标准：

- 能对一本文本资料完成导入与检索
- `/chat` 可返回带引用回答

## Phase B：图片 OCR 融合

- 接入 PaddleOCR
- 图片 -> OCR 文本 -> 统一切块/向量化
- 引用中带 `image_id`

交付标准：

- 图片资料可被检索并参与回答
- 引用可定位到图片来源

## Phase C：检索质量增强

- 加 Hybrid（向量 + BM25）
- 接入 reranker
- 加评测集（命中率、MRR、引用正确率）

交付标准：

- 检索质量可量化，较 Phase A 明显提升

## Phase D：工程化与稳定性

- 异步 ingest 任务队列
- 重试与失败补偿
- 观测指标（耗时、命中率、失败率）

---

## 11. 关键风险与应对

风险 1：OCR 误识别导致召回噪声  
应对：OCR 置信度过滤 + rerank + 术语词典校正

风险 2：整本书切块质量不稳定  
应对：章节结构优先切块 + 抽样人工校验 + 自动评测集

风险 3：回答“看似合理但证据弱”  
应对：强制 citations 输出；无证据时返回“证据不足”

风险 4：性能与成本上升  
应对：离线 embedding、缓存高频 query、批处理 ingest

---

## 12. 与当前项目的最小改造点

1. 配置新增（`.env`）：
- `RAG_ENABLED`
- `RAG_BACKEND=pgvector`
- `OCR_ENGINE=paddleocr`
- `EMBEDDING_PROVIDER`

2. 服务层新增：
- `RAGIngestService`
- `RAGRetrieveService`

3. Skill 层新增：
- `retrieve_skill`（并注册）

4. Agent 流程新增：
- 在 explain/followup 前后按条件调用检索，注入 `topic_context`

---

## 13. 选型结论（最终建议）

最终推荐组合：

- RAG 编排：`LlamaIndex`
- OCR：`PaddleOCR`
- 向量存储：`PostgreSQL + pgvector`
- Embedding：`bge-m3`（或 OpenAI embedding）
- Rerank：`bge-reranker`

这是在你当前代码基础上“改造成本最低、落地速度快、可持续演进”的方案，且与既有 `bluegraph` 架构路线一致。

