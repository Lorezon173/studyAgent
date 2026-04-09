from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.rag.schemas import (
    KnowledgeChunkResponse,
    KnowledgeIngestRequest,
    KnowledgeIngestResponse,
    KnowledgeRetrieveRequest,
    KnowledgeRetrieveResponse,
)
from app.services.rag_service import rag_service
from app.services.file_extract_service import infer_source_type_from_filename, read_and_extract_upload

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


@router.post("/ingest", response_model=KnowledgeIngestResponse)
def ingest(req: KnowledgeIngestRequest) -> KnowledgeIngestResponse:
    try:
        inserted = rag_service.ingest(
            source_type=req.source_type,
            scope=req.scope,
            user_id=str(req.user_id) if req.user_id is not None else None,
            content=req.content,
            topic=req.topic,
            title=req.title,
            source_uri=req.source_uri,
            chapter=req.chapter,
            page_no=req.page_no,
            image_id=req.image_id,
            chunk_size=req.chunk_size,
            chunk_overlap=req.chunk_overlap,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return KnowledgeIngestResponse(
        inserted=inserted,
        source_type=req.source_type,
        scope=req.scope,
        user_id=req.user_id,
        topic=req.topic,
    )


@router.post("/retrieve", response_model=KnowledgeRetrieveResponse)
def retrieve(req: KnowledgeRetrieveRequest) -> KnowledgeRetrieveResponse:
    try:
        rows = rag_service.retrieve_scoped(
            query=req.query,
            scope=req.scope,
            user_id=str(req.user_id) if req.user_id is not None else None,
            topic=req.topic,
            top_k=req.top_k,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    items = [KnowledgeChunkResponse(**x) for x in rows]
    return KnowledgeRetrieveResponse(query=req.query, total=len(items), items=items)


@router.post("/ingest-file", response_model=KnowledgeIngestResponse)
async def ingest_file(
    file: UploadFile = File(...),
    source_type: str | None = Form(default=None),
    scope: str = Form(default="global"),
    user_id: int | None = Form(default=None),
    topic: str | None = Form(default=None),
    title: str | None = Form(default=None),
    source_uri: str | None = Form(default=None),
    chapter: str | None = Form(default=None),
    page_no: int | None = Form(default=None),
    image_id: str | None = Form(default=None),
    chunk_size: int | None = Form(default=None),
    chunk_overlap: int | None = Form(default=None),
) -> KnowledgeIngestResponse:
    resolved_source_type = (source_type or infer_source_type_from_filename(file.filename)).strip().lower()
    try:
        text = await read_and_extract_upload(file=file, source_type=resolved_source_type)
        inserted = rag_service.ingest(
            source_type=resolved_source_type,
            scope=scope,
            user_id=str(user_id) if user_id is not None else None,
            content=text,
            topic=topic,
            title=title or file.filename,
            source_uri=source_uri,
            chapter=chapter,
            page_no=page_no,
            image_id=image_id,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return KnowledgeIngestResponse(
        inserted=inserted,
        source_type=resolved_source_type,
        scope=scope,
        user_id=user_id,
        topic=topic,
    )

