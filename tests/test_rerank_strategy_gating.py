from unittest.mock import patch

from app.services.rerank_service import should_rerank


def test_should_rerank_true_for_comparison_with_enough_candidates():
    strategy = {"bm25_weight": 0.5, "vector_weight": 0.5}
    assert should_rerank(strategy=strategy, candidate_count=5) is True


def test_should_rerank_false_for_fact_with_few_candidates():
    strategy = {"bm25_weight": 0.4, "vector_weight": 0.6}
    assert should_rerank(strategy=strategy, candidate_count=2) is False


def test_should_rerank_false_when_strategy_disables():
    strategy = {"bm25_weight": 0.4, "vector_weight": 0.6, "rerank_enabled": False}
    assert should_rerank(strategy=strategy, candidate_count=10) is False


def test_should_rerank_true_when_strategy_forces():
    strategy = {"rerank_enabled": True}
    assert should_rerank(strategy=strategy, candidate_count=2) is True


def test_execute_rag_calls_rerank_when_strategy_says_so():
    fake_rows = [{"chunk_id": f"c{i}", "score": 0.5, "text": f"x{i}"} for i in range(5)]
    from app.services import rag_coordinator
    with patch.object(rag_coordinator, "execute_retrieval_tools",
                      return_value=(fake_rows, ["search_local_textbook"])), \
         patch("app.services.rerank_service.rerank_items",
               return_value=fake_rows) as rerank_spy:
        rag_coordinator.execute_rag(
            query="对比 A 和 B", topic=None, user_id=None,
            tool_route=None, top_k=5,
            strategy={"bm25_weight": 0.5, "vector_weight": 0.5},
        )
    assert rerank_spy.called


def test_execute_rag_skips_rerank_when_strategy_off():
    fake_rows = [{"chunk_id": f"c{i}", "score": 0.5, "text": f"x{i}"} for i in range(5)]
    from app.services import rag_coordinator
    with patch.object(rag_coordinator, "execute_retrieval_tools",
                      return_value=(fake_rows, ["search_local_textbook"])), \
         patch("app.services.rerank_service.rerank_items") as rerank_spy:
        rag_coordinator.execute_rag(
            query="什么是B+树", topic=None, user_id=None,
            tool_route=None, top_k=5,
            strategy={"bm25_weight": 0.4, "vector_weight": 0.6},
        )
    assert not rerank_spy.called
