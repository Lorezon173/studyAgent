from pydantic import BaseModel, Field


class KnowledgeIngestRequest(BaseModel):
    source_type: str = Field(..., description="数据来源类型: text|image")
    content: str = Field(..., description="原始文本或图片 OCR 结果/占位内容")
    scope: str = Field(default="global", description="知识轨道: global|personal")
    user_id: int | None = Field(default=None, description="个人轨道必填（数字ID）")
    topic: str | None = Field(default=None, description="关联学习主题")
    title: str | None = Field(default=None, description="文档标题")
    source_uri: str | None = Field(default=None, description="来源路径或标识")
    chapter: str | None = Field(default=None, description="章节标识")
    page_no: int | None = Field(default=None, description="页码")
    image_id: str | None = Field(default=None, description="图片ID")
    chunk_size: int | None = Field(default=None, description="切块大小")
    chunk_overlap: int | None = Field(default=None, description="切块重叠")


class KnowledgeIngestResponse(BaseModel):
    inserted: int
    source_type: str
    scope: str
    user_id: int | None = None
    topic: str | None = None


class KnowledgeRetrieveRequest(BaseModel):
    query: str
    scope: str = "global"
    user_id: int | None = None
    topic: str | None = None
    top_k: int = 3


class KnowledgeChunkResponse(BaseModel):
    chunk_id: str
    source_type: str
    text: str
    score: float
    lexical_score: float | None = None
    bm25_score: float | None = None
    vector_score: float | None = None
    rrf_score: float | None = None
    rrf_bm25: float | None = None
    rrf_dense: float | None = None
    hybrid_score: float | None = None
    rerank_score: float | None = None
    topic: str | None = None
    title: str | None = None
    source_uri: str | None = None
    chapter: str | None = None
    page_no: int | None = None
    image_id: str | None = None
    scope: str = "global"
    user_id: int | None = None


class KnowledgeRetrieveResponse(BaseModel):
    query: str
    total: int
    items: list[KnowledgeChunkResponse]

