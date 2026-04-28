"""验证装饰器元数据可被外部观察工具消费。"""
from app.agent.node_registry import get_registry
import app.agent.nodes  # 触发注册


def test_all_nodes_have_trace_labels():
    """每个注册节点都有非空 trace_label。"""
    reg = get_registry()
    for name, (meta, _fn) in reg.all().items():
        assert meta.trace_label, f"node '{name}' missing trace_label"


def test_retry_keys_are_valid():
    """retry_key 取值在 {None, LLM_RETRY, RAG_RETRY, DB_RETRY} 内。"""
    reg = get_registry()
    valid = {None, "LLM_RETRY", "RAG_RETRY", "DB_RETRY"}
    for name, (meta, _fn) in reg.all().items():
        assert meta.retry_key in valid, \
            f"node '{name}' has invalid retry_key={meta.retry_key!r}"


def test_no_node_has_duplicate_name():
    """注册表保证名称唯一（registry.register 也会强制）。"""
    reg = get_registry()
    names = list(reg.all().keys())
    assert len(names) == len(set(names))


def test_all_production_nodes_registered():
    """17 个生产节点全部在注册表中（不强制 == 17，因测试装饰器会向全局 registry 注入临时节点）。"""
    reg = get_registry()
    expected = {
        "intent_router", "history_check", "ask_review_or_continue",
        "diagnose", "knowledge_retrieval", "explain", "restate_check",
        "followup", "summary", "rag_first", "rag_answer", "llm_answer",
        "replan", "retrieval_planner", "evidence_gate", "answer_policy",
        "recovery",
    }
    assert expected.issubset(set(reg.all().keys()))
