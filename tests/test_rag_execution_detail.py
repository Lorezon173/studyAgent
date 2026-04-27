from unittest.mock import patch
from app.services import rag_coordinator


def test_execution_detail_records_all_candidates():
    fake_rows = [
        {"chunk_id": "c1", "score": 0.9, "text": "A"},
        {"chunk_id": "c2", "score": 0.5, "text": "B"},
        {"chunk_id": "c3", "score": 0.3, "text": "C"},
    ]
    with patch.object(rag_coordinator, "execute_retrieval_tools",
                      return_value=(fake_rows, ["search_local_textbook"])):
        rows, meta = rag_coordinator.execute_rag(
            query="q", topic=None, user_id=None,
            tool_route=None, top_k=5, strategy={},
        )
    assert hasattr(meta, "candidates")
    assert len(meta.candidates) == 3
    assert meta.candidates[0]["chunk_id"] == "c1"
    assert "score" in meta.candidates[0]
    assert meta.elapsed_ms >= 0
    assert meta.selected_chunk_ids == ["c1", "c2", "c3"]
    assert meta.reranked is False


def test_execution_detail_marks_reranked_true():
    fake_rows = [{"chunk_id": f"c{i}", "score": 0.5, "text": f"x{i}"} for i in range(5)]
    with patch.object(rag_coordinator, "execute_retrieval_tools",
                      return_value=(fake_rows, ["search_local_textbook"])), \
         patch("app.services.rerank_service.rerank_items", return_value=fake_rows):
        _, meta = rag_coordinator.execute_rag(
            query="q", topic=None, user_id=None,
            tool_route=None, top_k=5,
            strategy={"rerank_enabled": True},
        )
    assert meta.reranked is True


def test_execution_detail_empty_path_has_zero_candidates():
    with patch.object(rag_coordinator, "execute_retrieval_tools",
                      return_value=([], [])):
        _, meta = rag_coordinator.execute_rag(
            query="q", topic=None, user_id=None,
            tool_route=None, top_k=5, strategy={},
        )
    assert meta.candidates == []
    assert meta.selected_chunk_ids == []
    assert meta.reranked is False
    assert meta.elapsed_ms >= 0
