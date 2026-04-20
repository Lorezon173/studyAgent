# tests/test_retrieval_strategy.py
"""检索策略配置测试"""
from app.services.retrieval_strategy import get_retrieval_strategy, RETRIEVAL_STRATEGIES


def test_retrieval_strategy_for_fact_mode():
    """测试事实模式的检索策略"""
    strategy = get_retrieval_strategy("fact")
    assert strategy["bm25_weight"] == 0.4
    assert strategy["vector_weight"] == 0.6
    assert strategy["web_enabled"] is False
    assert strategy["top_k"] == 3


def test_retrieval_strategy_for_freshness_mode():
    """测试时效性模式的检索策略"""
    strategy = get_retrieval_strategy("freshness")
    assert strategy["web_enabled"] is True
    assert strategy["top_k"] == 5


def test_retrieval_strategy_for_comparison_mode():
    """测试对比模式的检索策略"""
    strategy = get_retrieval_strategy("comparison")
    assert strategy["bm25_weight"] == 0.5
    assert strategy["vector_weight"] == 0.5


def test_retrieval_strategy_defaults_to_fact():
    """测试未知模式默认返回事实模式策略"""
    strategy = get_retrieval_strategy("unknown_mode")
    assert strategy == RETRIEVAL_STRATEGIES["fact"]
