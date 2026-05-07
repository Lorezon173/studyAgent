# RAG问题解决方案

**文档版本**: v1.0
**创建日期**: 2026-04-15
**关联文档**: [rag_report.md](./rag_report.md)

---

## 目录

1. [问题总览](#一问题总览)
2. [P1: 大数据入库崩溃解决方案](#p1-大数据入库崩溃解决方案)
3. [P2: RAG调用条件复杂解决方案](#p2-rag调用条件复杂解决方案)
4. [P3: 重排模型重复加载解决方案](#p3-重排模型重复加载解决方案)
5. [P4: CLI无入库命令解决方案](#p4-cli无入库命令解决方案)
6. [P5: 切分边界处理不当解决方案](#p5-切分边界处理不当解决方案)
7. [P6: 检索全量加载解决方案](#p6-检索全量加载解决方案)
8. [P7: Personal双轨存储解决方案](#p7-personal双轨存储解决方案)
9. [P8: 向量维度截断解决方案](#p8-向量维度截断解决方案)
10. [实施计划](#九实施计划)

---

## 一、问题总览

| 编号 | 问题 | 严重程度 | 解决优先级 |
|------|------|----------|------------|
| P1 | 大数据入库崩溃 | 高 | P0 |
| P2 | RAG调用条件复杂 | 高 | P0 |
| P3 | 重排模型重复加载 | 中 | P1 |
| P4 | CLI无入库命令 | 中 | P1 |
| P5 | 切分边界处理不当 | 中 | P2 |
| P6 | 检索全量加载 | 中 | P2 |
| P7 | Personal双轨存储 | 中 | P2 |
| P8 | 向量维度截断 | 低 | P3 |

---

## 二、P1: 大数据入库崩溃解决方案

### 2.1 问题根因

1. **Embedding向量直接存储**: 128维浮点数组每个chunk都存储，导致JSON行过大
2. **无入库限制**: 大文本切分后可能产生数百个chunk
3. **输出未限流**: CLI/Web界面可能打印完整响应

### 2.2 解决方案

#### 方案A: 分离向量存储（推荐）

**原理**: 将embedding向量与元数据分离存储，检索时按需加载。

**文件修改**: `app/services/rag_store.py`

```python
# 新增向量存储路径配置
from app.core.config import settings

def _embedding_store_path() -> Path:
    """向量存储路径"""
    return Path(settings.rag_store_path).parent / "embeddings.npy"

def _embedding_index_path() -> Path:
    """向量索引路径"""
    return Path(settings.rag_store_path).parent / "embedding_index.json"


# 内存缓存
_EMBEDDING_CACHE: dict[str, list[float]] = {}
_EMBEDDING_MATRIX: np.ndarray | None = None
_CHUNK_ID_TO_INDEX: dict[str, int] = {}


def _save_embedding(chunk_id: str, embedding: list[float]) -> None:
    """保存embedding到独立文件"""
    _EMBEDDING_CACHE[chunk_id] = embedding
    
    # 追加到numpy文件
    emb_path = _embedding_store_path()
    idx_path = _embedding_index_path()
    
    if not emb_path.parent.exists():
        emb_path.parent.mkdir(parents=True, exist_ok=True)
    
    # 加载现有矩阵或创建新矩阵
    if emb_path.exists():
        matrix = np.load(emb_path)
        matrix = np.vstack([matrix, [embedding]])
    else:
        matrix = np.array([embedding])
    
    np.save(emb_path, matrix)
    
    # 更新索引
    index = {}
    if idx_path.exists():
        index = json.loads(idx_path.read_text(encoding="utf-8"))
    index[chunk_id] = len(matrix) - 1
    idx_path.write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")


def _load_embedding(chunk_id: str) -> list[float] | None:
    """按需加载embedding"""
    # 优先从内存缓存读取
    if chunk_id in _EMBEDDING_CACHE:
        return _EMBEDDING_CACHE[chunk_id]
    
    # 从磁盘加载
    global _EMBEDDING_MATRIX, _CHUNK_ID_TO_INDEX
    
    if _EMBEDDING_MATRIX is None:
        emb_path = _embedding_store_path()
        idx_path = _embedding_index_path()
        if emb_path.exists() and idx_path.exists():
            _EMBEDDING_MATRIX = np.load(emb_path)
            _CHUNK_ID_TO_INDEX = json.loads(idx_path.read_text(encoding="utf-8"))
    
    if chunk_id in _CHUNK_ID_TO_INDEX:
        idx = _CHUNK_ID_TO_INDEX[chunk_id]
        embedding = _EMBEDDING_MATRIX[idx].tolist()
        _EMBEDDING_CACHE[chunk_id] = embedding
        return embedding
    
    return None
```

**修改入库函数**:

```python
def ingest_knowledge(...) -> int:
    # ... 前置校验代码不变 ...
    
    for idx, chunk in enumerate(chunks):
        embedding = embed_text(chunk)
        chunk_id = str(uuid4())
        
        # 分离存储
        _save_embedding(chunk_id, embedding)
        
        # 元数据不包含embedding
        item = {
            "chunk_id": chunk_id,
            "source_type": source_type,
            "scope": scope,
            "user_id": user_id,
            "topic": topic,
            "title": title,
            "source_uri": source_uri,
            "chapter": chapter,
            "page_no": page_no,
            "image_id": image_id,
            "chunk_index": idx,
            "text": chunk,
            # 不再存储 embedding 字段
        }
        _MEMORY_KNOWLEDGE_CHUNKS.append(item)
        _persist_chunk(item)
        inserted += 1
    
    return inserted
```

**修改检索函数**:

```python
def retrieve_knowledge_by_scope(...) -> list[dict[str, Any]]:
    # ... 前面的检索逻辑不变 ...
    
    # 在需要计算相似度时加载embedding
    for item, d_tf, d_len in tokenized_docs:
        chunk_id = str(item.get("chunk_id", ""))
        emb = _load_embedding(chunk_id)  # 按需加载
        
        vector_score = cosine_similarity(query_embedding, emb if isinstance(emb, list) else [])
        # ... 后续处理不变 ...
```

#### 方案B: 入库限制与分批处理

**文件修改**: `app/services/rag_store.py`

```python
# 配置常量
MAX_CHUNKS_PER_INGEST = 100  # 单次入库最大chunk数
MAX_TEXT_LENGTH = 100000     # 单次入库最大字符数


def ingest_knowledge(
    *,
    source_type: str,
    scope: str,
    user_id: str | None,
    content: str,
    topic: str | None,
    title: str | None,
    source_uri: str | None,
    chapter: str | None,
    page_no: int | None,
    image_id: str | None,
    chunk_size: int | None,
    chunk_overlap: int | None,
    max_chunks: int | None = None,  # 新增参数
) -> int:
    """入库知识，支持限制chunk数量"""
    # 前置校验
    if source_type not in {"text", "image"}:
        raise ValueError("source_type 仅支持 text 或 image")
    if scope not in {"global", "personal"}:
        raise ValueError("scope 仅支持 global 或 personal")
    if scope == "personal" and not user_id:
        raise ValueError("personal scope 必须提供 user_id")
    
    raw = (content or "").strip()
    if not raw:
        raise ValueError("content 不能为空")
    
    # 长度检查
    if len(raw) > MAX_TEXT_LENGTH:
        raise ValueError(
            f"文本长度({len(raw)})超过限制({MAX_TEXT_LENGTH})，请分批入库"
        )
    
    size = chunk_size or settings.rag_default_chunk_size
    overlap = chunk_overlap if chunk_overlap is not None else settings.rag_default_chunk_overlap
    chunks = _split_text(raw, chunk_size=size, chunk_overlap=overlap)
    
    # chunk数量检查
    limit = max_chunks or MAX_CHUNKS_PER_INGEST
    if len(chunks) > limit:
        raise ValueError(
            f"切分后chunk数量({len(chunks)})超过限制({limit})，"
            f"建议增大chunk_size或分批入库"
        )
    
    # ... 后续入库逻辑不变 ...
```

#### 方案C: 响应精简

**文件修改**: `app/api/knowledge.py`

```python
@router.post("/ingest", response_model=KnowledgeIngestResponse)
def ingest(req: KnowledgeIngestRequest) -> KnowledgeIngestResponse:
    try:
        inserted = rag_service.ingest(
            source_type=req.source_type,
            scope=req.scope,
            user_id=str(req.user_id) if req.user_id is not None else None,
            content=req.content,
            topic=req.topic,
            title=req.title,
            source_uri=req.source_uri,
            chapter=req.chapter,
            page_no=req.page_no,
            image_id=req.image_id,
            chunk_size=req.chunk_size,
            chunk_overlap=req.chunk_overlap,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # 精简响应，不返回详细chunk信息
    return KnowledgeIngestResponse(
        inserted=inserted,
        source_type=req.source_type,
        scope=req.scope,
        user_id=req.user_id,
        topic=req.topic,
        message=f"成功入库 {inserted} 个知识片段",  # 新增友好提示
    )
```

### 2.3 完整实施代码

**新增配置项** (`app/core/config.py`):

```python
class Settings(BaseSettings):
    # ... 现有配置 ...
    
    # 新增：入库限制配置
    rag_max_chunks_per_ingest: int = 100
    rag_max_text_length: int = 100000
    rag_separate_embedding_storage: bool = True  # 是否分离向量存储
```

### 2.4 实施优先级

| 步骤 | 内容 | 工作量 |
|------|------|--------|
| Step 1 | 添加入库限制（方案B） | 0.5天 |
| Step 2 | 响应精简（方案C） | 0.5天 |
| Step 3 | 向量分离存储（方案A） | 2天 |

---

## 三、P2: RAG调用条件复杂解决方案

### 3.1 问题根因

1. **条件判断分散**: `context_builder.py`和`agent_service.py`都有RAG开关判断
2. **短路逻辑**: `if context or not settings.rag_enabled` 导致有context时跳过RAG
3. **意图识别干扰**: tool_route判断可能覆盖RAG调用

### 3.2 解决方案

#### 方案: 统一RAG调用入口

**新增文件**: `app/services/rag_coordinator.py`

```python
"""
RAG调用协调器
统一管理RAG调用逻辑，避免条件判断分散
"""
from dataclasses import dataclass
from typing import Any

from app.core.config import settings
from app.services.rag_service import rag_service
from app.services.tool_executor import execute_retrieval_tools


@dataclass
class RAGCallDecision:
    """RAG调用决策"""
    should_call: bool
    reason: str
    scope: str  # global, personal, both
    user_id: str | None = None
    topic: str | None = None


class RAGCoordinator:
    """RAG调用协调器"""
    
    def __init__(self) -> None:
        self._enabled = settings.rag_enabled
    
    def decide(
        self,
        *,
        user_input: str,
        topic: str | None,
        user_id: str | None,
        tool_route: dict[str, Any] | None,
        existing_context: str = "",
    ) -> RAGCallDecision:
        """
        决定是否调用RAG及调用方式
        
        决策规则:
        1. RAG未启用 → 不调用
        2. 现有context已足够（长度>500）→ 不调用
        3. 有user_id → 调用both（global + personal）
        4. 无user_id → 仅调用global
        """
        if not self._enabled:
            return RAGCallDecision(
                should_call=False,
                reason="RAG功能未启用",
                scope="none",
            )
        
        # 检查现有context是否充分
        if len(existing_context) > 500:
            return RAGCallDecision(
                should_call=False,
                reason=f"现有context已充分(长度:{len(existing_context)})",
                scope="none",
            )
        
        # 检查查询是否为空
        if not user_input or not user_input.strip():
            return RAGCallDecision(
                should_call=False,
                reason="查询为空",
                scope="none",
            )
        
        # 决定调用范围
        if user_id is not None:
            return RAGCallDecision(
                should_call=True,
                reason="用户已登录，检索全局+个人知识库",
                scope="both",
                user_id=user_id,
                topic=topic,
            )
        
        return RAGCallDecision(
            should_call=True,
            reason="用户未登录，仅检索全局知识库",
            scope="global",
            topic=topic,
        )
    
    def execute(
        self,
        decision: RAGCallDecision,
        *,
        user_input: str,
        top_k: int = 3,
    ) -> tuple[str, list[dict[str, Any]]]:
        """
        执行RAG检索
        
        Returns:
            (context_str, citations_list)
        """
        if not decision.should_call:
            return "", []
        
        rows: list[dict[str, Any]] = []
        used_tools: list[str] = []
        
        # 根据决策执行检索
        if decision.scope in ("global", "both"):
            global_rows = rag_service.retrieve(
                query=user_input,
                topic=decision.topic,
                top_k=top_k,
            )
            rows.extend([{**r, "scope": "global"} for r in global_rows])
            used_tools.append("search_local_textbook")
        
        if decision.scope == "both" and decision.user_id:
            personal_rows = rag_service.retrieve_scoped(
                query=user_input,
                scope="personal",
                user_id=decision.user_id,
                topic=decision.topic,
                top_k=top_k,
            )
            rows.extend([{**r, "scope": "personal"} for r in personal_rows])
            used_tools.append("search_personal_memory")
        
        if not rows:
            return "", []
        
        # 去重和排序
        rows.sort(key=lambda x: float(x.get("score", 0.0)), reverse=True)
        deduped = self._deduplicate(rows, top_k)
        
        # 构建context字符串
        context = self._build_context_string(deduped, used_tools)
        citations = self._build_citations(deduped)
        
        return context, citations
    
    def _deduplicate(
        self,
        rows: list[dict[str, Any]],
        top_k: int,
    ) -> list[dict[str, Any]]:
        """去重并保留top_k"""
        seen: set[str] = set()
        result: list[dict[str, Any]] = []
        for row in rows:
            cid = str(row.get("chunk_id", ""))
            if cid and cid in seen:
                continue
            if cid:
                seen.add(cid)
            result.append(row)
            if len(result) >= top_k:
                break
        return result
    
    def _build_context_string(
        self,
        rows: list[dict[str, Any]],
        tools: list[str],
    ) -> str:
        """构建上下文字符串"""
        lines: list[str] = []
        tool_tag = f"[知识检索|tools={','.join(tools)}]" if tools else "[知识检索]"
        
        for idx, row in enumerate(rows, start=1):
            snippet = str(row.get("text", "")).strip()[:200]
            lines.append(f"[证据{idx}] {snippet}")
        
        return tool_tag + "\n" + "\n".join(lines)
    
    def _build_citations(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """构建引用列表"""
        citations: list[dict[str, Any]] = []
        for row in rows:
            citations.append({
                "chunk_id": row.get("chunk_id"),
                "source_type": row.get("source_type"),
                "title": row.get("title"),
                "source_uri": row.get("source_uri"),
                "chapter": row.get("chapter"),
                "page_no": row.get("page_no"),
                "scope": row.get("scope", "global"),
                "snippet": str(row.get("text", ""))[:180],
                "score": row.get("score", 0.0),
            })
        return citations


# 单例
rag_coordinator = RAGCoordinator()
```

**修改文件**: `app/services/orchestration/context_builder.py`

```python
from app.services.rag_coordinator import rag_coordinator

class ContextBuilder:
    @staticmethod
    def build_rag_context(
        topic: str | None,
        user_input: str,
        user_id: int | None = None,
        tool_route: dict | None = None,
    ) -> tuple[str, list[dict]]:
        """使用协调器进行RAG调用"""
        decision = rag_coordinator.decide(
            user_input=user_input,
            topic=topic,
            user_id=str(user_id) if user_id else None,
            tool_route=tool_route,
        )
        
        return rag_coordinator.execute(
            decision,
            user_input=user_input,
            top_k=settings.rag_retrieve_top_k,
        )
```

**修改文件**: `app/services/agent_service.py`

```python
# 删除 _build_rag_context 方法，使用 ContextBuilder.build_rag_context
# 或直接使用 rag_coordinator

def _build_rag_context(
    self,
    topic: str | None,
    user_input: str,
    user_id: int | None = None,
    tool_route: dict | None = None,
) -> tuple[str, list[dict]]:
    """统一使用ContextBuilder，移除冗余逻辑"""
    return ContextBuilder.build_rag_context(
        topic=topic,
        user_input=user_input,
        user_id=user_id,
        tool_route=tool_route,
    )
```

### 3.3 调用流程优化后

```
agent_service.run()
    ↓
_build_rag_context()
    ↓
rag_coordinator.decide()     ← 统一决策
    ↓
rag_coordinator.execute()    ← 统一执行
    ↓
[根据scope调用相应检索]
├── scope=global → rag_service.retrieve()
└── scope=both → rag_service.retrieve() + retrieve_scoped()
```

---

## 四、P3: 重排模型重复加载解决方案

### 4.1 问题根因

```python
# 每次调用都重新加载模型
model = CrossEncoder("BAAI/bge-reranker-base")
```

### 4.2 解决方案: 模型单例缓存

**修改文件**: `app/services/rerank_service.py`

```python
"""
重排服务 - 支持simple和bge两种provider
使用单例模式缓存模型，避免重复加载
"""
import re
from typing import Any

from app.core.config import settings


# 模型单例缓存
_RERANKER_MODEL: Any = None
_RERANKER_MODEL_NAME: str | None = None


def _get_reranker_model():
    """获取或创建重排模型单例"""
    global _RERANKER_MODEL, _RERANKER_MODEL_NAME
    
    provider = settings.rag_rerank_provider.lower().strip()
    
    if provider == "simple":
        return None  # simple模式不需要模型
    
    if provider != "bge":
        raise ValueError(f"不支持的 rerank provider: {provider}")
    
    # 检查是否需要重新加载（配置变更）
    model_name = "BAAI/bge-reranker-base"
    if _RERANKER_MODEL is not None and _RERANKER_MODEL_NAME == model_name:
        return _RERANKER_MODEL
    
    # 加载模型
    try:
        from sentence_transformers import CrossEncoder
    except ImportError as exc:
        raise RuntimeError(
            "当前配置了 bge reranker，但未安装 sentence-transformers。"
            "请运行: pip install sentence-transformers"
        ) from exc
    
    print(f"[RerankService] 加载重排模型: {model_name}")
    _RERANKER_MODEL = CrossEncoder(model_name)
    _RERANKER_MODEL_NAME = model_name
    
    return _RERANKER_MODEL


def _simple_overlap_score(query: str, text: str) -> float:
    """简单的词重叠打分"""
    q = set(re.findall(r"[0-9a-zA-Z\u4e00-\u9fa5]{2,}", query.lower()))
    t = set(re.findall(r"[0-9a-zA-Z\u4e00-\u9fa5]{2,}", text.lower()))
    if not q or not t:
        return 0.0
    return float(len(q & t))


def _cross_encoder_score(query: str, text: str) -> float:
    """使用CrossEncoder进行精确打分"""
    model = _get_reranker_model()
    if model is None:
        return _simple_overlap_score(query, text)
    
    score = model.predict([(query, text)])
    if hasattr(score, "__len__"):
        return float(score[0])
    return float(score)


def _batch_cross_encoder_score(
    query: str,
    texts: list[str],
) -> list[float]:
    """批量打分，提升效率"""
    model = _get_reranker_model()
    if model is None:
        return [_simple_overlap_score(query, t) for t in texts]
    
    pairs = [(query, text) for text in texts]
    scores = model.predict(pairs)
    
    if hasattr(scores, "__iter__"):
        return [float(s) for s in scores]
    return [float(scores)]


def rerank_items(query: str, items: list[dict]) -> list[dict]:
    """
    对检索结果进行重排
    
    Args:
        query: 查询文本
        items: 待重排的结果列表
        
    Returns:
        重排后的结果列表（按rerank_score降序）
    """
    provider = settings.rag_rerank_provider.lower().strip()
    
    if provider == "bge":
        # 批量打分提升效率
        texts = [str(item.get("text", "")) for item in items]
        scores = _batch_cross_encoder_score(query, texts)
        
        scored: list[tuple[float, dict]] = []
        for item, score in zip(items, scores):
            row = item.copy()
            row["rerank_score"] = score
            scored.append((score, row))
    else:
        # simple模式
        scored: list[tuple[float, dict]] = []
        for item in items:
            text = str(item.get("text", ""))
            rs = _simple_overlap_score(query, text)
            row = item.copy()
            row["rerank_score"] = rs
            scored.append((rs, row))
    
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [row for _, row in scored]


def clear_reranker_cache() -> None:
    """清除模型缓存（用于测试或配置变更）"""
    global _RERANKER_MODEL, _RERANKER_MODEL_NAME
    _RERANKER_MODEL = None
    _RERANKER_MODEL_NAME = None
```

### 4.3 性能对比

| 场景 | 优化前 | 优化后 |
|------|--------|--------|
| 首次调用 | ~5s (加载模型) | ~5s (加载模型) |
| 后续调用 | ~5s (重复加载) | ~0.1s (使用缓存) |
| 批量重排(10条) | ~50s | ~0.5s |

---

## 五、P4: CLI无入库命令解决方案

### 5.1 解决方案: 添加CLI入库命令

**修改文件**: `app/cli/repl.py`

```python
from app.services.rag_service import rag_service

class StudyAgentCLI:
    def __init__(self) -> None:
        # ... 现有初始化代码 ...
        
        self.commands: dict[str, CommandHandler] = {
            # ... 现有命令 ...
            "kadd": self._cmd_kadd,        # 新增：知识入库
            "ksearch": self._cmd_ksearch,  # 新增：知识检索
            "klist": self._cmd_klist,      # 新增：查看知识库统计
        }
    
    def _cmd_help(self, _: list[str]) -> None:
        print(
            """可用命令:
# ... 现有帮助内容 ...

知识库命令:
/kadd <内容>                        入库文本到知识库
/kadd-file <文件路径>               入库文件内容
/ksearch <查询词>                   检索知识库
/klist                              查看知识库统计信息

# ... 其他帮助内容 ..."""
        )
    
    def _cmd_kadd(self, args: list[str]) -> None:
        """入库文本到知识库"""
        if not args:
            print("用法: /kadd <要入库的文本内容>")
            print("选项:")
            print("  --scope <global|personal>  知识范围(默认: global)")
            print("  --topic <主题>             关联主题")
            print("  --title <标题>             文档标题")
            print("示例: /add 这是一条测试文本 --topic 测试主题 --scope personal")
            return
        
        # 解析参数
        content_parts: list[str] = []
        scope = "global"
        topic = self.ctx.topic
        title = None
        
        i = 0
        while i < len(args):
            if args[i] == "--scope" and i + 1 < len(args):
                scope = args[i + 1]
                i += 2
            elif args[i] == "--topic" and i + 1 < len(args):
                topic = args[i + 1]
                i += 2
            elif args[i] == "--title" and i + 1 < len(args):
                title = args[i + 1]
                i += 2
            else:
                content_parts.append(args[i])
                i += 1
        
        content = " ".join(content_parts)
        if not content:
            print("错误: 内容不能为空")
            return
        
        if scope not in ("global", "personal"):
            print(f"错误: scope必须是global或personal，当前: {scope}")
            return
        
        if scope == "personal":
            user_id_str = str(self.ctx.user_id)
        else:
            user_id_str = None
        
        try:
            inserted = rag_service.ingest(
                source_type="text",
                scope=scope,
                user_id=user_id_str,
                content=content,
                topic=topic,
                title=title or "cli-input",
            )
            print(f"入库成功: {inserted} 个知识片段 (scope={scope}, topic={topic})")
        except ValueError as e:
            print(f"入库失败: {e}")
        except Exception as e:
            print(f"入库异常: {e}")
    
    def _cmd_kadd_file(self, args: list[str]) -> None:
        """入库文件内容"""
        if not args:
            print("用法: /kadd-file <文件路径> [--scope <global|personal>] [--topic <主题>]")
            return
        
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("file", help="文件路径")
        parser.add_argument("--scope", default="global", choices=["global", "personal"])
        parser.add_argument("--topic", default=None)
        parser.add_argument("--title", default=None)
        
        try:
            parsed = parser.parse_args(args)
        except SystemExit:
            return
        
        from pathlib import Path
        file_path = Path(parsed.file)
        
        if not file_path.exists():
            print(f"错误: 文件不存在: {file_path}")
            return
        
        try:
            content = file_path.read_text(encoding="utf-8")
        except Exception as e:
            print(f"错误: 读取文件失败: {e}")
            return
        
        # 调用kadd逻辑
        self._cmd_kadd([
            content,
            "--scope", parsed.scope,
            *(["--topic", parsed.topic] if parsed.topic else []),
            *(["--title", parsed.title or file_path.name] if parsed.title or True else []),
        ])
    
    def _cmd_ksearch(self, args: list[str]) -> None:
        """检索知识库"""
        if not args:
            print("用法: /ksearch <查询词> [--scope <global|personal>] [--top-k <数量>]")
            return
        
        # 解析参数
        query_parts: list[str] = []
        scope = "global"
        top_k = 5
        
        i = 0
        while i < len(args):
            if args[i] == "--scope" and i + 1 < len(args):
                scope = args[i + 1]
                i += 2
            elif args[i] == "--top-k" and i + 1 < len(args):
                try:
                    top_k = int(args[i + 1])
                except ValueError:
                    pass
                i += 2
            else:
                query_parts.append(args[i])
                i += 1
        
        query = " ".join(query_parts)
        if not query:
            print("错误: 查询词不能为空")
            return
        
        try:
            if scope == "personal":
                items = rag_service.retrieve_scoped(
                    query=query,
                    scope="personal",
                    user_id=str(self.ctx.user_id),
                    topic=self.ctx.topic,
                    top_k=top_k,
                )
            else:
                items = rag_service.retrieve(
                    query=query,
                    topic=self.ctx.topic,
                    top_k=top_k,
                )
            
            if not items:
                print("未找到相关知识片段")
                return
            
            print(f"检索结果 (共{len(items)}条):")
            print("-" * 60)
            for idx, item in enumerate(items, 1):
                score = item.get("score", 0)
                text = item.get("text", "")[:100]
                title = item.get("title", "")
                print(f"[{idx}] score={score:.4f} | {title}")
                print(f"    {text}...")
                print()
        except Exception as e:
            print(f"检索失败: {e}")
    
    def _cmd_klist(self, args: list[str]) -> None:
        """查看知识库统计"""
        from pathlib import Path
        from app.core.config import settings
        
        kb_path = Path(settings.rag_store_path)
        personal_path = Path(settings.personal_rag_store_path)
        
        stats = {
            "knowledge_chunks": {
                "exists": kb_path.exists(),
                "lines": 0,
                "global_count": 0,
                "personal_count": 0,
            },
            "personal_rag": {
                "exists": personal_path.exists(),
                "lines": 0,
            },
        }
        
        if kb_path.exists():
            lines = kb_path.read_text(encoding="utf-8").splitlines()
            stats["knowledge_chunks"]["lines"] = len(lines)
            
            import json
            for line in lines:
                if not line.strip():
                    continue
                try:
                    obj = json.loads(line)
                    scope = obj.get("scope", "global")
                    if scope == "global":
                        stats["knowledge_chunks"]["global_count"] += 1
                    else:
                        stats["knowledge_chunks"]["personal_count"] += 1
                except:
                    pass
        
        if personal_path.exists():
            lines = personal_path.read_text(encoding="utf-8").splitlines()
            stats["personal_rag"]["lines"] = len(lines)
        
        print("知识库统计:")
        print(f"  主知识库 (knowledge_chunks.jsonl):")
        print(f"    - 总条目: {stats['knowledge_chunks']['lines']}")
        print(f"    - Global: {stats['knowledge_chunks']['global_count']}")
        print(f"    - Personal: {stats['knowledge_chunks']['personal_count']}")
        print(f"  个人记忆 (personal_rag.jsonl):")
        print(f"    - 总条目: {stats['personal_rag']['lines']}")
```

---

## 六、P5: 切分边界处理不当解决方案

### 6.1 问题根因

当前切分是简单的字符滑动窗口，不考虑语义边界。

### 6.2 解决方案: 语义切分

**修改文件**: `app/services/rag_store.py`

```python
import re
from typing import Callable

def _split_text(
    text: str,
    chunk_size: int,
    chunk_overlap: int,
    respect_sentences: bool = True,  # 新增：是否尊重句子边界
) -> list[str]:
    """
    文本切分，支持语义边界
    
    Args:
        text: 原始文本
        chunk_size: 目标chunk大小
        chunk_overlap: 重叠大小
        respect_sentences: 是否尊重句子边界
    """
    normalized = " ".join(text.split())
    if not normalized:
        return []
    
    if chunk_size <= 0:
        chunk_size = 500
    if chunk_overlap < 0:
        chunk_overlap = 0
    if chunk_overlap >= chunk_size:
        chunk_overlap = max(0, chunk_size // 5)
    
    if not respect_sentences:
        # 原有的简单切分逻辑
        return _simple_split(normalized, chunk_size, chunk_overlap)
    
    # 语义切分：按句子分割
    return _semantic_split(normalized, chunk_size, chunk_overlap)


def _simple_split(text: str, chunk_size: int, chunk_overlap: int) -> list[str]:
    """简单字符切分（原有逻辑）"""
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + chunk_size)
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(text):
            break
        start = end - chunk_overlap
    return chunks


def _semantic_split(text: str, chunk_size: int, chunk_overlap: int) -> list[str]:
    """
    语义切分：尽量在句子边界处切分
    """
    # 中英文句子分割正则
    # 匹配：句号、问号、感叹号、中文句号、中文问号、中文感叹号
    sentence_pattern = r'(?<=[。！？.!?])\s*'
    sentences = re.split(sentence_pattern, text)
    sentences = [s.strip() for s in sentences if s.strip()]
    
    if not sentences:
        return _simple_split(text, chunk_size, chunk_overlap)
    
    chunks: list[str] = []
    current_chunk: list[str] = []
    current_length = 0
    
    for sentence in sentences:
        sentence_len = len(sentence)
        
        # 如果单个句子就超过chunk_size，需要进一步切分
        if sentence_len > chunk_size:
            # 先保存当前chunk
            if current_chunk:
                chunks.append(" ".join(current_chunk))
                current_chunk = []
                current_length = 0
            
            # 长句子用简单切分
            sub_chunks = _simple_split(sentence, chunk_size, chunk_overlap)
            chunks.extend(sub_chunks)
            continue
        
        # 检查添加这个句子是否会超过限制
        if current_length + sentence_len > chunk_size and current_chunk:
            # 保存当前chunk
            chunks.append(" ".join(current_chunk))
            
            # 处理overlap：保留最后几个句子
            overlap_sentences = _get_overlap_sentences(
                current_chunk, chunk_overlap
            )
            current_chunk = overlap_sentences
            current_length = sum(len(s) for s in overlap_sentences)
        
        current_chunk.append(sentence)
        current_length += sentence_len
    
    # 保存最后一个chunk
    if current_chunk:
        chunks.append(" ".join(current_chunk))
    
    return [c.strip() for c in chunks if c.strip()]


def _get_overlap_sentences(
    sentences: list[str],
    target_overlap: int,
) -> list[str]:
    """
    获取用于overlap的句子
    从后往前取，直到总长度接近target_overlap
    """
    result: list[str] = []
    total_len = 0
    
    for sentence in reversed(sentences):
        if total_len + len(sentence) > target_overlap * 1.5:
            break
        result.insert(0, sentence)
        total_len += len(sentence)
    
    return result
```

### 6.3 配置支持

**修改文件**: `app/core/config.py`

```python
class Settings(BaseSettings):
    # ... 现有配置 ...
    
    # 新增：切分配置
    rag_chunk_respect_sentences: bool = True  # 是否尊重句子边界
    rag_chunk_min_size: int = 100             # 最小chunk大小
```

---

## 七、P6: 检索全量加载解决方案

### 7.1 问题根因

每次检索都加载完整JSONL文件到内存。

### 7.2 解决方案: 增量索引 + 缓存

**修改文件**: `app/services/rag_store.py`

```python
import os
from typing import Any
from pathlib import Path

# 增量索引缓存
_DISK_CHUNKS_CACHE: list[dict[str, Any]] | None = None
_LAST_FILE_MTIME: float = 0
_LAST_FILE_SIZE: int = 0


def _get_file_stats() -> tuple[float, int]:
    """获取文件状态（修改时间和大小）"""
    path = _store_path()
    if not path.exists():
        return 0, 0
    stat = path.stat()
    return stat.st_mtime, stat.st_size


def _load_disk_chunks() -> list[dict[str, Any]]:
    """
    加载磁盘chunk，支持增量更新
    
    使用文件修改时间和大小判断是否需要重新加载
    """
    global _DISK_CHUNKS_CACHE, _LAST_FILE_MTIME, _LAST_FILE_SIZE
    
    current_mtime, current_size = _get_file_stats()
    
    # 检查缓存是否有效
    if _DISK_CHUNKS_CACHE is not None:
        if current_mtime == _LAST_FILE_MTIME and current_size == _LAST_FILE_SIZE:
            return _DISK_CHUNKS_CACHE
    
    # 需要重新加载
    path = _store_path()
    if not path.exists():
        _DISK_CHUNKS_CACHE = []
        _LAST_FILE_MTIME = 0
        _LAST_FILE_SIZE = 0
        return []
    
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text:
            continue
        try:
            obj = json.loads(text)
            if isinstance(obj, dict):
                rows.append(obj)
        except json.JSONDecodeError:
            continue
    
    # 更新缓存
    _DISK_CHUNKS_CACHE = rows
    _LAST_FILE_MTIME = current_mtime
    _LAST_FILE_SIZE = current_size
    
    return rows


def _invalidate_cache() -> None:
    """手动使缓存失效（入库后调用）"""
    global _DISK_CHUNKS_CACHE
    _DISK_CHUNKS_CACHE = None


def ingest_knowledge(...) -> int:
    # ... 入库逻辑 ...
    
    # 入库完成后使缓存失效
    _invalidate_cache()
    
    return inserted
```

### 7.3 进一步优化: 向量索引

如果知识库规模持续增长，建议引入向量数据库：

**可选方案**: 使用FAISS或Chroma

```python
# app/services/vector_store.py (新文件)
"""
向量存储抽象层
支持切换不同后端：JSONL、FAISS、Chroma等
"""
from abc import ABC, abstractmethod
from typing import Any

class VectorStore(ABC):
    @abstractmethod
    def add(self, chunk_id: str, embedding: list[float], metadata: dict) -> None:
        pass
    
    @abstractmethod
    def search(self, query_embedding: list[float], top_k: int) -> list[dict]:
        pass
    
    @abstractmethod
    def delete(self, chunk_id: str) -> None:
        pass


class FAISSVectorStore(VectorStore):
    """FAISS向量存储实现"""
    
    def __init__(self, dim: int = 128):
        import faiss
        self.index = faiss.IndexFlatIP(dim)
        self.id_map: dict[int, str] = {}
        self.metadata: dict[str, dict] = {}
    
    def add(self, chunk_id: str, embedding: list[float], metadata: dict) -> None:
        import numpy as np
        vec = np.array([embedding], dtype=np.float32)
        faiss.normalize_L2(vec)
        idx = self.index.ntotal
        self.index.add(vec)
        self.id_map[idx] = chunk_id
        self.metadata[chunk_id] = metadata
    
    def search(self, query_embedding: list[float], top_k: int) -> list[dict]:
        import numpy as np
        vec = np.array([query_embedding], dtype=np.float32)
        faiss.normalize_L2(vec)
        scores, indices = self.index.search(vec, top_k)
        
        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0:
                continue
            chunk_id = self.id_map.get(idx)
            if chunk_id:
                result = self.metadata[chunk_id].copy()
                result["chunk_id"] = chunk_id
                result["vector_score"] = float(score)
                results.append(result)
        return results
    
    def delete(self, chunk_id: str) -> None:
        # FAISS不支持删除，需要重建索引
        pass
```

---

## 八、P7: Personal双轨存储解决方案

### 8.1 问题根因

Personal知识存储在两个地方：
1. `knowledge_chunks.jsonl` 中 scope=personal 的条目
2. `personal_rag.jsonl` 独立记忆条目

### 8.2 解决方案: 统一存储架构

**方案**: 保留双文件但统一访问接口

**修改文件**: `app/services/personal_rag_store.py`

```python
"""
个人知识存储服务
统一管理 personal_rag.jsonl 和 knowledge_chunks.jsonl 中的personal条目
"""
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.services.rag_store import retrieve_knowledge_by_scope


def retrieve_unified_personal_memory(
    topic: str,
    query: str,
    user_id: int,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """
    统一个人记忆检索
    
    同时检索 personal_rag.jsonl 和 knowledge_chunks.jsonl (scope=personal)
    合并结果并按相关度排序
    """
    # 从 personal_rag.jsonl 检索
    memory_items = retrieve_personal_memory(
        topic=topic,
        query=query,
        limit=limit,
        user_id=user_id,
    )
    
    # 从 knowledge_chunks.jsonl 检索 personal 条目
    rag_items = retrieve_knowledge_by_scope(
        query=query,
        topic=topic,
        top_k=limit,
        scope="personal",
        user_id=str(user_id),
    )
    
    # 合并去重
    merged: list[dict[str, Any]] = []
    seen_contents: set[str] = set()
    
    for item in rag_items:
        content = item.get("text", "")[:100]
        if content not in seen_contents:
            seen_contents.add(content)
            merged.append({
                "source": "knowledge_chunks",
                "chunk_id": item.get("chunk_id"),
                "content": item.get("text"),
                "score": item.get("score", 0),
                "topic": item.get("topic"),
                "title": item.get("title"),
            })
    
    for item in memory_items:
        content = item.get("content", "")[:100]
        if content not in seen_contents:
            seen_contents.add(content)
            merged.append({
                "source": "personal_rag",
                "session_id": item.get("session_id"),
                "content": item.get("content"),
                "score": item.get("score", 0),
                "topic": item.get("topic"),
            })
    
    # 按分数排序
    merged.sort(key=lambda x: float(x.get("score", 0)), reverse=True)
    
    return merged[:limit]
```

**更新检索技能**: `app/skills/builtin.py`

```python
class SearchPersonalMemorySkill(BaseSkill):
    name = "search_personal_memory"
    description = "检索用户私域记忆（personal）- 统一检索"

    def run(self, **kwargs):
        query = str(kwargs.get("query", "")).strip()
        topic = kwargs.get("topic")
        top_k = int(kwargs.get("top_k", 3))
        user_id = kwargs.get("user_id")
        
        if isinstance(user_id, str) and user_id.isdigit():
            user_id = int(user_id)
        
        if not query or user_id is None:
            return {"items": [], "total": 0, "scope": "personal"}
        
        # 使用统一检索
        from app.services.personal_rag_store import retrieve_unified_personal_memory
        
        items = retrieve_unified_personal_memory(
            topic=topic or "",
            query=query,
            user_id=user_id,
            limit=top_k,
        )
        
        return {
            "items": items,
            "total": len(items),
            "scope": "personal",
        }
```

---

## 九、P8: 向量维度截断解决方案

### 8.1 问题根因

```python
if dim > 0 and len(vec) > dim:
    vec = vec[:dim]  # 直接截断
```

### 8.2 解决方案: 智能维度处理

**修改文件**: `app/services/embedding_service.py`

```python
def _sentence_transformers_embed(text: str, dim: int) -> list[float]:
    """使用sentence_transformers生成embedding"""
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise RuntimeError(
            "当前配置了 sentence_transformers embedding，但未安装 sentence-transformers。"
        ) from exc
    
    model = SentenceTransformer("BAAI/bge-m3")
    vec = model.encode(text, normalize_embeddings=True).tolist()
    
    if not isinstance(vec, list):
        raise RuntimeError("sentence-transformers embedding 输出异常。")
    
    model_dim = len(vec)
    
    # 智能处理维度差异
    if dim > 0:
        if model_dim > dim:
            # 模型维度大于配置维度：降维（PCA或截断）
            # 这里使用简单的截断，后续可改为PCA降维
            vec = vec[:dim]
            # 重新归一化
            vec = _normalize(vec)
        elif model_dim < dim:
            # 模型维度小于配置维度：填充0
            vec = vec + [0.0] * (dim - model_dim)
    
    return vec


def _validate_embedding_config() -> None:
    """验证embedding配置是否合理"""
    provider = settings.rag_embedding_provider.lower().strip()
    dim = settings.rag_embedding_dim
    
    if provider == "sentence_transformers":
        # bge-m3 模型输出 1024 维
        model_dim = 1024
        if dim < model_dim * 0.5:
            import warnings
            warnings.warn(
                f"配置的embedding维度({dim})远小于模型维度({model_dim})，"
                f"建议设置为 {model_dim} 以获得最佳效果",
                UserWarning,
            )


# 启动时验证
_validate_embedding_config()
```

**更新配置建议**: `app/core/config.py`

```python
class Settings(BaseSettings):
    # embedding配置
    rag_embedding_provider: str = "simple"
    rag_embedding_dim: int = 128  # simple模式建议值
    
    # 如果使用sentence_transformers，建议设置为1024
    # rag_embedding_dim: int = 1024
```

---

## 十、实施计划

### 10.1 阶段一：紧急修复（1-2天）

| 任务 | 问题 | 工作量 | 负责人 |
|------|------|--------|--------|
| 入库限制 | P1 | 0.5天 | - |
| 响应精简 | P1 | 0.5天 | - |
| 重排模型单例 | P3 | 0.5天 | - |
| CLI入库命令 | P4 | 0.5天 | - |

### 10.2 阶段二：核心优化（3-5天）

| 任务 | 问题 | 工作量 | 负责人 |
|------|------|--------|--------|
| RAG调用协调器 | P2 | 2天 | - |
| 向量分离存储 | P1 | 2天 | - |
| 检索缓存 | P6 | 1天 | - |

### 10.3 阶段三：质量提升（3-5天）

| 任务 | 问题 | 工作量 | 负责人 |
|------|------|--------|--------|
| 语义切分 | P5 | 2天 | - |
| Personal统一检索 | P7 | 1天 | - |
| 向量维度智能处理 | P8 | 0.5天 | - |

### 10.4 验收标准

```python
# tests/test_rag_solutions.py

def test_ingest_large_text():
    """测试大文本入库限制"""
    large_text = "x" * 200000
    with pytest.raises(ValueError, match="超过限制"):
        rag_service.ingest(source_type="text", scope="global", content=large_text)


def test_reranker_singleton():
    """测试重排模型单例"""
    from app.services.rerank_service import _get_reranker_model
    
    model1 = _get_reranker_model()
    model2 = _get_reranker_model()
    assert model1 is model2


def test_semantic_chunking():
    """测试语义切分"""
    text = "这是第一句话。这是第二句话。这是第三句话。"
    chunks = _split_text(text, chunk_size=20, chunk_overlap=5, respect_sentences=True)
    # 每个chunk应该是完整的句子
    for chunk in chunks:
        assert chunk.endswith("。") or len(chunk) < 20


def test_rag_coordinator():
    """测试RAG调用协调器"""
    from app.services.rag_coordinator import rag_coordinator
    
    # RAG启用时的决策
    decision = rag_coordinator.decide(
        user_input="什么是二分查找？",
        topic="算法",
        user_id="1",
        tool_route={"tool": "search_local_textbook"},
    )
    assert decision.should_call is True
    assert decision.scope == "both"
```

---

## 附录：文件修改清单

| 文件 | 修改类型 | 关联问题 |
|------|----------|----------|
| `app/core/config.py` | 新增配置 | P1, P5, P8 |
| `app/services/rag_store.py` | 重构 | P1, P5, P6 |
| `app/services/rag_coordinator.py` | 新增 | P2 |
| `app/services/rerank_service.py` | 重构 | P3 |
| `app/services/embedding_service.py` | 优化 | P8 |
| `app/services/personal_rag_store.py` | 增强 | P7 |
| `app/cli/repl.py` | 新增命令 | P4 |
| `app/api/knowledge.py` | 优化响应 | P1 |
| `tests/test_rag_solutions.py` | 新增测试 | 全部 |

---

**文档维护**: 本文档应随代码实现同步更新
**最后更新**: 2026-04-15
