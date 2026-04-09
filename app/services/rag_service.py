from app.services.ocr_service import ocr_extract_text
from app.services.rag_store import ingest_knowledge
from app.services.retriever import JsonlRagRetriever, Retriever


class RAGService:
    def __init__(self, retriever: Retriever | None = None) -> None:
        self.retriever = retriever or JsonlRagRetriever()

    def ingest(
        self,
        *,
        source_type: str,
        scope: str,
        user_id: str | None,
        content: str,
        topic: str | None,
        title: str | None,
        source_uri: str | None,
        chapter: str | None,
        page_no: int | None,
        image_id: str | None,
        chunk_size: int | None,
        chunk_overlap: int | None,
    ) -> int:
        if source_type == "image":
            content = ocr_extract_text(content)
        return ingest_knowledge(
            source_type=source_type,
            scope=scope,
            user_id=user_id,
            content=content,
            topic=topic,
            title=title,
            source_uri=source_uri,
            chapter=chapter,
            page_no=page_no,
            image_id=image_id,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )

    def retrieve(self, *, query: str, topic: str | None, top_k: int) -> list[dict]:
        return self.retriever.retrieve(query=query, topic=topic, top_k=top_k)

    def retrieve_scoped(
        self,
        *,
        query: str,
        scope: str,
        user_id: str | None,
        topic: str | None,
        top_k: int,
    ) -> list[dict]:
        return self.retriever.retrieve_scoped(
            query=query,
            topic=topic,
            top_k=top_k,
            scope=scope,
            user_id=user_id,
        )


rag_service = RAGService()

