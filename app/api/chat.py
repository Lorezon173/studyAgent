from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from queue import Queue
from threading import Thread

from app.core.config import settings
from app.models.schemas import (
    ChatRequest,
    ChatResponse,
    RagCandidateModel,
    RagExecutionDetailModel,
)
from app.services.agent_service import agent_service
from app.services.llm import llm_service
from app.services.task_dispatcher import dispatch
from app.services import redis_pubsub as redis_pubsub_module

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    """
    学习对话端点 - 执行多轮费曼学习闭环

    阶段A：诊断 + 讲解
    阶段B：复述检测 + 追问
    阶段C：总结
    """
    numeric_user_id = request.user_id
    if numeric_user_id is not None and numeric_user_id <= 0:
        raise HTTPException(status_code=400, detail="user_id 必须是正整数")

    try:
        result = agent_service.run(
            session_id=request.session_id,
            topic=request.topic,
            user_input=request.user_input,
            user_id=numeric_user_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    rag_meta = result.get("rag_meta_last")
    rag_detail = None
    if rag_meta is not None:
        rag_detail = RagExecutionDetailModel(
            query_mode=getattr(rag_meta, "query_mode", ""),
            used_tools=list(getattr(rag_meta, "used_tools", []) or []),
            hit_count=getattr(rag_meta, "hit_count", 0),
            elapsed_ms=getattr(rag_meta, "elapsed_ms", 0),
            reranked=getattr(rag_meta, "reranked", False),
            candidates=[
                RagCandidateModel(
                    chunk_id=str(c.get("chunk_id", "")),
                    score=float(c.get("score", 0.0)),
                    tool=str(c.get("tool", "")),
                )
                for c in (getattr(rag_meta, "candidates", []) or [])
            ],
            selected_chunk_ids=list(getattr(rag_meta, "selected_chunk_ids", []) or []),
        )

    return ChatResponse(
        session_id=result["session_id"],
        stage=result.get("stage", "unknown"),
        reply=result.get("reply", ""),
        summary=result.get("summary"),
        citations=result.get("citations", []),
        rag_confidence_level=result.get("rag_confidence_level"),
        rag_low_evidence=result.get("rag_low_evidence"),
        rag_detail=rag_detail,
    )


@router.post("/stream")
def chat_stream(request: ChatRequest) -> StreamingResponse:
    numeric_user_id = request.user_id
    if numeric_user_id is not None and numeric_user_id <= 0:
        raise HTTPException(status_code=400, detail="user_id 必须是正整数")

    if settings.async_graph_enabled:
        return StreamingResponse(
            _async_event_generator(request, numeric_user_id),
            media_type="text/event-stream",
        )

    return StreamingResponse(
        _sync_event_generator(request, numeric_user_id),
        media_type="text/event-stream",
    )


def _async_event_generator(request: ChatRequest, numeric_user_id):
    """异步路径：先订阅 chat:{session_id} 频道，再 dispatch 任务，桥接事件到 SSE。"""
    payload = {
        "session_id": request.session_id,
        "topic": request.topic,
        "user_input": request.user_input,
        "user_id": numeric_user_id,
    }
    pubsub = redis_pubsub_module.get_default_pubsub()
    channel = f"chat:{request.session_id}"
    timeout_s = float(settings.celery_task_timeout_s) + 5.0

    with pubsub.open_subscription(channel, timeout_s=timeout_s) as events:
        try:
            dispatch(payload)
        except Exception as exc:  # noqa: BLE001
            yield f"event: error\ndata: dispatch failed: {exc}\n\n"
            return

        try:
            for event, data in events:
                safe = data.replace("\r", " ").replace("\n", "\\n")
                yield f"event: {event}\ndata: {safe}\n\n"
        except TimeoutError:
            yield "event: error\ndata: worker timeout\n\n"


def _sync_event_generator(request: ChatRequest, numeric_user_id):
    """同步路径（Phase 7 前行为，flag off 时使用）。"""
    queue: Queue[tuple[str, str]] = Queue()

    def worker() -> None:
        def _on_chunk(piece: str) -> None:
            safe = piece.replace("\r", " ").replace("\n", "\\n")
            queue.put(("token", safe))

        with llm_service.stream_to(_on_chunk):
            try:
                result = agent_service.run(
                    session_id=request.session_id,
                    topic=request.topic,
                    user_input=request.user_input,
                    user_id=numeric_user_id,
                    stream_output=True,
                )
                queue.put(("stage", str(result.get("stage", "unknown"))))
            except ValueError as exc:
                queue.put(("error", str(exc)))
            except Exception as exc:  # noqa: BLE001
                queue.put(("error", f"stream failed: {exc}"))
            finally:
                queue.put(("done", "[DONE]"))

    Thread(target=worker, daemon=True).start()
    while True:
        event, data = queue.get()
        yield f"event: {event}\ndata: {data}\n\n"
        if event == "done":
            break
