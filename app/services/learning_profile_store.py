import json
import sqlite3
from pathlib import Path
from typing import Any

from app.core.config import settings

# memory 后端下的学习档案存储
_MEMORY_SESSION_SUMMARIES: dict[str, dict[str, Any]] = {}
_MEMORY_MASTERY_PROFILES: dict[str, dict[str, Any]] = {}
_MEMORY_ERROR_PATTERNS: dict[str, list[dict[str, Any]]] = {}
_MEMORY_REVIEW_PLANS: dict[str, dict[str, Any]] = {}
_MEMORY_TOPIC_MEMORY_ENTRIES: list[dict[str, Any]] = []


def _use_sqlite() -> bool:
    return settings.session_store_backend.lower() == "sqlite"


class LearningProfileSQLiteStore:
    def __init__(self, db_path: str) -> None:
        self.db_path = Path(db_path)
        if not self.db_path.parent.exists():
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_tables()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA busy_timeout=3000;")
        return conn

    def _init_tables(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS session_summaries (
                    session_id TEXT PRIMARY KEY,
                    topic TEXT,
                    summary TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS mastery_profiles (
                    session_id TEXT PRIMARY KEY,
                    topic TEXT,
                    score INTEGER NOT NULL,
                    level TEXT NOT NULL,
                    rationale TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS error_patterns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    topic TEXT,
                    label TEXT NOT NULL,
                    detail TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS review_plans (
                    session_id TEXT PRIMARY KEY,
                    topic TEXT,
                    next_review_at TEXT NOT NULL,
                    suggestions_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS topic_memory_entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    topic TEXT NOT NULL,
                    entry_type TEXT NOT NULL,
                    content TEXT NOT NULL,
                    score INTEGER,
                    level TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.commit()

    def save_session_summary(self, session_id: str, topic: str | None, summary: str, created_at: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO session_summaries(session_id, topic, summary, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    topic=excluded.topic,
                    summary=excluded.summary,
                    created_at=excluded.created_at
                """,
                (session_id, topic, summary, created_at),
            )
            conn.commit()

    def get_session_summary(self, session_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT topic, summary, created_at FROM session_summaries WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        if row is None:
            return None
        return {"topic": row[0], "summary": row[1], "created_at": row[2]}

    def upsert_mastery_profile(
        self,
        session_id: str,
        topic: str | None,
        score: int,
        level: str,
        rationale: str,
        updated_at: str,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO mastery_profiles(session_id, topic, score, level, rationale, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    topic=excluded.topic,
                    score=excluded.score,
                    level=excluded.level,
                    rationale=excluded.rationale,
                    updated_at=excluded.updated_at
                """,
                (session_id, topic, score, level, rationale, updated_at),
            )
            conn.commit()

    def get_mastery_profile(self, session_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT topic, score, level, rationale, updated_at FROM mastery_profiles WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        if row is None:
            return None
        return {
            "topic": row[0],
            "score": row[1],
            "level": row[2],
            "rationale": row[3],
            "updated_at": row[4],
        }

    def replace_error_patterns(
        self,
        session_id: str,
        topic: str | None,
        labels: list[str],
        detail: str,
        created_at: str,
    ) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM error_patterns WHERE session_id = ?", (session_id,))
            for label in labels:
                conn.execute(
                    """
                    INSERT INTO error_patterns(session_id, topic, label, detail, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (session_id, topic, label, detail, created_at),
                )
            conn.commit()

    def list_error_patterns(self, session_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT label, detail, created_at FROM error_patterns WHERE session_id = ?",
                (session_id,),
            ).fetchall()
        return [{"label": label, "detail": detail, "created_at": created_at} for label, detail, created_at in rows]

    def upsert_review_plan(
        self,
        session_id: str,
        topic: str | None,
        next_review_at: str,
        suggestions: list[str],
        created_at: str,
    ) -> None:
        payload = json.dumps(suggestions, ensure_ascii=False)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO review_plans(session_id, topic, next_review_at, suggestions_json, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    topic=excluded.topic,
                    next_review_at=excluded.next_review_at,
                    suggestions_json=excluded.suggestions_json,
                    created_at=excluded.created_at
                """,
                (session_id, topic, next_review_at, payload, created_at),
            )
            conn.commit()

    def get_review_plan(self, session_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT topic, next_review_at, suggestions_json, created_at FROM review_plans WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        if row is None:
            return None
        return {
            "topic": row[0],
            "next_review_at": row[1],
            "suggestions": json.loads(row[2]),
            "created_at": row[3],
        }

    def append_topic_memory_entry(
        self,
        session_id: str,
        topic: str,
        entry_type: str,
        content: str,
        score: int | None,
        level: str | None,
        created_at: str,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO topic_memory_entries(
                    session_id, topic, entry_type, content, score, level, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (session_id, topic, entry_type, content, score, level, created_at),
            )
            conn.commit()

    def list_topic_memory_entries(self, topic: str, limit: int = 10) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT session_id, topic, entry_type, content, score, level, created_at
                FROM topic_memory_entries
                WHERE topic = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (topic, limit),
            ).fetchall()
        return [
            {
                "session_id": row[0],
                "topic": row[1],
                "entry_type": row[2],
                "content": row[3],
                "score": row[4],
                "level": row[5],
                "created_at": row[6],
            }
            for row in rows
        ]


_SQLITE_LEARNING_PROFILE_STORES: dict[str, LearningProfileSQLiteStore] = {}


def _get_sqlite_store() -> LearningProfileSQLiteStore:
    path = settings.session_sqlite_path
    store = _SQLITE_LEARNING_PROFILE_STORES.get(path)
    if store is None:
        store = LearningProfileSQLiteStore(path)
        _SQLITE_LEARNING_PROFILE_STORES[path] = store
    return store


def _make_session_key(session_id: str, user_id: int | None) -> str:
    if user_id is not None and session_id.startswith(f"{user_id}:"):
        return session_id
    return f"{user_id}:{session_id}" if user_id is not None else session_id


def _display_session_id(session_id: str, user_id: int | None) -> str:
    if user_id is None:
        return session_id
    prefix = f"{user_id}:"
    if session_id.startswith(prefix):
        return session_id[len(prefix) :]
    return session_id


def save_session_summary(
    session_id: str,
    topic: str | None,
    summary: str,
    created_at: str,
    user_id: int | None = None,
) -> None:
    key = _make_session_key(session_id, user_id)
    if _use_sqlite():
        _get_sqlite_store().save_session_summary(key, topic, summary, created_at)
        return
    _MEMORY_SESSION_SUMMARIES[key] = {"topic": topic, "summary": summary, "created_at": created_at, "user_id": user_id}


def get_session_summary(session_id: str, user_id: int | None = None) -> dict[str, Any] | None:
    key = _make_session_key(session_id, user_id)
    if _use_sqlite():
        return _get_sqlite_store().get_session_summary(key)
    return _MEMORY_SESSION_SUMMARIES.get(key)


def upsert_mastery_profile(
    session_id: str,
    topic: str | None,
    score: int,
    level: str,
    rationale: str,
    updated_at: str,
    user_id: int | None = None,
) -> None:
    key = _make_session_key(session_id, user_id)
    if _use_sqlite():
        _get_sqlite_store().upsert_mastery_profile(key, topic, score, level, rationale, updated_at)
        return
    _MEMORY_MASTERY_PROFILES[key] = {
        "topic": topic,
        "score": score,
        "level": level,
        "rationale": rationale,
        "updated_at": updated_at,
        "user_id": user_id,
    }


def get_mastery_profile(session_id: str, user_id: int | None = None) -> dict[str, Any] | None:
    key = _make_session_key(session_id, user_id)
    if _use_sqlite():
        return _get_sqlite_store().get_mastery_profile(key)
    return _MEMORY_MASTERY_PROFILES.get(key)


def replace_error_patterns(
    session_id: str,
    topic: str | None,
    labels: list[str],
    detail: str,
    created_at: str,
    user_id: int | None = None,
) -> None:
    key = _make_session_key(session_id, user_id)
    if _use_sqlite():
        _get_sqlite_store().replace_error_patterns(key, topic, labels, detail, created_at)
        return
    _MEMORY_ERROR_PATTERNS[key] = [
        {"label": label, "detail": detail, "created_at": created_at} for label in labels
    ]


def list_error_patterns(session_id: str, user_id: int | None = None) -> list[dict[str, Any]]:
    key = _make_session_key(session_id, user_id)
    if _use_sqlite():
        return _get_sqlite_store().list_error_patterns(key)
    return _MEMORY_ERROR_PATTERNS.get(key, [])


def upsert_review_plan(
    session_id: str,
    topic: str | None,
    next_review_at: str,
    suggestions: list[str],
    created_at: str,
    user_id: int | None = None,
) -> None:
    key = _make_session_key(session_id, user_id)
    if _use_sqlite():
        _get_sqlite_store().upsert_review_plan(key, topic, next_review_at, suggestions, created_at)
        return
    _MEMORY_REVIEW_PLANS[key] = {
        "topic": topic,
        "next_review_at": next_review_at,
        "suggestions": suggestions,
        "created_at": created_at,
        "user_id": user_id,
    }


def get_review_plan(session_id: str, user_id: int | None = None) -> dict[str, Any] | None:
    key = _make_session_key(session_id, user_id)
    if _use_sqlite():
        return _get_sqlite_store().get_review_plan(key)
    return _MEMORY_REVIEW_PLANS.get(key)


def append_topic_memory_entry(
    session_id: str,
    topic: str | None,
    entry_type: str,
    content: str,
    score: int | None,
    level: str | None,
    created_at: str,
    user_id: int | None = None,
) -> None:
    if not topic:
        return
    if _use_sqlite():
        _get_sqlite_store().append_topic_memory_entry(
            session_id=session_id,
            topic=topic,
            entry_type=entry_type,
            content=content,
            score=score,
            level=level,
            created_at=created_at,
        )
        return
    _MEMORY_TOPIC_MEMORY_ENTRIES.append(
        {
            "session_id": session_id,
            "topic": topic,
            "entry_type": entry_type,
            "content": content,
            "score": score,
            "level": level,
            "created_at": created_at,
            "user_id": user_id,
        }
    )


def list_topic_memory_entries(topic: str, limit: int = 10, user_id: int | None = None) -> list[dict[str, Any]]:
    if _use_sqlite():
        rows = _get_sqlite_store().list_topic_memory_entries(topic, limit * 5 if user_id is not None else limit)
        if user_id is not None:
            rows = [x for x in rows if str(x.get("session_id", "")).startswith(f"{user_id}:")]
        return rows[:limit]
    rows = [x for x in _MEMORY_TOPIC_MEMORY_ENTRIES if x.get("topic") == topic]
    if user_id is not None:
        rows = [x for x in rows if x.get("user_id") == user_id]
    rows.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return rows[:limit]


def get_learning_profile(session_id: str, user_id: int | None = None) -> dict[str, Any]:
    return {
        "session_summary": get_session_summary(session_id, user_id=user_id),
        "mastery_profile": get_mastery_profile(session_id, user_id=user_id),
        "error_patterns": list_error_patterns(session_id, user_id=user_id),
        "review_plan": get_review_plan(session_id, user_id=user_id),
    }


def _collect_session_ids_memory() -> list[str]:
    keys = set(_MEMORY_SESSION_SUMMARIES.keys())
    keys.update(_MEMORY_MASTERY_PROFILES.keys())
    keys.update(_MEMORY_ERROR_PATTERNS.keys())
    keys.update(_MEMORY_REVIEW_PLANS.keys())
    return sorted(keys)


def _collect_session_ids_sqlite() -> list[str]:
    store = _get_sqlite_store()
    with store._connect() as conn:  # noqa: SLF001
        rows = conn.execute(
            """
            SELECT session_id FROM session_summaries
            UNION
            SELECT session_id FROM mastery_profiles
            UNION
            SELECT session_id FROM error_patterns
            UNION
            SELECT session_id FROM review_plans
            """
        ).fetchall()
    return sorted([x[0] for x in rows])


def list_session_ids() -> list[str]:
    if _use_sqlite():
        return _collect_session_ids_sqlite()
    return _collect_session_ids_memory()


def aggregate_by_topic(topic: str, user_id: int | None = None) -> dict[str, Any]:
    session_ids = list_session_ids()
    if user_id is not None:
        prefix = f"{user_id}:"
        session_ids = [sid for sid in session_ids if sid.startswith(prefix)]
    items: list[dict[str, Any]] = []
    scores: list[int] = []
    for sid in session_ids:
        summary = get_session_summary(sid, user_id=user_id)
        mastery = get_mastery_profile(sid, user_id=user_id)
        review = get_review_plan(sid, user_id=user_id)
        actual_topic = (
            (summary or {}).get("topic")
            or (mastery or {}).get("topic")
            or (review or {}).get("topic")
        )
        if actual_topic != topic:
            continue

        score = (mastery or {}).get("score")
        if isinstance(score, int):
            scores.append(score)

        items.append(
            {
                "session_id": _display_session_id(sid, user_id),
                "score": (mastery or {}).get("score"),
                "level": (mastery or {}).get("level"),
                "next_review_at": (review or {}).get("next_review_at"),
                "summary_created_at": (summary or {}).get("created_at"),
            }
        )

    avg_score = round(sum(scores) / len(scores), 2) if scores else None
    return {"topic": topic, "total_sessions": len(items), "avg_score": avg_score, "sessions": items}


def build_session_timeline(session_id: str, user_id: int | None = None) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    key = _make_session_key(session_id, user_id)
    summary = get_session_summary(key, user_id=None)
    mastery = get_mastery_profile(key, user_id=None)
    errors = list_error_patterns(key, user_id=None)
    review = get_review_plan(key, user_id=None)

    if summary:
        events.append(
            {
                "event_type": "summary_generated",
                "timestamp": summary["created_at"],
                "detail": "会话总结已生成",
            }
        )
    if mastery:
        events.append(
            {
                "event_type": "mastery_assessed",
                "timestamp": mastery["updated_at"],
                "detail": f"掌握度评分={mastery['score']}，等级={mastery['level']}",
            }
        )
    for item in errors:
        events.append(
            {
                "event_type": "error_pattern_recorded",
                "timestamp": item["created_at"],
                "detail": f"{item['label']}：{item['detail']}",
            }
        )
    if review:
        events.append(
            {
                "event_type": "review_plan_created",
                "timestamp": review["created_at"],
                "detail": f"下次复习时间：{review['next_review_at']}",
            }
        )

    events.sort(key=lambda x: x["timestamp"])
    return events


def get_profile_overview() -> dict[str, Any]:
    session_ids = list_session_ids()
    topics: set[str] = set()
    level_dist: dict[str, int] = {"high": 0, "medium": 0, "low": 0}
    sessions_with_review_plan = 0

    for sid in session_ids:
        summary = get_session_summary(sid)
        mastery = get_mastery_profile(sid)
        review = get_review_plan(sid)

        topic = (
            (summary or {}).get("topic")
            or (mastery or {}).get("topic")
            or (review or {}).get("topic")
        )
        if topic:
            topics.add(topic)

        level = (mastery or {}).get("level")
        if level in level_dist:
            level_dist[level] += 1

        if review is not None:
            sessions_with_review_plan += 1

    return {
        "total_profiles": len(session_ids),
        "total_topics": len(topics),
        "mastery_level_distribution": level_dist,
        "sessions_with_review_plan": sessions_with_review_plan,
    }


def get_topic_long_term_memory(topic: str, user_id: int | None = None) -> dict[str, Any]:
    items = aggregate_by_topic(topic, user_id=user_id)["sessions"]
    trend = [
        {
            "session_id": it["session_id"],
            "score": it.get("score"),
            "level": it.get("level"),
            "timestamp": it.get("summary_created_at"),
        }
        for it in sorted(items, key=lambda x: x.get("summary_created_at") or "")
    ]

    error_counter: dict[str, int] = {}
    last_stuck_point = ""
    for sid_item in items:
        sid = sid_item["session_id"]
        errors = list_error_patterns(sid, user_id=user_id)
        for err in errors:
            label = err.get("label") or "未知问题"
            error_counter[label] = error_counter.get(label, 0) + 1
            if not last_stuck_point:
                last_stuck_point = f"{label}: {err.get('detail', '')[:120]}"

    common_errors = sorted(
        [{"label": k, "count": v} for k, v in error_counter.items()],
        key=lambda x: x["count"],
        reverse=True,
    )

    review_history = []
    for sid_item in items:
        sid = sid_item["session_id"]
        review = get_review_plan(sid, user_id=user_id)
        if review:
            review_history.append(
                {
                    "session_id": sid,
                    "next_review_at": review.get("next_review_at"),
                    "suggestions": review.get("suggestions", []),
                    "created_at": review.get("created_at"),
                }
            )

    memory_entries = list_topic_memory_entries(topic, limit=10, user_id=user_id)
    if not last_stuck_point and memory_entries:
        last_stuck_point = memory_entries[0].get("content", "")[:120]

    return {
        "topic": topic,
        "mastery_trend": trend,
        "common_errors": common_errors,
        "review_history": sorted(review_history, key=lambda x: x.get("created_at") or ""),
        "last_stuck_point": last_stuck_point,
        "memory_entries": memory_entries,
    }
