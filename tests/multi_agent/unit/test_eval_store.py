"""EvalResultStore 单元测试。"""
import os
import tempfile
from app.agent.system_eval.eval_store import EvalResultStore


def test_save_and_get_result():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_eval.db")
        store = EvalResultStore(db_path=db_path)

        store.save(
            session_id="sess-1",
            teaching_eval={"teaching_score": 75.0, "clarity_score": 80.0},
            orchestrator_eval={"orchestrator_score": 85.0, "intent_accuracy": 90.0},
        )

        result = store.get("sess-1")
        assert result is not None
        assert result["session_id"] == "sess-1"
        assert result["teaching_eval"]["teaching_score"] == 75.0
        assert result["orchestrator_eval"]["orchestrator_score"] == 85.0


def test_get_nonexistent_returns_none():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_eval.db")
        store = EvalResultStore(db_path=db_path)
        assert store.get("nonexistent") is None


def test_save_overwrites_existing():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_eval.db")
        store = EvalResultStore(db_path=db_path)

        store.save("sess-1", {"teaching_score": 60.0}, {"orchestrator_score": 70.0})
        store.save("sess-1", {"teaching_score": 80.0}, {"orchestrator_score": 90.0})

        result = store.get("sess-1")
        assert result["teaching_eval"]["teaching_score"] == 80.0


def test_get_stats():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_eval.db")
        store = EvalResultStore(db_path=db_path)

        store.save("sess-1", {"teaching_score": 70.0}, {"orchestrator_score": 80.0})
        store.save("sess-2", {"teaching_score": 80.0}, {"orchestrator_score": 90.0})

        stats = store.get_stats()
        assert stats["total_evaluations"] == 2
        assert stats["avg_teaching_score"] == 75.0
        assert stats["avg_orchestrator_score"] == 85.0
