from app.agent.nodes import llm_answer_node, rag_answer_node


def test_llm_answer_node_appends_boundary_notice_when_low_evidence(monkeypatch):
    monkeypatch.setattr("app.agent.nodes.llm_service.invoke", lambda **kwargs: "基础回答")
    state = {"user_input": "什么是二分查找", "rag_low_evidence": True}

    result = llm_answer_node(state)
    assert "基础回答" in result["reply"]
    assert "【证据边界声明】" in result["reply"]


def test_rag_answer_node_keeps_reply_when_not_low_evidence(monkeypatch):
    monkeypatch.setattr("app.agent.nodes.llm_service.invoke", lambda **kwargs: "RAG回答")
    state = {"user_input": "什么是二分查找", "rag_context": "证据", "rag_low_evidence": False}

    result = rag_answer_node(state)
    assert result["reply"] == "RAG回答"
