"""Graph V2 测试共享 fixtures 和工具函数。"""
import json
import pytest
from pathlib import Path
from langgraph.checkpoint.memory import MemorySaver


class ScenarioLoader:
    """从 JSON 文件加载测试场景配置。"""

    def __init__(self, scenario_path: Path):
        self.config = json.loads(scenario_path.read_text(encoding="utf-8"))

    def get_mock(self, mock_type: str, key: str = None):
        """获取 mock 配置。"""
        mocks = self.config.get("mocks", {})
        if key:
            return mocks.get(mock_type, {}).get(key)
        return mocks.get(mock_type)

    def get_steps(self):
        """获取测试步骤。"""
        return self.config.get("steps", [])

    def get_assertions(self):
        """获取断言配置。"""
        return self.config.get("assertions", {})


@pytest.fixture(autouse=True)
def force_graph_v2(monkeypatch):
    """强制所有测试使用 Graph V2。"""
    monkeypatch.setattr("app.core.config.settings.use_graph_v2", True)
    # 重置单例
    import app.agent.graph_v2 as graph_module
    graph_module._learning_graph_v2 = None


@pytest.fixture
def fresh_graph():
    """每次测试使用新的 MemorySaver checkpointer。"""
    import app.agent.checkpointer as cp_module
    from app.agent.graph_v2 import build_learning_graph_v2

    original = cp_module._checkpointer
    cp_module._checkpointer = MemorySaver()

    graph = build_learning_graph_v2()
    yield graph

    cp_module._checkpointer = original
    import app.agent.graph_v2 as graph_module
    graph_module._learning_graph_v2 = None


@pytest.fixture
def scenario_loader(request):
    """加载场景配置的 fixture。"""
    scenario_name = request.param
    scenario_path = Path(__file__).parent / "scenarios" / f"{scenario_name}.json"
    return ScenarioLoader(scenario_path)


def assert_branch_trace_phases(state, expected_phases):
    """验证 branch_trace 包含预期阶段。"""
    actual_phases = [entry.get("phase") for entry in state.get("branch_trace", [])]
    for phase in expected_phases:
        assert phase in actual_phases, f"Missing phase: {phase}. Actual: {actual_phases}"


def make_fake_invoke(mocks: dict):
    """生成基于关键词匹配的 fake_invoke 函数。"""
    def fake_invoke(system_prompt: str, user_prompt: str, stream_output: bool = False) -> str:
        for keyword, response in mocks.items():
            if keyword in system_prompt:
                return response
        return "默认输出"
    return fake_invoke
