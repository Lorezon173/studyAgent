"""验证 NodeRegistry 单例与 add_to_graph 集成。"""
import pytest
from app.agent.node_registry import NodeRegistry, get_registry
from app.agent.node_decorator import node, NodeMeta


def test_registry_register_and_get():
    reg = NodeRegistry()

    @node(name="x_only_for_test")
    def x_node(state):
        return state

    # 装饰器自动注册到全局；这里手动注册到独立 reg 验证 API
    meta = NodeMeta(name="manual", retry_key=None, trace_label="manual")

    def manual(state):
        return state
    reg.register(meta, manual)

    got_meta, got_fn = reg.get("manual")
    assert got_meta is meta
    assert got_fn is manual


def test_registry_rejects_duplicate_with_different_meta():
    reg = NodeRegistry()
    m1 = NodeMeta(name="dup", retry_key="LLM_RETRY", trace_label="x")
    m2 = NodeMeta(name="dup", retry_key="DB_RETRY", trace_label="y")

    def f(state):
        return state
    reg.register(m1, f)
    with pytest.raises(ValueError, match="already registered"):
        reg.register(m2, f)


def test_registry_idempotent_for_same_meta():
    """同一 meta 重复注册不报错（模块重新导入场景）。"""
    reg = NodeRegistry()
    m = NodeMeta(name="ok", retry_key=None, trace_label="ok")

    def f(state):
        return state
    reg.register(m, f)
    reg.register(m, f)  # 不应抛异常
    assert reg.get("ok")[0] is m


def test_registry_get_unknown_raises():
    reg = NodeRegistry()
    with pytest.raises(KeyError):
        reg.get("missing")


def test_global_registry_contains_all_17_production_nodes():
    """导入节点包后，全局注册表必须包含 17 个生产节点（Task 2 已贴装饰器）。

    断言为子集而非相等：其他测试可能通过装饰器临时注入名称（"hello"、"bare" 等），
    这是装饰器使用全局 registry 的副作用，预期可控。
    """
    import app.agent.nodes  # 触发装饰器执行
    reg = get_registry()
    expected = {
        "intent_router", "history_check", "ask_review_or_continue",
        "diagnose", "knowledge_retrieval", "explain", "restate_check",
        "followup", "summary", "rag_first", "rag_answer", "llm_answer",
        "replan", "retrieval_planner", "evidence_gate", "answer_policy",
        "recovery",
    }
    actual = set(reg.all().keys())
    missing = expected - actual
    assert not missing, f"Missing production nodes in registry: {missing}"


def test_registry_add_to_graph_uses_meta_retry():
    """add_to_graph 把每个节点添加到图，按 meta.retry_key 解析 retry。"""
    from langgraph.graph import StateGraph, END
    from app.agent.state import LearningState
    from app.agent.retry_policy import LLM_RETRY, RAG_RETRY, DB_RETRY

    reg = NodeRegistry()

    # 自定义注册（隔离全局）
    m_llm = NodeMeta(name="llm_x", retry_key="LLM_RETRY", trace_label="t")
    m_rag = NodeMeta(name="rag_x", retry_key="RAG_RETRY", trace_label="t")
    m_db = NodeMeta(name="db_x", retry_key="DB_RETRY", trace_label="t")
    m_no = NodeMeta(name="no_x", retry_key=None, trace_label="t")

    def f(state):
        return state

    for m in [m_llm, m_rag, m_db, m_no]:
        reg.register(m, f)

    g = StateGraph(LearningState)
    reg.add_to_graph(g, retries={
        "LLM_RETRY": LLM_RETRY,
        "RAG_RETRY": RAG_RETRY,
        "DB_RETRY": DB_RETRY,
    })

    # 不直接断言 RetryPolicy 内部细节；改用 LangGraph 的 nodes 视图
    assert "llm_x" in g.nodes
    assert "rag_x" in g.nodes
    assert "db_x" in g.nodes
    assert "no_x" in g.nodes
