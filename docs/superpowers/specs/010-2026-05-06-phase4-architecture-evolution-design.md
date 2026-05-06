# Phase 4 架构演进设计：测试修复 + 框架升级 + Multi-Agent 协作

> **本文档为 Phase 4 顶层设计（top-level spec）。**
> 拆分为 3 个子阶段：4a（测试修复）、4b（框架升级）、4c（Multi-Agent）。

- 日期：2026-05-06
- 适用阶段：Phase 4（架构演进）
- 上游基准：`docs/superpowers/specs/top-007-2026-05-01-phase3-finalization-design.md`
- 类型：架构设计 + 落地路线（顶层）

---

## 1. 背景与目标

### 1.1 当前状态（截至 2026-05-06）

1. Phase 1/2/7/3 全部交付 ✅
2. Graph V2 测试套件已完成（77 个测试，全部通过）
3. 全量回归：457 passed / 16 failed
4. 16 个失败测试均源于 **Graph V2 vs 旧路径不兼容**
5. 框架版本：
   - langchain: 1.2.13
   - langgraph: 1.1.3
   - langfuse: 2.0.0

### 1.2 本 spec 目标

1. **Phase 4a**：修复 Graph V2 相关失败测试，建立稳定基线
2. **Phase 4b**：升级框架到最新稳定版本，确保 API 兼容
3. **Phase 4c**：引入 Multi-Agent 协作框架，支持复杂协作场景

### 1.3 非目标

1. 平台化拆分（属 Phase 5 范围）
2. 基础设施升级（Kafka、Redis Streams 等）
3. 生产部署与云上扩展

---

## 2. 子阶段总览

| 子阶段 | 目标 | 预计周期 |
|--------|------|----------|
| Phase 4a | 测试修复（Graph V2 对齐） | 1-2 天 |
| Phase 4b | 框架版本升级 | 2-3 天 |
| Phase 4c | Multi-Agent 协作框架 | 3-5 天 |

---

## 3. Phase 4a：测试修复

### 3.1 问题分析

**16 个失败测试分布：**

| 文件 | 失败数 | 根因 |
|------|--------|------|
| `test_chat_flow.py` | 6 | 期望旧 `_run_impl` 路径 |
| `test_agent_replan_branch.py` | 5 | 期望旧 `SESSION_STORE` 状态 |
| `test_sessions_api.py` | 1 | API 响应格式变化 |
| `test_learning_profile_api.py` | 1 | LangGraph checkpointer 问题 |
| `test_profile_tail_api.py` | 1 | LangGraph checkpointer 问题 |
| `test_harness_engineering.py` | 1 | 模板指标格式 |

**根本原因**：
- `.env` 中 `USE_GRAPH_V2=true`
- 测试写于 Graph V2 之前，未适配新路径
- Graph V2 使用 LangGraph checkpointer，旧路径使用 `SESSION_STORE`

### 3.2 修复策略

**策略 A：迁移到 Graph V2 路径（推荐）**

- 复用 `tests/agent_v2/conftest.py` 的 fixtures
- 强制 `use_graph_v2=True`（已在 conftest 中 autouse）
- 使用 MemorySaver 避免状态污染

**策略 B：标记 skip 并记录**

- 对于无法迁移的测试，标记 `@pytest.mark.skip(reason="legacy path deprecated")`
- 在测试文件头部注释说明

### 3.3 修复清单

#### 3.3.1 test_chat_flow.py（6 tests）

**迁移方案**：

```python
# 旧代码路径
from app.agent.graph import run_learning_graph  # 已废弃

# 新代码路径（Graph V2）
from app.agent.graph_v2 import get_learning_graph_v2
from langgraph.checkpoint.memory import MemorySaver
```

**关键修改点**：

1. 替换 `run_learning_graph()` 为 `graph.invoke(state, config)`
2. 添加 `config = {"configurable": {"thread_id": session_id}}`
3. 使用 MemorySaver 作为 checkpointer

#### 3.3.2 test_agent_replan_branch.py（5 tests）

**迁移方案**：

- 复用 `tests/agent_v2/unit/test_routers.py` 的测试模式
- 对意图路由、重规划逻辑进行单元测试
- 集成测试迁移到 `tests/agent_v2/integration/`

#### 3.3.3 API 测试（3 tests）

**迁移方案**：

- `test_sessions_api.py`：确保 session 创建使用 Graph V2
- `test_learning_profile_api.py`：检查 LangGraph checkpointer 配置
- `test_profile_tail_api.py`：同上

#### 3.3.4 test_harness_engineering.py（1 test）

**迁移方案**：

- 检查模板指标格式是否与新代码兼容
- 更新断言以匹配实际输出

### 3.4 验收标准

| 指标 | 目标 |
|------|------|
| 全量回归 | 0 failed |
| 新增测试 | 复用已有 agent_v2 测试 |
| 代码覆盖率 | 不降低 |

---

## 4. Phase 4b：框架版本升级

### 4.1 目标版本

| 框架 | 当前版本 | 目标版本 | 备注 |
|------|---------|---------|------|
| langchain | 1.2.13 | 最新稳定 | 检查 breaking changes |
| langgraph | 1.1.3 | 最新稳定 | 重点关注 StateGraph API |
| langfuse | 2.0.0 | 最新稳定 | SDK v2 迁移 |

### 4.2 升级检查清单

#### 4.2.1 LangGraph 升级检查

**关键 API 变更检测**：

1. `StateGraph` 构造函数签名
2. `add_conditional_edges` 参数格式
3. `checkpointer` 配置方式
4. `invoke` / `stream` 返回值格式

**验证点**：

```python
# 确保 Graph V2 构建正常
from app.agent.graph_v2 import build_learning_graph_v2
graph = build_learning_graph_v2()

# 确保条件边正常工作
from app.agent.routers import route_by_intent
assert route_by_intent({"intent": "teach_loop"}) == "history_check"
```

#### 4.2.2 LangChain 升级检查

**关键 API 变更检测**：

1. `ChatOpenAI` 初始化参数
2. `invoke` 方法签名
3. Message 类型（`HumanMessage`、`SystemMessage`）

**验证点**：

```python
from app.services.llm import llm_service
result = llm_service.invoke("系统提示", "用户输入")
assert isinstance(result, str)
```

#### 4.2.3 Langfuse 升级检查

**关键 API 变更检测**：

1. `Langfuse` 客户端初始化
2. `trace` / `span` 创建方式
3. 回调适配器配置

**验证点**：

```python
from app.monitoring.langfuse_client import get_langfuse_client
client = get_langfuse_client()
assert client is not None
```

### 4.3 迁移步骤

1. **更新 pyproject.toml** 版本约束
2. **运行全量测试**，收集 breaking changes
3. **逐模块修复**：
   - `app/agent/graph_v2.py`
   - `app/services/llm.py`
   - `app/monitoring/`
4. **验证 SLO 门禁**：`uv run python -m slo.run_regression`

### 4.4 验收标准

| 指标 | 目标 |
|------|------|
| 全量回归 | 0 failed |
| Deprecated warnings | 0 |
| SLO 门禁 | 通过 |
| 依赖安全检查 | 无高危漏洞 |

---

## 5. Phase 4c：Multi-Agent 协作框架

### 5.1 目标

引入多 Agent 协作能力，支持复杂场景：

1. **教学 Agent**：负责知识讲解
2. **评估 Agent**：负责理解程度评估
3. **检索 Agent**：负责知识库检索

### 5.2 技术选型

| 方案 | 优点 | 缺点 | 推荐 |
|------|------|------|------|
| **LangGraph Multi-Agent** | 与现有架构一致，无新依赖 | 需要学习新模式 | ✅ 推荐 |
| CrewAI | 成熟框架，文档丰富 | 引入新依赖，架构冲突风险 | 备选 |
| AutoGen | 微软支持，功能强大 | 复杂度高，与 LangGraph 集成困难 | 不推荐 |

### 5.3 架构设计

```
┌─────────────────────────────────────────────────────────────┐
│                     Orchestrator Agent                       │
│  (意图识别、任务分配、结果汇总)                                │
└─────────────────────────────────────────────────────────────┘
                    │                    │
        ┌───────────┴──────────┐ ┌──────┴──────────┐
        ▼                      ▼ ▼                 ▼
┌───────────────┐    ┌───────────────┐    ┌───────────────┐
│ Teaching Agent│    │  Eval Agent   │    │ Retrieval Agent│
│ (知识讲解)     │    │ (理解评估)     │    │ (知识检索)      │
└───────────────┘    └───────────────┘    └───────────────┘
```

### 5.4 实现要点

#### 5.4.1 Agent 定义

```python
# app/agent/multi_agent/teaching_agent.py
from langgraph.prebuilt import create_react_agent

teaching_agent = create_react_agent(
    model=llm,
    tools=[explain_concept, generate_example],
    name="teaching_agent",
    prompt="你是一个专业的教学助手..."
)
```

#### 5.4.2 协作图构建

```python
# app/agent/multi_agent/orchestrator.py
from langgraph.graph import StateGraph, END

def build_multi_agent_graph():
    graph = StateGraph(MultiAgentState)
    
    # 添加节点
    graph.add_node("orchestrator", orchestrator_node)
    graph.add_node("teaching", teaching_agent_node)
    graph.add_node("evaluation", evaluation_agent_node)
    graph.add_node("retrieval", retrieval_agent_node)
    
    # 添加边
    graph.set_entry_point("orchestrator")
    graph.add_conditional_edges("orchestrator", route_by_task)
    # ...
    
    return graph.compile()
```

### 5.5 迁移路径

1. **保留现有 Graph V2** 作为单 Agent 模式
2. **新增 Multi-Agent 入口**：
   - `/chat/multi` API
   - 配置开关 `MULTI_AGENT_ENABLED`
3. **渐进式迁移**：先支持一个协作场景

### 5.6 验收标准

| 指标 | 目标 |
|------|------|
| 协作场景 | 至少 1 个（教学+评估） |
| 端到端测试 | 覆盖协作流程 |
| 性能 | 单次协作 < 30s |
| 文档 | Multi-Agent 架构文档 |

---

## 6. 测试策略

### 6.1 Phase 4a 测试

- 复用 `tests/agent_v2/` 测试基础设施
- 迁移旧测试到 Graph V2 路径
- 全量回归验证

### 6.2 Phase 4b 测试

- 框架升级前后对比测试
- API 兼容性测试
- SLO 门禁验证

### 6.3 Phase 4c 测试

- 新增 `tests/multi_agent/` 目录
- 单元测试：各 Agent 行为
- 集成测试：协作流程
- 性能测试：响应时间

---

## 7. 风险与应对

| 风险 | 影响 | 应对 |
|------|------|------|
| 框架升级 breaking changes | 现有代码不可用 | 逐模块升级，保持回退能力 |
| Multi-Agent 性能问题 | 用户体验下降 | 异步执行，并行 Agent |
| 测试迁移工作量超预期 | 进度延误 | 优先迁移核心测试，其余标记 skip |

---

## 8. 验收标准（spec 整体）

| 类别 | 项 | 阈值 |
|------|---|------|
| 质量 | 全量回归 | 0 failed |
| 质量 | SLO 门禁 | 通过 |
| 功能 | Multi-Agent | 至少 1 个协作场景 |
| 文档 | 架构文档 | 更新 README |

---

## 9. 落地路线图

```
Day 1-2   ┌─ Phase 4a：测试修复
          │   └─ 迁移旧测试到 Graph V2 路径
Day 3-5   ├─ Phase 4b：框架升级
          │   └─ langchain/langgraph/langfuse 升级
Day 6-10  └─ Phase 4c：Multi-Agent
              └─ 协作框架引入 + 场景实现
```

---

## 10. 与上游文档的关系

1. 本 spec 继承 Phase 3 稳定基线
2. 完成后更新顶层 spec `004-2026-04-20-rag-agent-framework-evolution-design.md` 的进度
3. 每个子阶段产出独立 plan 文件
