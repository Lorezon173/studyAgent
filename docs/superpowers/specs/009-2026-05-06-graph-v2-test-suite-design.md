# Graph V2 测试套件设计

> **状态：** 设计完成，待实施
> **日期：** 2026-05-06
> **目标：** 为 Graph V2 建立完整测试覆盖，确保所有节点、路由和端到端流程的正确性

---

## 1. 背景与目标

### 1.1 背景

- Graph V2 是 Agent 编排的核心路径，包含 16 个节点和 9 个路由函数
- Phase 2-7 的所有增强都集成在 Graph V2 中
- 当前测试期望旧代码路径，未覆盖 Graph V2
- `.env` 已设置 `USE_GRAPH_V2=true`，需要确保 V2 功能正确

### 1.2 目标

1. 建立完整的单元测试覆盖（节点、路由函数）
2. 建立端到端集成测试（4 个核心流程）
3. 使用场景驱动 mock 策略，提高可维护性
4. 确保全量回归基线稳定

### 1.3 成功标准

| 指标 | 目标值 |
|------|--------|
| 单元测试覆盖 | 所有 16 个节点 + 9 个路由函数 |
| 集成测试覆盖 | 4 个核心流程 |
| 测试通过率 | 100% |
| 新增测试数量 | ~80 个 |

---

## 2. 测试结构

```
tests/
├── agent_v2/                          # 新增：Graph V2 测试目录
│   ├── conftest.py                    # 共享 fixtures + 场景加载器
│   ├── scenarios/                     # 场景配置（JSON）
│   │   ├── teach_loop.json            # 教学主线场景
│   │   ├── qa_direct.json             # QA 直答场景
│   │   ├── replan.json                # 重规划场景
│   │   └── recovery.json              # 恢复降级场景
│   ├── unit/                          # 单元测试
│   │   ├── test_nodes_teach.py        # 教学节点测试
│   │   ├── test_nodes_qa.py           # QA 节点测试
│   │   ├── test_nodes_orchestration.py # 编排节点测试
│   │   └── test_routers.py            # 路由函数测试
│   └── integration/                   # 集成测试
│       ├── test_teach_loop_flow.py    # 教学主线端到端
│       ├── test_qa_direct_flow.py     # QA 直答端到端
│       ├── test_replan_flow.py        # 重规划端到端
│       └── test_recovery_flow.py      # 恢复降级端到端
```

---

## 3. 场景驱动 Mock 策略

### 3.1 场景配置格式

```json
{
  "scenario_id": "teach_loop_basic",
  "description": "标准三阶段教学闭环",
  "mocks": {
    "llm_invoke": {
      "学习诊断助手": "用户对二分查找有基本概念，但边界条件理解不足。",
      "教学助手": "二分查找的核心是每次取中间值比较，缩小搜索范围。请你复述。",
      "学习评估助手": "复述正确，理解程度较高。",
      "追问老师": "请说明为什么数组必须有序。",
      "复盘学习成果": "已掌握二分查找基本流程，边界条件仍需加强。"
    },
    "detect_topic": {"topic": "二分查找", "changed": true, "confidence": 0.9},
    "route_intent": {"intent": "teach_loop", "confidence": 0.95}
  },
  "steps": [
    {"input": "我想学二分查找", "expected_stage": "explained"},
    {"input": "每次取中间值比较", "expected_stage": "followup_generated"},
    {"input": "因为可以排除一半", "expected_stage": "summarized"}
  ],
  "assertions": {
    "final_mastery_score": ">= 60",
    "branch_trace_phases": ["router", "diagnose", "explain", "restate_check", "followup", "summary"]
  }
}
```

### 3.2 ScenarioLoader 实现

```python
# tests/agent_v2/conftest.py
class ScenarioLoader:
    """从 JSON 文件加载测试场景配置"""
    
    def __init__(self, scenario_path: Path):
        self.config = json.loads(scenario_path.read_text(encoding="utf-8"))
    
    def get_mock(self, mock_type: str, key: str = None):
        """获取 mock 配置"""
        mocks = self.config.get("mocks", {})
        if key:
            return mocks.get(mock_type, {}).get(key)
        return mocks.get(mock_type)
    
    def apply_mocks(self, monkeypatch):
        """应用所有 mock 到测试环境"""
        # LLM invoke mock
        llm_mocks = self.get_mock("llm_invoke")
        if llm_mocks:
            def fake_invoke(system_prompt, user_prompt, stream_output=False):
                for keyword, response in llm_mocks.items():
                    if keyword in system_prompt:
                        return response
                return "默认输出"
            monkeypatch.setattr("app.services.llm.llm_service.invoke", fake_invoke)
        
        # 其他 mock...
```

---

## 4. 单元测试设计

### 4.1 节点测试

**教学节点** (`test_nodes_teach.py`)：

| 节点 | 测试点 | 数量 |
|------|--------|------|
| `history_check_node` | 有历史/无历史、历史摘要生成 | 3 |
| `diagnose_node` | 诊断输出、状态更新 | 3 |
| `explain_node` | 讲解生成、流式输出 | 3 |
| `restate_check_node` | 复述评估、理解程度判断 | 3 |
| `followup_node` | 追问生成 | 2 |
| `summarize_node` | 总结生成、掌握度评分 | 3 |
| **小计** | | **17** |

**QA 节点** (`test_nodes_qa.py`)：

| 节点 | 测试点 | 数量 |
|------|--------|------|
| `rag_first_node` | RAG 检索执行、结果解析 | 3 |
| `rag_answer_node` | 基于 RAG 回答生成 | 2 |
| `llm_answer_node` | 纯 LLM 回答生成 | 2 |
| `knowledge_retrieval_node` | 知识检索、上下文构建 | 3 |
| **小计** | | **10** |

**编排节点** (`test_nodes_orchestration.py`)：

| 节点 | 测试点 | 数量 |
|------|--------|------|
| `intent_router_node` | 意图识别、置信度设置 | 3 |
| `replan_node` | 重规划执行、计划更新 | 3 |
| `retrieval_planner_node` | 检索策略选择 | 3 |
| `evidence_gate_node` | 证据守门（pass/supplement/reject） | 3 |
| `answer_policy_node` | 回答模板选择 | 3 |
| `recovery_node` | 错误恢复、降级响应 | 3 |
| **小计** | | **18** |

### 4.2 路由函数测试 (`test_routers.py`)

| 路由函数 | 测试点 | 数量 |
|----------|--------|------|
| `route_by_intent` | teach_loop/qa_direct/replan/summary 分流 | 4 |
| `route_after_history_check` | 有历史/无历史 | 2 |
| `route_after_choice` | review/continue | 2 |
| `route_after_diagnosis` | 已掌握/需补充/正常讲解 | 3 |
| `route_after_restate` | 已理解/需重讲/追问 | 3 |
| `route_after_rag` | rag_found/llm_answer | 2 |
| `route_after_evidence_gate` | pass/reject | 2 |
| `route_on_error_or_evidence` | 错误/正常 | 2 |
| `route_on_error_or_explain` | 错误/正常 | 2 |
| **小计** | | **22** |

**单元测试总计：67 个**

---

## 5. 集成测试设计

### 5.1 教学主线流程 (`test_teach_loop_flow.py`)

| 测试用例 | 描述 |
|----------|------|
| `test_teach_loop_complete` | 完整三阶段闭环：诊断→讲解→复述→追问→总结 |
| `test_teach_loop_with_history` | 有历史记录时询问复习/继续 |
| `test_teach_loop_restate_retry` | 复述不合格时重新讲解（最多3次） |
| `test_teach_loop_topic_change` | 中途切换主题 |
| `test_teach_loop_mastery_scoring` | 掌握度评分正确性 |
| `test_teach_loop_branch_trace` | 分支追踪完整性 |

### 5.2 QA 直答流程 (`test_qa_direct_flow.py`)

| 测试用例 | 描述 |
|----------|------|
| `test_qa_direct_rag_hit` | RAG 检索命中 → 证据守门通过 → RAG 回答 |
| `test_qa_direct_rag_miss` | RAG 检索未命中 → 纯 LLM 回答 |
| `test_qa_direct_evidence_gate_reject` | 证据守门拒绝 → 降级回答 |
| `test_qa_direct_low_confidence_notice` | 低置信度时添加边界声明 |
| `test_qa_direct_citations_attached` | 引用正确附加到响应 |

### 5.3 重规划流程 (`test_replan_flow.py`)

| 测试用例 | 描述 |
|----------|------|
| `test_replan_from_start` | 首轮即重规划 |
| `test_replan_mid_session` | 中途请求重规划 |
| `test_replan_updates_current_plan` | 重规划更新当前计划 |

### 5.4 恢复降级流程 (`test_recovery_flow.py`)

| 测试用例 | 描述 |
|----------|------|
| `test_recovery_llm_timeout` | LLM 超时触发恢复 |
| `test_recovery_rag_failure` | RAG 失败触发降级 |
| `test_recovery_error_code_set` | 错误码正确设置 |
| `test_recovery_fallback_reply` | 降级响应生成 |

**集成测试总计：18 个**

---

## 6. 关键设计决策

### 6.1 强制 Graph V2 路径

```python
# tests/agent_v2/conftest.py
import pytest

@pytest.fixture(autouse=True)
def force_graph_v2(monkeypatch):
    """强制所有测试使用 Graph V2"""
    monkeypatch.setattr("app.core.config.settings.use_graph_v2", True)
    # 重置单例，确保使用新配置
    import app.agent.graph_v2 as graph_module
    graph_module._learning_graph_v2 = None
```

### 6.2 使用 MemorySaver 避免状态污染

```python
# tests/agent_v2/conftest.py
@pytest.fixture
def fresh_graph():
    """每次测试使用新的 MemorySaver checkpointer"""
    from langgraph.checkpoint.memory import MemorySaver
    from app.agent.graph_v2 import build_learning_graph_v2
    
    # 临时替换 checkpointer
    import app.agent.checkpointer as cp_module
    original = cp_module._checkpointer
    cp_module._checkpointer = MemorySaver()
    
    graph = build_learning_graph_v2()
    yield graph
    
    # 恢复
    cp_module._checkpointer = original
```

### 6.3 分支追踪验证

```python
def assert_branch_trace_phases(state, expected_phases):
    """验证 branch_trace 包含预期阶段"""
    actual_phases = [entry.get("phase") for entry in state.get("branch_trace", [])]
    for phase in expected_phases:
        assert phase in actual_phases, f"Missing phase: {phase}. Actual: {actual_phases}"
```

---

## 7. 文件清单

| 文件 | 类型 | 描述 |
|------|------|------|
| `tests/agent_v2/conftest.py` | 新增 | 共享 fixtures |
| `tests/agent_v2/scenarios/teach_loop.json` | 新增 | 教学场景配置 |
| `tests/agent_v2/scenarios/qa_direct.json` | 新增 | QA 场景配置 |
| `tests/agent_v2/scenarios/replan.json` | 新增 | 重规划场景配置 |
| `tests/agent_v2/scenarios/recovery.json` | 新增 | 恢复场景配置 |
| `tests/agent_v2/unit/test_nodes_teach.py` | 新增 | 教学节点单元测试 |
| `tests/agent_v2/unit/test_nodes_qa.py` | 新增 | QA 节点单元测试 |
| `tests/agent_v2/unit/test_nodes_orchestration.py` | 新增 | 编排节点单元测试 |
| `tests/agent_v2/unit/test_routers.py` | 新增 | 路由函数单元测试 |
| `tests/agent_v2/integration/test_teach_loop_flow.py` | 新增 | 教学集成测试 |
| `tests/agent_v2/integration/test_qa_direct_flow.py` | 新增 | QA 集成测试 |
| `tests/agent_v2/integration/test_replan_flow.py` | 新增 | 重规划集成测试 |
| `tests/agent_v2/integration/test_recovery_flow.py` | 新增 | 恢复集成测试 |

---

## 8. 验收标准

### 8.1 功能验收

- [ ] 所有 16 个节点有单元测试覆盖
- [ ] 所有 9 个路由函数有单元测试覆盖
- [ ] 4 个核心流程有集成测试覆盖
- [ ] 场景配置可加载并正确应用 mock

### 8.2 质量验收

- [ ] 新增测试全部通过
- [ ] 全量回归测试失败数不增加
- [ ] 代码覆盖率 >= 80%

### 8.3 文档验收

- [ ] `.gitignore` 白名单新测试文件
- [ ] README 更新测试说明

---

## 9. 风险与应对

| 风险 | 影响 | 应对措施 |
|------|------|----------|
| 节点内部依赖复杂 | mock 困难 | patch 节点内部调用的服务而非节点本身 |
| LangGraph checkpointer 状态残留 | 测试污染 | 每次测试使用 MemorySaver 并重置单例 |
| 场景配置维护成本 | 灵活性差 | 使用 JSON Schema 校验配置格式 |

---

## 10. 后续工作

1. 实施 `conftest.py` 和场景加载器
2. 按顺序编写单元测试
3. 编写集成测试
4. 更新 `.gitignore` 和 README
5. 运行全量回归确认基线
