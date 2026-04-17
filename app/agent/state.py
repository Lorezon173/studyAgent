from typing import TypedDict, List, Optional, Literal


IntentType = Literal["teach_loop", "qa_direct", "review", "replan"]
RAGScope = Literal["global", "personal", "both", "web", "none"]


class TopicSegment(TypedDict, total=False):
    topic: Optional[str]
    stage: str
    diagnosis: str
    explanation: str
    restatement_eval: str
    followup_question: str
    summary: str
    timestamp: str


class DecisionContractState(TypedDict):
    decision_id: str
    intent: IntentType
    intent_confidence: float
    reason: str
    need_rag: bool
    rag_scope: RAGScope
    tool_plan: List[str]
    fallback_policy: str


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
    intent: IntentType
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
    decision_id: str
    decision_contract: DecisionContractState
    decision_contract_fingerprint: str
    need_rag: bool
    rag_scope: RAGScope
    tool_plan: List[str]
    fallback_policy: str
