"""节点包：按职责拆分但保留 from app.agent.nodes import xxx_node 兼容性。

After Phase 4: split into teach.py / qa.py / orchestration.py.
This package's __init__ re-exports every public node so existing imports
and graph_v2.py do not change.
"""
# IMPORTANT: 这些显式 import 同时触发 @node 装饰器，
# 使节点在 NodeRegistry 中注册。不要删除——graph_v2.py 通过
# register_all_nodes() 依赖此处的副作用。
#
# 测试 patch 注意：`patch("app.agent.nodes.xxx_node")` 重绑模块属性，
# 但 NodeRegistry 已捕获装饰时的函数引用。已编译图（即调用过
# build_learning_graph_v2() 之后）不会看到这种 patch 的效果。
# 测试如需替换节点行为，请 patch 节点函数内部使用的依赖（如
# `app.services.llm.llm_service.invoke`、
# `app.services.rag_coordinator.execute_retrieval_tools`）。
from app.agent.nodes.teach import (
    history_check_node,
    ask_review_or_continue_node,
    diagnose_node,
    explain_node,
    restate_check_node,
    followup_node,
    summarize_node,
)
from app.agent.nodes.qa import (
    rag_first_node,
    rag_answer_node,
    llm_answer_node,
    knowledge_retrieval_node,
)
from app.agent.nodes.orchestration import (
    intent_router_node,
    replan_node,
    retrieval_planner_node,
    evidence_gate_node,
    answer_policy_node,
    recovery_node,
)

# Re-export commonly mocked module-level attributes so existing test patches
# like patch("app.agent.nodes.llm_service.invoke", ...) still resolve.
from app.services.llm import llm_service
from app.services.rag_coordinator import decide_rag_call, execute_rag

__all__ = [
    "history_check_node", "ask_review_or_continue_node", "diagnose_node",
    "explain_node", "restate_check_node", "followup_node", "summarize_node",
    "rag_first_node", "rag_answer_node", "llm_answer_node", "knowledge_retrieval_node",
    "intent_router_node", "replan_node",
    "retrieval_planner_node", "evidence_gate_node", "answer_policy_node", "recovery_node",
    "llm_service", "decide_rag_call", "execute_rag",
    "register_all_nodes",
]


def register_all_nodes() -> None:
    """显式触发节点注册的入口点。

    本模块的顶部 import 已经触发所有 @node 装饰器（执行期注册）。
    本函数本身是 no-op；它的存在是为了让 graph_v2.py 等调用方
    通过显式函数调用 *grep 得到* 这一依赖关系，避免被
    "remove unused imports" 类的工具误删。
    """
    return None
