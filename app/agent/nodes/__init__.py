"""节点包：按职责拆分但保留 from app.agent.nodes import xxx_node 兼容性。

After Phase 4: split into teach.py / qa.py / orchestration.py.
This package's __init__ re-exports every public node so existing imports
and graph_v2.py do not change.
"""
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
]
