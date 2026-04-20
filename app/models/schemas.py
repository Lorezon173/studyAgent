from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    session_id: str = Field(..., description="学习会话 ID")
    user_input: str = Field(..., description="用户当前输入")
    topic: str | None = Field(default=None, description="学习主题")
    user_id: int | None = Field(default=None, description="数字用户ID（用于个人记忆隔离）")


class ChatResponse(BaseModel):
    session_id: str
    stage: str
    reply: str
    summary: str | None = None
    citations: list[dict] = Field(default_factory=list)
    rag_confidence_level: str | None = None
    rag_low_evidence: bool | None = None


class SessionStateResponse(BaseModel):
    session_id: str
    stage: str
    topic: str | None = None
    history: list[str] = Field(default_factory=list)
    topic_segments: list[dict] = Field(default_factory=list)


class SessionListResponse(BaseModel):
    sessions: list[SessionStateResponse]
    total: int


class SessionClearResponse(BaseModel):
    message: str
    session_id: str | None = None


class SkillResponse(BaseModel):
    name: str
    description: str


class SkillListResponse(BaseModel):
    skills: list[SkillResponse]
    total: int


class SessionSummaryResponse(BaseModel):
    session_id: str
    topic: str | None = None
    summary: str
    created_at: str


class MasteryProfileResponse(BaseModel):
    session_id: str
    topic: str | None = None
    score: int
    level: str
    rationale: str
    updated_at: str


class ErrorPatternItem(BaseModel):
    label: str
    detail: str
    created_at: str


class ErrorPatternListResponse(BaseModel):
    session_id: str
    items: list[ErrorPatternItem]


class ReviewPlanResponse(BaseModel):
    session_id: str
    topic: str | None = None
    next_review_at: str
    suggestions: list[str]
    created_at: str


class LearningProfileResponse(BaseModel):
    session_id: str
    session_summary: SessionSummaryResponse | None = None
    mastery_profile: MasteryProfileResponse | None = None
    error_patterns: ErrorPatternListResponse | None = None
    review_plan: ReviewPlanResponse | None = None


class TopicSessionItem(BaseModel):
    session_id: str
    score: int | None = None
    level: str | None = None
    next_review_at: str | None = None
    summary_created_at: str | None = None


class TopicAggregateResponse(BaseModel):
    topic: str
    total_sessions: int
    avg_score: float | None = None
    sessions: list[TopicSessionItem]


class TimelineEventResponse(BaseModel):
    event_type: str
    timestamp: str
    detail: str


class SessionTimelineResponse(BaseModel):
    session_id: str
    events: list[TimelineEventResponse]


class ProfileOverviewResponse(BaseModel):
    total_profiles: int
    total_topics: int
    mastery_level_distribution: dict[str, int]
    sessions_with_review_plan: int


class TopicMemoryEntryResponse(BaseModel):
    session_id: str
    topic: str
    entry_type: str
    content: str
    score: int | None = None
    level: str | None = None
    created_at: str


class TopicLongTermMemoryResponse(BaseModel):
    topic: str
    mastery_trend: list[dict]
    common_errors: list[dict]
    review_history: list[dict]
    last_stuck_point: str
    memory_entries: list[TopicMemoryEntryResponse]


class AuthRegisterRequest(BaseModel):
    username: str = Field(..., description="用户名")
    password: str = Field(..., description="登录密码")


class AuthLoginRequest(BaseModel):
    username: str = Field(..., description="用户名")
    password: str = Field(..., description="登录密码")


class AuthUserResponse(BaseModel):
    user_id: int
    username: str


class AuthUserListResponse(BaseModel):
    users: list[AuthUserResponse]
    total: int
