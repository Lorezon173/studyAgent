"""验证 LearningState.rag_meta_last 类型注解是 Optional[RAGExecutionMeta]。"""
from app.agent.state import LearningState
from app.services.rag_coordinator import RAGExecutionMeta


def test_rag_meta_last_accepts_meta_instance():
    meta = RAGExecutionMeta(
        reason="ok", used_tools=[], hit_count=0,
        fallback_used=False, query_mode="fact", query_reason="t",
    )
    state: LearningState = {"rag_meta_last": meta}
    assert isinstance(state["rag_meta_last"], RAGExecutionMeta)


def test_rag_meta_last_accepts_none():
    state: LearningState = {"rag_meta_last": None}
    assert state["rag_meta_last"] is None


def test_rag_meta_last_type_annotation_references_meta():
    """注解应包含 RAGExecutionMeta（非 object）。"""
    annotations = LearningState.__annotations__
    annotation = annotations.get("rag_meta_last")
    assert annotation is not None
    annotation_str = str(annotation)
    assert "RAGExecutionMeta" in annotation_str, \
        f"expected RAGExecutionMeta in annotation, got: {annotation_str}"
    assert "object" != annotation_str.strip(), \
        "rag_meta_last is still typed as bare object"
