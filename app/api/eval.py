"""System Eval API。"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.agent.system_eval.eval_store import EvalResultStore
from app.agent.system_eval.eval_graph import run_system_eval
from app.core.config import settings

router = APIRouter(prefix="/eval", tags=["system-eval"])


class EvalRerunResponse(BaseModel):
    session_id: str
    teaching_eval: dict
    orchestrator_eval: dict


@router.get("/{session_id}")
async def get_eval(session_id: str):
    """获取会话评估结果。"""
    store = EvalResultStore(db_path=settings.eval_db_path)
    result = store.get(session_id)
    if not result:
        raise HTTPException(status_code=404, detail="评估结果不存在")
    return result


@router.post("/{session_id}/rerun", response_model=EvalRerunResponse)
async def rerun_eval(session_id: str):
    """重新评估指定会话。"""
    from app.agent.multi_agent.graph import get_multi_agent_graph

    graph = get_multi_agent_graph()
    config = {"configurable": {"thread_id": session_id}}
    state_snapshot = graph.get_state(config)

    if not state_snapshot or not state_snapshot.values:
        raise HTTPException(status_code=404, detail="会话不存在")

    session_data = dict(state_snapshot.values)
    result = run_system_eval(session_id, session_data, db_path=settings.eval_db_path)

    return EvalRerunResponse(
        session_id=session_id,
        teaching_eval=result["teaching_eval"],
        orchestrator_eval=result["orchestrator_eval"],
    )


@router.get("/stats/overview")
async def get_eval_stats():
    """获取评估统计（用于可视化）。"""
    store = EvalResultStore(db_path=settings.eval_db_path)
    return store.get_stats()
