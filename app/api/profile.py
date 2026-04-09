from fastapi import APIRouter, HTTPException, Query

from app.models.schemas import (
    ErrorPatternItem,
    ErrorPatternListResponse,
    LearningProfileResponse,
    MasteryProfileResponse,
    ProfileOverviewResponse,
    ReviewPlanResponse,
    SessionTimelineResponse,
    SessionSummaryResponse,
    TimelineEventResponse,
    TopicAggregateResponse,
    TopicLongTermMemoryResponse,
    TopicMemoryEntryResponse,
    TopicSessionItem,
)
from app.services.learning_profile_store import (
    aggregate_by_topic,
    build_session_timeline,
    get_learning_profile,
    get_mastery_profile,
    get_profile_overview,
    get_topic_long_term_memory,
    get_review_plan,
    get_session_summary,
    list_error_patterns,
)

router = APIRouter(prefix="/profile", tags=["profile"])


@router.get("/overview", response_model=ProfileOverviewResponse)
def get_overview() -> ProfileOverviewResponse:
    return ProfileOverviewResponse(**get_profile_overview())


@router.get("/topic/{topic}/memory", response_model=TopicLongTermMemoryResponse)
def get_topic_memory(topic: str, user_id: int | None = Query(default=None)) -> TopicLongTermMemoryResponse:
    data = get_topic_long_term_memory(topic, user_id=user_id)
    return TopicLongTermMemoryResponse(
        topic=data["topic"],
        mastery_trend=data["mastery_trend"],
        common_errors=data["common_errors"],
        review_history=data["review_history"],
        last_stuck_point=data["last_stuck_point"],
        memory_entries=[TopicMemoryEntryResponse(**x) for x in data["memory_entries"]],
    )


@router.get("/topic/{topic}", response_model=TopicAggregateResponse)
def get_topic_aggregate(topic: str, user_id: int | None = Query(default=None)) -> TopicAggregateResponse:
    data = aggregate_by_topic(topic, user_id=user_id)
    return TopicAggregateResponse(
        topic=data["topic"],
        total_sessions=data["total_sessions"],
        avg_score=data["avg_score"],
        sessions=[TopicSessionItem(**x) for x in data["sessions"]],
    )


@router.get("/session/{session_id}/timeline", response_model=SessionTimelineResponse)
def get_session_timeline(
    session_id: str,
    user_id: int | None = Query(default=None),
) -> SessionTimelineResponse:
    events = [TimelineEventResponse(**x) for x in build_session_timeline(session_id, user_id=user_id)]
    if not events:
        raise HTTPException(status_code=404, detail=f"未找到学习时间线：{session_id}")
    return SessionTimelineResponse(session_id=session_id, events=events)


@router.get("/{session_id}/summary", response_model=SessionSummaryResponse)
def get_summary(session_id: str, user_id: int | None = Query(default=None)) -> SessionSummaryResponse:
    data = get_session_summary(session_id, user_id=user_id)
    if data is None:
        raise HTTPException(status_code=404, detail=f"未找到会话总结：{session_id}")
    return SessionSummaryResponse(session_id=session_id, **data)


@router.get("/{session_id}/mastery", response_model=MasteryProfileResponse)
def get_mastery(session_id: str, user_id: int | None = Query(default=None)) -> MasteryProfileResponse:
    data = get_mastery_profile(session_id, user_id=user_id)
    if data is None:
        raise HTTPException(status_code=404, detail=f"未找到掌握度档案：{session_id}")
    return MasteryProfileResponse(session_id=session_id, **data)


@router.get("/{session_id}/errors", response_model=ErrorPatternListResponse)
def get_errors(session_id: str, user_id: int | None = Query(default=None)) -> ErrorPatternListResponse:
    items = [ErrorPatternItem(**x) for x in list_error_patterns(session_id, user_id=user_id)]
    if not items:
        raise HTTPException(status_code=404, detail=f"未找到错因记录：{session_id}")
    return ErrorPatternListResponse(session_id=session_id, items=items)


@router.get("/{session_id}/review-plan", response_model=ReviewPlanResponse)
def get_plan(session_id: str, user_id: int | None = Query(default=None)) -> ReviewPlanResponse:
    data = get_review_plan(session_id, user_id=user_id)
    if data is None:
        raise HTTPException(status_code=404, detail=f"未找到复习计划：{session_id}")
    return ReviewPlanResponse(session_id=session_id, **data)


@router.get("/{session_id}", response_model=LearningProfileResponse)
def get_profile(session_id: str, user_id: int | None = Query(default=None)) -> LearningProfileResponse:
    data = get_learning_profile(session_id, user_id=user_id)
    if not any(data.values()):
        raise HTTPException(status_code=404, detail=f"未找到学习档案：{session_id}")

    summary = data["session_summary"]
    mastery = data["mastery_profile"]
    errors = data["error_patterns"]
    plan = data["review_plan"]

    return LearningProfileResponse(
        session_id=session_id,
        session_summary=SessionSummaryResponse(session_id=session_id, **summary) if summary else None,
        mastery_profile=MasteryProfileResponse(session_id=session_id, **mastery) if mastery else None,
        error_patterns=ErrorPatternListResponse(
            session_id=session_id,
            items=[ErrorPatternItem(**x) for x in errors],
        )
        if errors
        else None,
        review_plan=ReviewPlanResponse(session_id=session_id, **plan) if plan else None,
    )


