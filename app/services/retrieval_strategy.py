# app/services/retrieval_strategy.py
"""检索策略配置模块

根据查询模式返回对应的检索策略配置。
"""
from __future__ import annotations

RETRIEVAL_STRATEGIES: dict[str, dict] = {
    "fact": {
        "bm25_weight": 0.4,
        "vector_weight": 0.6,
        "web_enabled": False,
        "top_k": 3,
        "description": "事实问答：向量优先，精确命中",
    },
    "freshness": {
        "bm25_weight": 0.2,
        "vector_weight": 0.3,
        "web_enabled": True,
        "top_k": 5,
        "description": "时效性查询：启用Web检索，扩大召回",
    },
    "comparison": {
        "bm25_weight": 0.5,
        "vector_weight": 0.5,
        "web_enabled": False,
        "top_k": 5,
        "description": "对比分析：均衡召回",
    },
}


def get_retrieval_strategy(mode: str) -> dict:
    """根据查询模式返回检索策略配置

    Args:
        mode: 查询模式（fact/freshness/comparison）

    Returns:
        检索策略配置字典
    """
    return RETRIEVAL_STRATEGIES.get(mode, RETRIEVAL_STRATEGIES["fact"])
