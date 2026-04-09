from typing import Any, Protocol

from app.services.rag_store import retrieve_knowledge, retrieve_knowledge_by_scope


class Retriever(Protocol):
    def retrieve(self, *, query: str, topic: str | None, top_k: int) -> list[dict[str, Any]]:
        ...

    def retrieve_scoped(
        self,
        *,
        query: str,
        scope: str,
        user_id: str | None,
        topic: str | None,
        top_k: int,
    ) -> list[dict[str, Any]]:
        ...


class JsonlRagRetriever:
    """基于本地 JSONL+内存实现的默认 Retriever。"""

    def retrieve(self, *, query: str, topic: str | None, top_k: int) -> list[dict[str, Any]]:
        return retrieve_knowledge(query=query, topic=topic, top_k=top_k)

    def retrieve_scoped(
        self,
        *,
        query: str,
        scope: str,
        user_id: str | None,
        topic: str | None,
        top_k: int,
    ) -> list[dict[str, Any]]:
        return retrieve_knowledge_by_scope(
            query=query,
            topic=topic,
            top_k=top_k,
            scope=scope,
            user_id=user_id,
        )

