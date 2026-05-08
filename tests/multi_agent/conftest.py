"""Multi-Agent 测试 fixtures。"""
import pytest
from app.agent.multi_agent.graph import reset_multi_agent_graph


@pytest.fixture(autouse=True)
def reset_graph():
    """每个测试前重置图单例，避免状态污染。"""
    reset_multi_agent_graph()
    yield
    reset_multi_agent_graph()
