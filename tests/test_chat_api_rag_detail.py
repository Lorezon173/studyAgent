"""Verify chat API exposes rag_detail when RAG ran."""
from app.models.schemas import RagExecutionDetailModel


def _fake_meta():
    from app.services.rag_coordinator import RAGExecutionMeta
    return RAGExecutionMeta(
        reason="tool_retrieval",
        used_tools=["search_local_textbook"],
        hit_count=2,
        fallback_used=False,
        query_mode="fact",
        query_reason="test",
        candidates=[
            {"chunk_id": "c1", "score": 0.9, "tool": "search_local_textbook"},
            {"chunk_id": "c2", "score": 0.5, "tool": "search_local_textbook"},
        ],
        selected_chunk_ids=["c1", "c2"],
        elapsed_ms=42,
        reranked=False,
    )


def test_rag_execution_detail_model_serializes_meta():
    meta = _fake_meta()
    detail = RagExecutionDetailModel(
        query_mode=meta.query_mode,
        used_tools=meta.used_tools,
        hit_count=meta.hit_count,
        elapsed_ms=meta.elapsed_ms,
        reranked=meta.reranked,
        candidates=[{"chunk_id": c["chunk_id"], "score": c["score"], "tool": c["tool"]}
                    for c in meta.candidates],
        selected_chunk_ids=meta.selected_chunk_ids,
    )
    payload = detail.model_dump()
    assert payload["query_mode"] == "fact"
    assert payload["elapsed_ms"] == 42
    assert payload["reranked"] is False
    assert len(payload["candidates"]) == 2
    assert payload["candidates"][0]["chunk_id"] == "c1"
    assert payload["selected_chunk_ids"] == ["c1", "c2"]


def test_chat_response_field_optional():
    """ChatResponse accepts rag_detail=None and defaults to None."""
    from app.models import schemas
    response_cls = getattr(schemas, "ChatResponse", None)
    assert response_cls is not None, "ChatResponse model is expected to exist"
    instance = response_cls(
        session_id="s1",
        stage="start",
        reply="hi",
    )
    assert getattr(instance, "rag_detail", "missing") is None
    # Explicit None also accepted
    instance2 = response_cls(
        session_id="s1",
        stage="start",
        reply="hi",
        rag_detail=None,
    )
    assert instance2.rag_detail is None


def test_chat_response_accepts_rag_detail_payload():
    from app.models import schemas
    meta = _fake_meta()
    detail = RagExecutionDetailModel(
        query_mode=meta.query_mode,
        used_tools=meta.used_tools,
        hit_count=meta.hit_count,
        elapsed_ms=meta.elapsed_ms,
        reranked=meta.reranked,
        candidates=[{"chunk_id": c["chunk_id"], "score": c["score"], "tool": c["tool"]}
                    for c in meta.candidates],
        selected_chunk_ids=meta.selected_chunk_ids,
    )
    instance = schemas.ChatResponse(
        session_id="s1",
        stage="rag_answered",
        reply="ok",
        rag_detail=detail,
    )
    dumped = instance.model_dump()
    assert dumped["rag_detail"]["query_mode"] == "fact"
    assert dumped["rag_detail"]["candidates"][1]["chunk_id"] == "c2"
