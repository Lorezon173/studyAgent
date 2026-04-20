from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from queue import Queue
from threading import Thread

from app.models.schemas import ChatRequest, ChatResponse
from app.services.agent_service import agent_service
from app.services.llm import llm_service

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

    return ChatResponse(
        session_id=result["session_id"],
        stage=result.get("stage", "unknown"),
        reply=result.get("reply", ""),
        summary=result.get("summary"),
        citations=result.get("citations", []),
        rag_confidence_level=result.get("rag_confidence_level"),
        rag_low_evidence=result.get("rag_low_evidence"),
    )


@router.post("/stream")
def chat_stream(request: ChatRequest) -> StreamingResponse:
    numeric_user_id = request.user_id
    if numeric_user_id is not None and numeric_user_id <= 0:
        raise HTTPException(status_code=400, detail="user_id 必须是正整数")

    def event_generator():
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

    return StreamingResponse(event_generator(), media_type="text/event-stream")
