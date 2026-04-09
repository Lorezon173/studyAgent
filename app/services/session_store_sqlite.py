import json
import sqlite3
from pathlib import Path
from typing import Dict

from app.agent.state import LearningState
from app.core.config import settings


class SQLiteSessionStore:
    def __init__(self, db_path: str) -> None:
        self.db_path = Path(db_path)
        if not self.db_path.parent.exists():
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_table()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA busy_timeout=3000;")
        return conn

    def _init_table(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL
                )
                """
            )
            conn.commit()

    def get_session(self, session_id: str) -> LearningState | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload FROM sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        if row is None:
            return None
        return json.loads(row[0])

    def save_session(self, session_id: str, state: LearningState) -> None:
        payload = json.dumps(state, ensure_ascii=False)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO sessions (session_id, payload)
                VALUES (?, ?)
                ON CONFLICT(session_id) DO UPDATE SET payload = excluded.payload
                """,
                (session_id, payload),
            )
            conn.commit()

    def clear_session(self, session_id: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
            conn.commit()

    def list_sessions(self) -> Dict[str, LearningState]:
        with self._connect() as conn:
            rows = conn.execute("SELECT session_id, payload FROM sessions").fetchall()
        return {session_id: json.loads(payload) for session_id, payload in rows}

    def clear_all_sessions(self) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM sessions")
            conn.commit()

_SQLITE_STORES: dict[str, SQLiteSessionStore] = {}


def get_sqlite_session_store() -> SQLiteSessionStore:
    path = settings.session_sqlite_path
    store = _SQLITE_STORES.get(path)
    if store is None:
        store = SQLiteSessionStore(path)
        _SQLITE_STORES[path] = store
    return store
