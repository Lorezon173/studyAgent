"""Teaching Agent：诊断 + 讲解。"""
from app.agent.multi_agent.state import MultiAgentState
from app.services.llm import llm_service


def teaching_agent_node(state: MultiAgentState) -> dict:
    """Teaching Agent 节点：讲解知识点。"""
    topic = state.get("topic") or "未指定主题"
    user_input = state.get("user_input", "")
    rag_context = state.get("retrieval_output", {}).get("rag_context", "")

    context_block = ""
    if rag_context:
        context_block = f"\n\n[参考知识]\n{rag_context}"

    system_prompt = "你是一个专业的教学助手，擅长用通俗易懂的方式讲解概念。"
    user_prompt = f"主题：{topic}\n用户问题：{user_input}{context_block}\n\n请给出清晰的讲解，并用例子说明。"

    reply = llm_service.invoke(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
    )

    return {
        "teaching_output": {
            "explanation": reply,
            "reply": reply,
        },
        "current_agent": "eval",
        "branch_trace": [{"phase": "teaching_agent", "topic": topic}],
    }
