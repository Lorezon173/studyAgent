"""Multi-Agent Chat API。"""
from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.agent.multi_agent.graph import get_multi_agent_graph

router = APIRouter(prefix="/chat", tags=["multi-agent"])


class MultiChatRequest(BaseModel):
    session_id: str = Field(..., description="学习会话 ID")
    user_id: int | None = Field(default=None, description="数字用户ID")
    topic: str | None = Field(default=None, description="学习主题")
    user_input: str = Field(..., description="用户当前输入")


class MultiChatResponse(BaseModel):
    session_id: str
    final_reply: str
    teaching_output: dict | None = None
    eval_output: dict | None = None
    mastery_score: float | None = None


@router.post("/multi", response_model=MultiChatResponse)
async def chat_multi(request: MultiChatRequest):
    """Multi-Agent 协作对话接口。"""
    graph = get_multi_agent_graph()
    config = {"configurable": {"thread_id": request.session_id}}

    state = {
        "session_id": request.session_id,
        "user_id": request.user_id,
        "user_input": request.user_input,
        "topic": request.topic,
        "current_agent": "orchestrator",
        "task_queue": [],
        "completed_tasks": [],
        "teaching_output": {},
        "eval_output": {},
        "retrieval_output": {},
        "final_reply": "",
        "mastery_score": None,
        "branch_trace": [],
    }

    result = graph.invoke(state, config=config)

    return MultiChatResponse(
        session_id=request.session_id,
        final_reply=result.get("final_reply", ""),
        teaching_output=result.get("teaching_output") or None,
        eval_output=result.get("eval_output") or None,
        mastery_score=result.get("mastery_score"),
    )
