"""验证 RagView 读写直接落到原 state dict（无独立状态）。"""
from app.agent.state_view import RagView


def test_ragview_read_default_when_state_empty():
    state = {}
    view = RagView(state)
    assert view.found is False
    assert view.context == ""
    assert view.citations == []
    assert view.confidence_level == "low"
    assert view.low_evidence is True
    assert view.avg_score == 0.0
    assert view.meta_last is None


def test_ragview_read_existing_values():
    state = {
        "rag_found": True,
        "rag_context": "B+ tree definition",
        "rag_citations": [{"source": "textbook", "score": 0.9}],
        "rag_confidence_level": "high",
        "rag_low_evidence": False,
        "rag_avg_score": 0.85,
    }
    view = RagView(state)
    assert view.found is True
    assert view.context == "B+ tree definition"
    assert view.citations == [{"source": "textbook", "score": 0.9}]
    assert view.confidence_level == "high"
    assert view.low_evidence is False
    assert view.avg_score == 0.85


def test_ragview_reset_writes_defaults_into_state():
    state = {"rag_found": True, "rag_context": "stale", "rag_avg_score": 0.5}
    view = RagView(state)
    view.reset()
    assert state["rag_found"] is False
    assert state["rag_context"] == ""
    assert state["rag_avg_score"] == 0.0
    assert state["rag_low_evidence"] is True


def test_ragview_record_hit_sets_all_fields():
    state = {}
    view = RagView(state)
    view.record_hit(
        context="ctx",
        citations=[{"source": "a", "score": 0.7}],
        avg_score=0.7,
        confidence_level="medium",
    )
    assert state["rag_found"] is True
    assert state["rag_context"] == "ctx"
    assert state["rag_citations"] == [{"source": "a", "score": 0.7}]
    assert state["rag_avg_score"] == 0.7
    assert state["rag_confidence_level"] == "medium"
    assert state["rag_low_evidence"] is False  # medium → not low


def test_ragview_record_hit_low_confidence_marks_low_evidence():
    state = {}
    view = RagView(state)
    view.record_hit(
        context="ctx",
        citations=[],
        avg_score=0.2,
        confidence_level="low",
    )
    assert state["rag_low_evidence"] is True


def test_ragview_to_return_dict_matches_state_keys():
    state = {
        "rag_found": True,
        "rag_context": "x",
        "rag_citations": [{"s": 1}],
        "rag_confidence_level": "high",
        "rag_low_evidence": False,
        "rag_avg_score": 0.9,
        "rag_meta_last": None,
    }
    view = RagView(state)
    out = view.to_return_dict()
    assert set(out.keys()) == {
        "rag_found", "rag_context", "rag_citations",
        "rag_confidence_level", "rag_low_evidence", "rag_avg_score",
        "rag_meta_last",
    }
    assert out["rag_context"] == "x"


def test_ragview_record_meta_stores_meta_only():
    """记录 meta 不应触发命中状态。"""
    from app.services.rag_coordinator import RAGExecutionMeta
    state = {}
    view = RagView(state)
    meta = RAGExecutionMeta(
        reason="ok", used_tools=[], hit_count=0,
        fallback_used=False, query_mode="fact", query_reason="t",
    )
    view.record_meta(meta)
    assert state["rag_meta_last"] is meta
    assert state.get("rag_found") is None  # 未触碰 found


def test_ragview_record_meta_none_writes_none_into_state():
    """record_meta is a drop-in for state["rag_meta_last"] = meta;
    None must produce an explicit None entry, not skip the write."""
    state = {"rag_meta_last": "not-none-yet"}
    view = RagView(state)
    view.record_meta(None)
    assert "rag_meta_last" in state
    assert state["rag_meta_last"] is None
