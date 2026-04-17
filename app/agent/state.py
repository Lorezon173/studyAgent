from typing import TypedDict, List, Optional


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

    # 新增：讲解循环控制
    explain_loop_count: int

    # 新增：知识检索
    retrieved_context: str

    # 新增：降级标记
    fallback_used: bool
    node_error: str
