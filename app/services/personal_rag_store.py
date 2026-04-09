import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core.config import settings

_MEMORY_PERSONAL_RAG: list[dict[str, Any]] = []


def _store_path() -> Path:
    return Path(settings.personal_rag_store_path)


def _tokenize(text: str) -> set[str]:
    cleaned = re.sub(r"[^0-9a-zA-Z\u4e00-\u9fa5]+", " ", text.lower())
    return {x for x in cleaned.split() if len(x) >= 2}


def append_personal_memory(
    *,
    user_id: int | None,
    session_id: str,
    topic: str | None,
    content: str,
    source: str,
    score: int | None,
    level: str | None,
    created_at: str | None = None,
) -> None:
    if not topic or not content.strip():
        return
    now = created_at or datetime.now(UTC).isoformat()
    item = {
        "user_id": user_id,
        "session_id": session_id,
        "topic": topic,
        "content": content.strip(),
        "source": source,
        "score": score,
        "level": level,
        "created_at": now,
    }
    _MEMORY_PERSONAL_RAG.append(item)

    path = _store_path()
    if not path.parent.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(item, ensure_ascii=False) + "\n")


def _iter_disk_items() -> list[dict[str, Any]]:
    path = _store_path()
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text:
            continue
        try:
            data = json.loads(text)
            if isinstance(data, dict):
                rows.append(data)
        except json.JSONDecodeError:
            continue
    return rows


def retrieve_personal_memory(
    topic: str,
    query: str,
    limit: int = 3,
    user_id: int | None = None,
) -> list[dict[str, Any]]:
    q_tokens = _tokenize(query)
    if not q_tokens:
        return []
    candidates = [x for x in (_MEMORY_PERSONAL_RAG + _iter_disk_items()) if x.get("topic") == topic]
    if user_id is not None:
        candidates = [x for x in candidates if x.get("user_id") == user_id]
    scored: list[tuple[int, dict[str, Any]]] = []
    for item in candidates:
        content = str(item.get("content", ""))
        c_tokens = _tokenize(content)
        score = len(q_tokens & c_tokens)
        if score > 0:
            scored.append((score, item))
    scored.sort(key=lambda x: (x[0], x[1].get("created_at", "")), reverse=True)
    unique: list[dict[str, Any]] = []
    seen = set()
    for _, item in scored:
        key = (item.get("session_id"), item.get("content"), item.get("created_at"))
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
        if len(unique) >= limit:
            break
    return unique
