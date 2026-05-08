"""Multi-Agent 路由函数。"""
from app.agent.multi_agent.state import MultiAgentState


def route_by_agent(state: MultiAgentState) -> str:
    """根据 current_agent 字段路由到对应 Agent 节点。"""
    current_agent = state.get("current_agent", "orchestrator")

    agent_map = {
        "orchestrator": "orchestrator",
        "teaching": "teaching_agent",
        "eval": "eval_agent",
        "retrieval": "retrieval_agent",
        "aggregator": "aggregator",
    }

    return agent_map.get(current_agent, "orchestrator")
