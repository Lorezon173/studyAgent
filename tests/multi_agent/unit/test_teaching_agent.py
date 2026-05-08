"""Teaching Agent 单元测试。"""
from app.agent.multi_agent.teaching_agent import teaching_agent_node


def _make_state(**overrides):
    base = {
        "session_id": "test-1",
        "user_id": 1,
        "user_input": "我想学二分查找",
        "topic": "二分查找",
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
    base.update(overrides)
    return base


def test_teaching_agent_produces_output(monkeypatch):
    monkeypatch.setattr(
        "app.services.llm.llm_service.invoke",
        lambda system_prompt, user_prompt, stream_output=False: "二分查找是每次取中间值比较的算法。",
    )
    state = _make_state()
    result = teaching_agent_node(state)
    assert "teaching_output" in result
    assert result["teaching_output"]["reply"] == "二分查找是每次取中间值比较的算法。"
    assert result["current_agent"] == "eval"


def test_teaching_agent_uses_rag_context(monkeypatch):
    captured = []
    def fake_invoke(system_prompt, user_prompt, stream_output=False):
        captured.append(user_prompt)
        return "基于检索结果的讲解。"
    monkeypatch.setattr("app.services.llm.llm_service.invoke", fake_invoke)

    state = _make_state(retrieval_output={"rag_context": "检索到的知识内容"})
    teaching_agent_node(state)
    assert any("检索到的知识内容" in p for p in captured)
