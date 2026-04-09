from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterator

import httpx


class BackendApiError(RuntimeError):
    pass


@dataclass(frozen=True)
class BackendClient:
    base_url: str
    timeout: float = 30.0

    def _client(self) -> httpx.Client:
        return httpx.Client(base_url=self.base_url, timeout=self.timeout)

    def register(self, username: str, password: str) -> dict[str, Any]:
        with self._client() as client:
            resp = client.post("/auth/register", json={"username": username, "password": password})
        return self._json_or_raise(resp)

    def login(self, username: str, password: str) -> dict[str, Any]:
        with self._client() as client:
            resp = client.post("/auth/login", json={"username": username, "password": password})
        return self._json_or_raise(resp)

    def list_skills(self) -> dict[str, Any]:
        with self._client() as client:
            resp = client.get("/skills")
        return self._json_or_raise(resp)

    def list_sessions(self) -> dict[str, Any]:
        with self._client() as client:
            resp = client.get("/sessions")
        return self._json_or_raise(resp)

    def clear_session(self, session_id: str) -> dict[str, Any]:
        with self._client() as client:
            resp = client.delete(f"/sessions/{session_id}")
        return self._json_or_raise(resp)

    def clear_all_sessions(self) -> dict[str, Any]:
        with self._client() as client:
            resp = client.delete("/sessions")
        return self._json_or_raise(resp)

    def get_profile(self, session_id: str, user_id: int | None) -> dict[str, Any]:
        params = {"user_id": user_id} if user_id is not None else None
        with self._client() as client:
            resp = client.get(f"/profile/{session_id}", params=params)
        return self._json_or_raise(resp)

    def get_topic_memory(self, topic: str, user_id: int | None) -> dict[str, Any]:
        params = {"user_id": user_id} if user_id is not None else None
        with self._client() as client:
            resp = client.get(f"/profile/topic/{topic}/memory", params=params)
        return self._json_or_raise(resp)

    def knowledge_ingest(
        self,
        *,
        source_type: str,
        content: str,
        topic: str | None,
        scope: str = "global",
        user_id: int | None = None,
        title: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "source_type": source_type,
            "content": content,
            "scope": scope,
            "topic": topic,
            "user_id": user_id,
            "title": title,
        }
        with self._client() as client:
            resp = client.post("/knowledge/ingest", json=payload)
        return self._json_or_raise(resp)

    def knowledge_retrieve(
        self,
        *,
        query: str,
        topic: str | None,
        scope: str = "global",
        user_id: int | None = None,
        top_k: int = 3,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "query": query,
            "topic": topic,
            "scope": scope,
            "user_id": user_id,
            "top_k": top_k,
        }
        with self._client() as client:
            resp = client.post("/knowledge/retrieve", json=payload)
        return self._json_or_raise(resp)

    def chat_stream(
        self,
        *,
        session_id: str,
        user_input: str,
        user_id: int | None,
        topic: str | None = None,
    ) -> Iterator[tuple[str, str]]:
        payload: dict[str, Any] = {
            "session_id": session_id,
            "user_input": user_input,
            "user_id": user_id,
            "topic": topic,
        }
        with self._client() as client:
            with client.stream("POST", "/chat/stream", json=payload) as resp:
                self._ensure_ok(resp)
                event: str | None = None
                for line in resp.iter_lines():
                    if not line:
                        continue
                    if line.startswith("event:"):
                        event = line.split(":", 1)[1].strip()
                        continue
                    if line.startswith("data:"):
                        data = line.split(":", 1)[1].strip()
                        if event is None:
                            event = "message"
                        yield event, data
                        event = None

    def chat(
        self,
        *,
        session_id: str,
        user_input: str,
        user_id: int | None,
        topic: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "session_id": session_id,
            "user_input": user_input,
            "user_id": user_id,
            "topic": topic,
        }
        with self._client() as client:
            resp = client.post("/chat", json=payload)
        return self._json_or_raise(resp)

    def _json_or_raise(self, resp: httpx.Response) -> dict[str, Any]:
        self._ensure_ok(resp)
        try:
            body = resp.json()
        except ValueError as exc:
            raise BackendApiError("后端响应不是有效 JSON") from exc
        if not isinstance(body, dict):
            raise BackendApiError("后端响应 JSON 结构不符合预期")
        return body

    def _ensure_ok(self, resp: httpx.Response) -> None:
        if resp.status_code < 400:
            return
        detail = ""
        try:
            data = resp.json()
            if isinstance(data, dict):
                detail = str(data.get("detail", data))
            else:
                detail = str(data)
        except ValueError:
            detail = resp.text
        raise BackendApiError(f"后端请求失败 {resp.status_code}: {detail}")
