from typing import Dict

from app.agent.state import LearningState
from app.core.config import settings
from app.services.session_store_sqlite import get_sqlite_session_store

# 内存会话存储（v0.1 先用内存，后续可替换为数据库）
SESSION_STORE: Dict[str, LearningState] = {}


def _use_sqlite() -> bool:
    return settings.session_store_backend.lower() == "sqlite"


def get_session(session_id: str) -> LearningState | None:
    if _use_sqlite():
        return get_sqlite_session_store().get_session(session_id)
    return SESSION_STORE.get(session_id)


def save_session(session_id: str, state: LearningState) -> None:
    if _use_sqlite():
        get_sqlite_session_store().save_session(session_id, state)
        return
    SESSION_STORE[session_id] = state


def clear_session(session_id: str) -> None:
    if _use_sqlite():
        get_sqlite_session_store().clear_session(session_id)
        return
    SESSION_STORE.pop(session_id, None)


def list_sessions() -> Dict[str, LearningState]:
    if _use_sqlite():
        return get_sqlite_session_store().list_sessions()
    return SESSION_STORE.copy()


def clear_all_sessions() -> None:
    if _use_sqlite():
        get_sqlite_session_store().clear_all_sessions()
        return
    SESSION_STORE.clear()
