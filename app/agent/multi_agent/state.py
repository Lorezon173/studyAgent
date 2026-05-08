"""Multi-Agent 协作状态与类型定义。"""
from typing import TypedDict


class MultiAgentState(TypedDict, total=False):
    """Multi-Agent 协作共享状态。"""
    # 会话标识
    session_id: str
    user_id: int | None
    topic: str | None
    user_input: str

    # 协作控制
    current_agent: str               # orchestrator / teaching / eval / retrieval / aggregator
    task_queue: list[dict]           # 待执行任务
    completed_tasks: list[dict]      # 已完成任务

    # Agent 输出（命名空间隔离）
    teaching_output: dict            # TeachingOutput
    eval_output: dict                # EvalOutput
    retrieval_output: dict           # RetrievalOutput

    # 最终结果
    final_reply: str
    mastery_score: float | None

    # 追踪
    branch_trace: list[dict]


class RetrievalOutput(TypedDict, total=False):
    """Retrieval Agent 输出。"""
    citations: list[dict]
    rag_context: str
    rag_found: bool
    rag_confidence_level: str


class TeachingOutput(TypedDict, total=False):
    """Teaching Agent 输出。"""
    diagnosis: str
    explanation: str
    restatement_eval: str
    followup_question: str
    reply: str


class EvalOutput(TypedDict, total=False):
    """Eval Agent 输出。"""
    mastery_score: float             # 0-100
    mastery_level: str               # low / medium / high
    eval_feedback: str
    error_labels: list[str]
