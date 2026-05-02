"""Phase 3c Task 4：run_regression CLI 行为。"""
from pathlib import Path
import pytest

import slo.run_regression as rr


@pytest.fixture
def stub_agent_pass(monkeypatch):
    """全部 12 题都成功、有 citations、低延迟，预期 SLO 全部达标。"""
    counter = {"n": 0}

    def fake_run(session_id, topic, user_input, user_id=None,
                 stream_output=False, progress_sink=None):
        counter["n"] += 1
        if progress_sink:
            progress_sink("token", "tok-1")
        return {
            "session_id": session_id,
            "stage": "explained",
            "reply": "回答内容",
            "citations": [{"chunk_id": "c1"}],
            "rag_low_evidence": False,
        }

    from app.services import agent_service as agent_mod
    monkeypatch.setattr(agent_mod.agent_service, "run", fake_run)
    return counter


@pytest.fixture
def stub_agent_breach(monkeypatch):
    """全部失败，预期 task_success_rate < 0.97。"""
    def fake_run(**kwargs):
        return {
            "session_id": kwargs["session_id"],
            "stage": "unknown",
            "reply": "",
        }

    from app.services import agent_service as agent_mod
    monkeypatch.setattr(agent_mod.agent_service, "run", fake_run)


def test_run_regression_returns_zero_when_all_pass(stub_agent_pass):
    exit_code = rr.main(argv=[])
    assert exit_code == 0
    assert stub_agent_pass["n"] == 12  # 12 题全跑完


def test_run_regression_returns_one_when_any_breach(stub_agent_breach):
    exit_code = rr.main(argv=[])
    assert exit_code == 1


def test_disclaimer_detector_recognizes_keywords():
    assert rr._reply_has_disclaimer("当前证据不足，建议进一步查阅资料。") is True
    assert rr._reply_has_disclaimer("信息有限，无法确定准确答案。") is True
    assert rr._reply_has_disclaimer("这是一道明确的数学题。") is False


def test_run_regression_returns_two_on_yaml_error(monkeypatch, tmp_path):
    """阈值文件路径错误时 exit code = 2。"""
    monkeypatch.setattr(rr, "_DEFAULT_THRESHOLDS_PATH", tmp_path / "missing.yaml")
    exit_code = rr.main(argv=[])
    assert exit_code == 2
