"""异步评估队列。"""
import logging

from app.core.config import settings

logger = logging.getLogger(__name__)


async def enqueue_eval(session_id: str, session_data: dict):
    """将评估任务加入队列。

    当 multi_agent_eval_enabled=True 时，会话结束后自动调用。
    当前实现为同步执行（后续可替换为 Celery 任务）。
    """
    if not getattr(settings, "multi_agent_eval_enabled", False):
        logger.debug("System Eval disabled, skipping session=%s", session_id)
        return

    try:
        from app.agent.system_eval.eval_graph import run_system_eval
        result = run_system_eval(
            session_id=session_id,
            session_data=session_data,
        )
        logger.info("System Eval completed for session=%s", session_id)
        return result
    except Exception as e:
        logger.error("System Eval failed for session=%s: %s", session_id, e)
        return None
