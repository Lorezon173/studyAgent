"""System Eval 评估图构建。"""
from app.agent.system_eval.teaching_eval import teaching_eval_node
from app.agent.system_eval.orchestrator_eval import orchestrator_eval_node
from app.agent.system_eval.eval_store import EvalResultStore


def run_system_eval(session_id: str, session_data: dict, db_path: str = "data/eval_results.db") -> dict:
    """执行 System Eval：串联 Teaching Eval → Orchestrator Eval → 存储。"""
    # Step 1: Teaching Eval
    teaching_input = {
        "session_id": session_id,
        "topic": session_data.get("topic", ""),
        "user_input": session_data.get("user_input", ""),
        "teaching_output": session_data.get("teaching_output", {}),
        "final_mastery_score": session_data.get("mastery_score", 50.0),
    }
    teaching_result = teaching_eval_node(teaching_input)

    # Step 2: Orchestrator Eval（依赖 Teaching Eval 结果）
    orchestrator_input = {
        "session_id": session_id,
        "user_input": session_data.get("user_input", ""),
        "detected_intent": session_data.get("detected_intent", ""),
        "task_queue": session_data.get("task_queue", []),
        "teaching_eval_result": teaching_result,
        "actual_flow": session_data.get("actual_flow", []),
        "response_time_ms": session_data.get("response_time_ms", 0.0),
    }
    orchestrator_result = orchestrator_eval_node(orchestrator_input)

    # Step 3: 存储
    store = EvalResultStore(db_path=db_path)
    store.save(
        session_id=session_id,
        teaching_eval=teaching_result,
        orchestrator_eval=orchestrator_result,
    )

    return {
        "session_id": session_id,
        "teaching_eval": teaching_result,
        "orchestrator_eval": orchestrator_result,
    }
