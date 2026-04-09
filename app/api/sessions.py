from fastapi import APIRouter, HTTPException

from app.models.schemas import SessionClearResponse, SessionListResponse, SessionStateResponse
from app.services.session_store import (
    clear_all_sessions,
    clear_session,
    get_session,
    list_sessions,
)

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.get("", response_model=SessionListResponse)
def get_sessions() -> SessionListResponse:
    data = list_sessions()
    items = [
        SessionStateResponse(
            session_id=session_id,
            stage=state.get("stage", "unknown"),
            topic=state.get("topic"),
            history=state.get("history", []),
            topic_segments=state.get("topic_segments", []),
        )
        for session_id, state in data.items()
    ]
    return SessionListResponse(sessions=items, total=len(items))


@router.get("/{session_id}", response_model=SessionStateResponse)
def get_session_detail(session_id: str) -> SessionStateResponse:
    state = get_session(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"未找到会话：{session_id}")
    return SessionStateResponse(
        session_id=session_id,
        stage=state.get("stage", "unknown"),
        topic=state.get("topic"),
        history=state.get("history", []),
        topic_segments=state.get("topic_segments", []),
    )


@router.delete("/{session_id}", response_model=SessionClearResponse)
def delete_session(session_id: str) -> SessionClearResponse:
    state = get_session(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"未找到会话：{session_id}")
    clear_session(session_id)
    return SessionClearResponse(message="会话已清理", session_id=session_id)


@router.delete("", response_model=SessionClearResponse)
def delete_all_sessions() -> SessionClearResponse:
    clear_all_sessions()
    return SessionClearResponse(message="所有会话已清理")
