"""System Eval 流程集成测试。"""
import os
import tempfile
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_eval_api_returns_404_for_nonexistent(monkeypatch):
    """评估不存在的会话返回 404。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setattr("app.core.config.settings.eval_db_path", os.path.join(tmpdir, "test_eval.db"))
        resp = client.get("/eval/nonexistent-session")
        assert resp.status_code == 404


def test_eval_stats_returns_empty_when_no_data(monkeypatch):
    """无评估数据时返回空统计。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setattr("app.core.config.settings.eval_db_path", os.path.join(tmpdir, "test_eval.db"))
        resp = client.get("/eval/stats/overview")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total_evaluations"] == 0
