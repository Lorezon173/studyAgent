"""Phase 3a/3b 共用：验证 run_chat_graph 任务注册于 celery_app。

（Echo 行为测试在 3b 删除，真实 graph 行为测试见 test_worker_tasks_real_graph.py）
"""
from app.worker.celery_app import celery_app


def test_task_is_registered_with_expected_name():
    assert "app.worker.tasks.run_chat_graph" in celery_app.tasks
