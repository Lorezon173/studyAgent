"""Orchestrator Agent：意图识别、任务分配、结果汇总。"""
import json

from app.agent.multi_agent.state import MultiAgentState
from app.services.llm import llm_service


def orchestrator_node(state: MultiAgentState) -> dict:
    """Orchestrator 节点：分析意图，构建任务队列。"""
    user_input = state.get("user_input", "")
    topic = state.get("topic")

    # 规则路由（常见模式，优先匹配）
    if "评估" in user_input or "理解程度" in user_input:
        return {
            "current_agent": "eval",
            "task_queue": [{"type": "evaluate", "topic": topic}],
        }

    if "讲解" in user_input or "学" in user_input:
        return {
            "current_agent": "teaching",
            "task_queue": [
                {"type": "teach", "topic": topic},
                {"type": "evaluate", "topic": topic},
            ],
        }

    if "问答" in user_input or "直接回答" in user_input:
        return {
            "current_agent": "retrieval",
            "task_queue": [{"type": "retrieve", "topic": topic}],
        }

    # LLM 路由（边界情况）
    try:
        raw = llm_service.route_intent(user_input)
        data = json.loads(raw)
        intent = str(data.get("intent", "teach_loop")).strip()
    except Exception:
        intent = "teach_loop"

    intent_map = {
        "teach_loop": "teaching",
        "qa_direct": "retrieval",
        "review": "teaching",
        "replan": "teaching",
    }
    current_agent = intent_map.get(intent, "teaching")

    queue = [{"type": "teach", "topic": topic}]
    if current_agent == "teaching":
        queue.append({"type": "evaluate", "topic": topic})

    return {
        "current_agent": current_agent,
        "task_queue": queue,
    }


def aggregator_node(state: MultiAgentState) -> dict:
    """汇总节点：整合各 Agent 输出，生成最终回复。"""
    teaching_output = state.get("teaching_output", {})
    eval_output = state.get("eval_output", {})

    parts = []
    teaching_reply = teaching_output.get("reply", "")
    if teaching_reply:
        parts.append(teaching_reply)

    eval_feedback = eval_output.get("eval_feedback", "")
    if eval_feedback:
        parts.append(f"--- 评估反馈 ---\n{eval_feedback}")

    final_reply = "\n\n".join(parts) if parts else "未能生成有效回复。"

    agents_used = []
    if teaching_output:
        agents_used.append("teaching")
    if eval_output:
        agents_used.append("eval")

    return {
        "final_reply": final_reply,
        "mastery_score": eval_output.get("mastery_score"),
        "branch_trace": [{"phase": "aggregator", "agents_used": agents_used}],
    }
