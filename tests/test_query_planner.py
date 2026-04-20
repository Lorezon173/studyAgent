from app.services.query_planner import build_query_plan


def test_build_query_plan_for_fact_question():
    plan = build_query_plan("二分查找是什么？", topic="算法")
    assert plan.mode == "fact"
    assert plan.top_k >= 3
    assert plan.enable_web is False


def test_build_query_plan_for_freshness_question():
    plan = build_query_plan("LangGraph 最新版本是什么", topic="框架")
    assert plan.mode == "freshness"
    assert plan.enable_web is True
    assert plan.top_k >= 4
