"""Retrieval Agent：知识检索。"""
from app.agent.multi_agent.state import MultiAgentState
from app.core.config import settings


def retrieval_agent_node(state: MultiAgentState) -> dict:
    """Retrieval Agent 节点：执行知识检索。"""
    user_input = state.get("user_input", "")
    topic = state.get("topic")
    user_id = state.get("user_id")

    if not settings.rag_enabled:
        return {
            "retrieval_output": {
                "citations": [],
                "rag_context": "",
                "rag_found": False,
                "rag_confidence_level": "",
            },
            "current_agent": "teaching",
            "branch_trace": [{"phase": "retrieval_agent", "rag_enabled": False}],
        }

    from app.services.rag_service import rag_service

    global_results = rag_service.retrieve(
        query=user_input, topic=topic, top_k=settings.rag_retrieve_top_k,
    )

    citations = list(global_results)

    if user_id:
        personal_results = rag_service.retrieve_scoped(
            query=user_input, scope="personal",
            user_id=str(user_id), topic=topic,
            top_k=settings.rag_retrieve_top_k,
        )
        citations.extend(personal_results)

    rag_context = ""
    if citations:
        rag_context = "\n".join(c.get("text", "") for c in citations if c.get("text"))

    rag_found = len(citations) > 0
    confidence = "high" if rag_found and len(citations) >= 2 else ("medium" if rag_found else "low")

    return {
        "retrieval_output": {
            "citations": citations,
            "rag_context": rag_context,
            "rag_found": rag_found,
            "rag_confidence_level": confidence,
        },
        "current_agent": "teaching",
        "branch_trace": [{"phase": "retrieval_agent", "rag_found": rag_found, "citation_count": len(citations)}],
    }
