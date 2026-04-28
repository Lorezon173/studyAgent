"""问答节点：RAG 优先 / RAG 回答 / 纯 LLM 回答 / 知识检索补充。"""

from app.agent.state import LearningState
from app.agent.nodes._shared import _append_trace
from app.services.llm import llm_service
from app.services.rag_coordinator import decide_rag_call, execute_rag


def rag_first_node(state: LearningState) -> LearningState:
    """RAG优先检索节点：在回答问题前，先检索本地知识库"""
    from app.services.rag_coordinator import decide_rag_call, execute_rag

    topic = state.get("topic")
    user_input = state.get("user_input", "")
    user_id = state.get("user_id")

    state["rag_found"] = False
    state["rag_context"] = ""
    state["rag_citations"] = []
    state["rag_confidence_level"] = "low"
    state["rag_low_evidence"] = True
    state["rag_avg_score"] = 0.0

    try:
        decision = decide_rag_call(user_input=user_input)
        if not decision.should_call:
            _append_trace(state, "rag_first", {
                "rag_found": False,
                "reason": decision.reason,
                "citations_count": 0,
            })
            return state

        rows, meta = execute_rag(
            query=user_input,
            topic=topic,
            user_id=user_id,
            tool_route=state.get("tool_route"),
            top_k=5,
            strategy=state.get("retrieval_strategy") or {},
        )
        state["rag_meta_last"] = meta

        if rows:
            context_parts = []
            citations = []
            for row in rows:
                content = row.get("text", "")
                if content:
                    context_parts.append(content)
                citations.append({
                    "source": row.get("source", "unknown"),
                    "score": row.get("score", 0),
                })
            state["rag_context"] = "\n\n".join(context_parts)
            state["rag_citations"] = citations
            state["rag_found"] = True
            scores = [float(row.get("score", 0.0)) for row in rows]
            avg_score = sum(scores) / len(scores) if scores else 0.0
            state["rag_avg_score"] = avg_score
            if len(rows) >= 2 and avg_score >= 0.7:
                state["rag_confidence_level"] = "high"
                state["rag_low_evidence"] = False
            elif len(rows) >= 1 and avg_score >= 0.45:
                state["rag_confidence_level"] = "medium"
                state["rag_low_evidence"] = False
    except Exception as e:
        from app.services.error_classifier import classify_error
        classification = classify_error(e)
        retry_trace = list(state.get("retry_trace") or [])
        # Only append after the first failure: detect retry by presence of prior error_code.
        if state.get("error_code"):
            retry_trace.append({"node": "rag_first", "error": classification.error_type.value})
        state["node_error"] = f"rag_first: {str(e)}"
        state["error_code"] = classification.error_type.value
        state["retry_trace"] = retry_trace
        state["rag_found"] = False

    _append_trace(state, "rag_first", {
        "rag_found": state.get("rag_found"),
        "citations_count": len(state.get("rag_citations", [])),
    })

    return state


def rag_answer_node(state: LearningState) -> LearningState:
    """基于RAG知识回答节点"""
    user_input = state.get("user_input", "")
    rag_context = state.get("rag_context", "")

    prompt = f"""请基于以下知识回答用户问题。

【相关知识】
{rag_context}

【用户问题】
{user_input}

请准确回答，并标注知识来源。"""

    stream_output = bool(state.get("stream_output", False))

    reply = llm_service.invoke(
        system_prompt="你是一个严谨的知识问答助手，请基于提供的知识准确回答问题。",
        user_prompt=prompt,
        stream_output=stream_output,
    )

    state["reply"] = reply
    if state.get("rag_low_evidence"):
        state["reply"] = (
            f"{state['reply']}\n\n"
            "【证据边界声明】当前可用证据较弱，以下内容包含推断，请优先结合教材或权威资料核验。"
        )
    state["stage"] = "rag_answered"

    _append_trace(state, "rag_answer", {"reply_length": len(reply)})

    return state


def llm_answer_node(state: LearningState) -> LearningState:
    """基于LLM回答节点（无知识库支撑）"""
    user_input = state.get("user_input", "")

    stream_output = bool(state.get("stream_output", False))

    reply = llm_service.invoke(
        system_prompt="你是一个知识渊博的问答助手。",
        user_prompt=user_input,
        stream_output=stream_output,
    )

    state["reply"] = reply
    if state.get("rag_low_evidence"):
        state["reply"] = (
            f"{state['reply']}\n\n"
            "【证据边界声明】当前可用证据较弱，以下内容包含推断，请优先结合教材或权威资料核验。"
        )
    state["stage"] = "llm_answered"

    _append_trace(state, "llm_answer", {"reply_length": len(reply)})

    return state


def knowledge_retrieval_node(state: LearningState) -> LearningState:
    """知识检索节点：在需要时补充知识"""
    from app.services.rag_coordinator import decide_rag_call, execute_rag

    topic = state.get("topic")
    user_input = state.get("user_input", "")
    user_id = state.get("user_id")

    state["retrieved_context"] = ""
    state["citations"] = []

    try:
        decision = decide_rag_call(user_input=user_input)
        if not decision.should_call:
            _append_trace(state, "knowledge_retrieval", {
                "citations_count": 0,
                "reason": decision.reason,
            })
            return state

        rows, meta = execute_rag(
            query=user_input,
            topic=topic,
            user_id=user_id,
            tool_route=state.get("tool_route"),
            top_k=5,
            strategy=state.get("retrieval_strategy") or {},
        )
        state["rag_meta_last"] = meta

        if rows:
            context_parts = []
            citations = []
            for row in rows:
                content = row.get("content", "")
                if content:
                    context_parts.append(content)
                citations.append({
                    "source": row.get("source", "unknown"),
                    "score": row.get("score", 0),
                })
            context = "\n\n".join(context_parts)
            state["retrieved_context"] = context
            state["citations"] = citations

            if context:
                existing = state.get("topic_context", "")
                state["topic_context"] = f"{existing}\n\n{context}".strip()
    except Exception as exc:
        from app.services.error_classifier import classify_error
        classification = classify_error(exc)
        _append_trace(state, "knowledge_retrieval_error", {
            "error_type": classification.error_type.value,
            "message": str(exc),
        })
        retry_trace = list(state.get("retry_trace") or [])
        # Only append after the first failure: detect retry by presence of prior error_code.
        if state.get("error_code"):
            retry_trace.append({"node": "knowledge_retrieval", "error": classification.error_type.value})
        return {
            "node_error": str(exc),
            "error_code": classification.error_type.value,
            "rag_found": False,
            "retry_trace": retry_trace,
        }

    _append_trace(state, "knowledge_retrieval", {"citations_count": len(state.get("citations", []))})

    return state
