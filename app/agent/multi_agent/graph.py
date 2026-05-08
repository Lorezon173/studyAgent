"""Multi-Agent 协作图构建。"""
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from app.agent.multi_agent.state import MultiAgentState
from app.agent.multi_agent.orchestrator import orchestrator_node, aggregator_node
from app.agent.multi_agent.teaching_agent import teaching_agent_node
from app.agent.multi_agent.eval_agent import eval_agent_node
from app.agent.multi_agent.retrieval_agent import retrieval_agent_node
from app.agent.multi_agent.routers import route_by_agent


def build_multi_agent_graph():
    """构建 Multi-Agent 协作图。

    流程：orchestrator → retrieval/teaching/eval → aggregator → END
    """
    graph = StateGraph(MultiAgentState)

    # 添加节点
    graph.add_node("orchestrator", orchestrator_node)
    graph.add_node("retrieval_agent", retrieval_agent_node)
    graph.add_node("teaching_agent", teaching_agent_node)
    graph.add_node("eval_agent", eval_agent_node)
    graph.add_node("aggregator", aggregator_node)

    # 入口
    graph.set_entry_point("orchestrator")

    # orchestrator → 条件分支
    graph.add_conditional_edges(
        "orchestrator",
        route_by_agent,
        {
            "retrieval_agent": "retrieval_agent",
            "teaching_agent": "teaching_agent",
            "eval_agent": "eval_agent",
        },
    )

    # retrieval → teaching
    graph.add_edge("retrieval_agent", "teaching_agent")

    # teaching → eval
    graph.add_edge("teaching_agent", "eval_agent")

    # eval → aggregator
    graph.add_edge("eval_agent", "aggregator")

    # aggregator → END
    graph.add_edge("aggregator", END)

    return graph.compile(checkpointer=MemorySaver())


_multi_agent_graph = None


def get_multi_agent_graph():
    """获取 Multi-Agent 图单例。"""
    global _multi_agent_graph
    if _multi_agent_graph is None:
        _multi_agent_graph = build_multi_agent_graph()
    return _multi_agent_graph


def reset_multi_agent_graph():
    """重置图单例（用于测试）。"""
    global _multi_agent_graph
    _multi_agent_graph = None
