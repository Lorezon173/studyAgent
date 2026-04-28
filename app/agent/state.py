from typing import TypedDict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.rag_coordinator import RAGExecutionMeta
else:
    # Runtime stub so LangGraph 的 get_type_hints() 能解析前向引用，
    # 同时避免在 state.py 中引入真实运行时导入（防止潜在循环依赖）。
    RAGExecutionMeta = object


class TopicSegment(TypedDict, total=False):
    topic: Optional[str]
    stage: str
    diagnosis: str
    explanation: str
    restatement_eval: str
    followup_question: str
    summary: str
    timestamp: str


class LearningState(TypedDict, total=False):
    session_id: str
    user_id: Optional[int]
    stream_output: bool
    topic: Optional[str]
    user_input: str
    stage: str

    diagnosis: str
    explanation: str
    restatement_eval: str
    followup_question: str
    summary: str

    history: List[str]
    reply: str
    mastery_score: int
    mastery_level: str
    mastery_rationale: str
    error_labels: List[str]
    next_review_at: str
    intent: str
    intent_confidence: float
    current_plan: dict
    current_step_index: int
    need_replan: bool
    replan_reason: str
    branch_trace: List[dict]
    topic_confidence: float
    topic_changed: bool
    topic_reason: str
    comparison_mode: bool
    next_stage: str
    topic_segments: List[TopicSegment]
    topic_context: str
    citations: List[dict]
    tool_route: dict

    # 新增：历史记录检查
    has_history: bool
    history_summary: str
    history_mastery: str

    # 新增：用户选择
    user_choice: str
    waiting_for_choice: bool

    # 新增：RAG优先检索
    rag_context: str
    rag_citations: List[dict]
    rag_found: bool
    rag_confidence_level: str
    rag_low_evidence: bool
    rag_avg_score: float

    # 新增：讲解循环控制
    explain_loop_count: int

    # 新增：知识检索
    retrieved_context: str

    # 新增：降级标记
    fallback_used: bool
    node_error: str

    # 新增：检索策略（Phase 2）
    retrieval_strategy: dict          # 检索策略配置
    retrieval_mode: str               # 查询模式（fact/freshness/comparison）

    # 新增：证据守门（Phase 2）
    gate_status: str                   # pass / supplement / reject
    gate_coverage_score: float         # 覆盖度分数
    gate_missing_keywords: List[str]   # 缺失关键词

    # 新增：回答策略（Phase 2）
    answer_template_id: str            # 回答模板ID
    boundary_notice: str               # 边界声明文本

    # 新增：恢复策略（Phase 2）
    recovery_action: str               # 恢复动作
    fallback_triggered: bool           # 是否触发降级
    error_code: str                    # 错误码
    retry_trace: List[dict]            # 重试轨迹

    # 新增：RAG 执行明细（运行时 RAGExecutionMeta 实例）
    rag_meta_last: "Optional[RAGExecutionMeta]"   # Phase 3+ RAG 执行明细
