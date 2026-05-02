"""Phase 3b Task 1：agent_service.run 的 progress_sink 参数。"""
import pytest

from app.services.agent_service import AgentService


@pytest.fixture
def fake_llm_and_graph(monkeypatch):
    """隔离 LLM 与 graph：让 agent_service.run 只走 stream_to 通路 + 返回固定 state。"""
    from app.services import llm as llm_mod

    real_llm = llm_mod.llm_service

    def fake_invoke(system_prompt, user_prompt, stream_output=False):
        consumer = real_llm._stream_consumer.get()
        if stream_output and consumer is not None:
            consumer("alp")
            consumer("ha")
        return "alpha"

    monkeypatch.setattr(real_llm, "invoke", fake_invoke)

    def fake_run_with_graph_v2(**kwargs):
        # 模拟一次 LLM 调用触发 sink token
        real_llm.invoke("sys", "user", stream_output=True)
        return {
            "session_id": kwargs["session_id"],
            "stage": "explained",
            "reply": "alpha",
            "history": [],
        }

    monkeypatch.setattr(AgentService, "run_with_graph_v2", staticmethod(fake_run_with_graph_v2))
    monkeypatch.setattr(AgentService, "_should_use_graph_v2", staticmethod(lambda: True))


def test_progress_sink_receives_token_events(fake_llm_and_graph):
    events: list[tuple[str, str]] = []
    svc = AgentService()
    result = svc.run(
        session_id="s-progress-1",
        topic="math",
        user_input="hi",
        progress_sink=lambda ev, data: events.append((ev, data)),
    )
    token_events = [e for e, _ in events if e == "token"]
    stage_events = [e for e, _ in events if e == "stage"]
    assert token_events == ["token", "token"]
    assert stage_events == ["stage"]
    assert result["stage"] == "explained"


def test_progress_sink_none_keeps_existing_behavior(fake_llm_and_graph):
    """未传 progress_sink 时不 emit 任何事件（保证旧调用者零感知）。"""
    svc = AgentService()
    result = svc.run(
        session_id="s-progress-2",
        topic="math",
        user_input="hi",
    )
    assert result["stage"] == "explained"


def test_progress_sink_forces_stream_output_true(fake_llm_and_graph, monkeypatch):
    """传了 sink 即使 stream_output=False，也要强制开流式（否则 sink 收不到 token）。"""
    captured_stream: list[bool] = []

    from app.services.agent_service import AgentService as AS
    original = AS.run_with_graph_v2

    def spy(**kwargs):
        captured_stream.append(kwargs.get("stream_output", False))
        return original(**kwargs)

    monkeypatch.setattr(AS, "run_with_graph_v2", staticmethod(spy))

    events: list[tuple[str, str]] = []
    AgentService().run(
        session_id="s-progress-3",
        topic="math",
        user_input="hi",
        stream_output=False,  # 故意传 False
        progress_sink=lambda ev, data: events.append((ev, data)),
    )
    assert captured_stream == [True]
