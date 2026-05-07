# Phase 4b: 框架版本升级实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 升级 LangChain/LangGraph/Langfuse 到最新稳定版本，确保 API 兼容，全量测试通过。

**Architecture:** 逐框架升级，每步验证。优先升级 LangGraph（核心依赖），然后 LangChain，最后 Langfuse。每个框架升级后立即运行测试验证。

**Tech Stack:** Python 3.12, langchain, langgraph, langfuse

---

## 前置条件

- Phase 4a 已完成（全量回归 0 failed）
- 当前框架版本：
  - langchain: 1.2.13
  - langgraph: 1.1.3
  - langfuse: 2.0.0

---

## Task 0: 版本调研与备份

**Files:**
- Modify: `pyproject.toml`（备份当前版本）

- [ ] **Step 1: 查询最新稳定版本**

```bash
uv pip index versions langchain 2>&1 | head -5
uv pip index versions langgraph 2>&1 | head -5
uv pip index versions langfuse 2>&1 | head -5
```

- [ ] **Step 2: 记录当前版本约束**

```bash
cat pyproject.toml | grep -E "langchain|langgraph|langfuse"
```

- [ ] **Step 3: 创建版本升级分支**

```bash
git checkout -b feature/framework-upgrade
```

---

## Task 1: 升级 LangGraph

**Files:**
- Modify: `pyproject.toml`
- Potentially modify: `app/agent/graph_v2.py`, `app/agent/checkpointer.py`

**风险**：LangGraph 是核心依赖，API 变更可能影响图构建。

- [ ] **Step 1: 更新 pyproject.toml**

```toml
# 更新版本约束为最新
"langgraph>=1.2.0",  # 根据实际最新版本调整
"langgraph-checkpoint-sqlite>=3.0.0",  # 保持兼容
```

- [ ] **Step 2: 安装新版本**

```bash
uv sync
```

- [ ] **Step 3: 运行 Graph V2 单元测试**

```bash
PYTHONPATH=. uv run pytest tests/agent_v2/unit/ -v --tb=short
```

Expected: 全部 PASS

- [ ] **Step 4: 运行 Graph V2 集成测试**

```bash
PYTHONPATH=. uv run pytest tests/agent_v2/integration/ -v --tb=short
```

Expected: 全部 PASS

- [ ] **Step 5: 检查 API 变更**

如果测试失败，检查 LangGraph changelog：

```bash
uv run python -c "
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

# 验证核心 API 可用
print('StateGraph:', StateGraph)
print('MemorySaver:', MemorySaver)
"
```

- [ ] **Step 6: 修复 API 不兼容（如有）**

根据测试失败信息，更新：
- `app/agent/graph_v2.py` - 图构建逻辑
- `app/agent/checkpointer.py` - checkpointer 初始化

- [ ] **Step 7: 验证修复**

```bash
PYTHONPATH=. uv run pytest tests/agent_v2/ -v --tb=short
```

- [ ] **Step 8: 提交**

```bash
git add pyproject.toml uv.lock app/agent/
git commit -m "chore: 升级 langgraph 到最新版本"
```

---

## Task 2: 升级 LangChain

**Files:**
- Modify: `pyproject.toml`
- Potentially modify: `app/services/llm.py`

**风险**：LangChain 是 LLM 调用层，API 变更可能影响 invoke 方法。

- [ ] **Step 1: 更新 pyproject.toml**

```toml
"langchain>=1.3.0",  # 根据实际最新版本调整
"langchain-text-splitters>=0.3.0",
"langchain-openai>=1.2.0",
```

- [ ] **Step 2: 安装新版本**

```bash
uv sync
```

- [ ] **Step 3: 验证 LLM 服务可用**

```bash
PYTHONPATH=. uv run python -c "
from app.services.llm import llm_service
# 仅验证导入和初始化，不实际调用 LLM
print('llm_service:', llm_service)
"
```

- [ ] **Step 4: 运行涉及 LLM 的测试**

```bash
PYTHONPATH=. uv run pytest tests/agent_v2/unit/test_nodes_teach.py tests/agent_v2/unit/test_nodes_qa.py -v --tb=short
```

Expected: 全部 PASS

- [ ] **Step 5: 检查 deprecated warnings**

```bash
PYTHONPATH=. uv run pytest tests/agent_v2/ -v -W error::DeprecationWarning 2>&1 | head -50
```

Expected: 无 deprecation warning

- [ ] **Step 6: 修复 API 不兼容（如有）**

更新 `app/services/llm.py`：
- ChatOpenAI 初始化参数
- invoke 方法签名
- Message 类型导入

- [ ] **Step 7: 提交**

```bash
git add pyproject.toml uv.lock app/services/llm.py
git commit -m "chore: 升级 langchain 到最新版本"
```

---

## Task 3: 升级 Langfuse

**Files:**
- Modify: `pyproject.toml`
- Potentially modify: `app/monitoring/langfuse_client.py`, `app/monitoring/callbacks.py`

**风险**：Langfuse SDK v2 到 v3 可能有重大 API 变更。

- [ ] **Step 1: 更新 pyproject.toml**

```toml
"langfuse>=3.0.0",  # 根据实际最新版本调整
```

- [ ] **Step 2: 安装新版本**

```bash
uv sync
```

- [ ] **Step 3: 验证 Langfuse 客户端初始化**

```bash
PYTHONPATH=. uv run python -c "
from app.monitoring.langfuse_client import get_langfuse_client
client = get_langfuse_client()
print('Langfuse client:', client)
"
```

- [ ] **Step 4: 检查 API 变更文档**

查阅 Langfuse v3 迁移指南：
- 客户端初始化
- trace/span 创建方式
- 回调适配器

- [ ] **Step 5: 更新监控模块（如有 API 变更）**

更新文件：
- `app/monitoring/langfuse_client.py`
- `app/monitoring/callbacks.py`
- `app/monitoring/trace_wrapper.py`

- [ ] **Step 6: 运行全量测试**

```bash
PYTHONPATH=. uv run pytest tests/ -q --tb=no
```

Expected: 全部 PASS

- [ ] **Step 7: 提交**

```bash
git add pyproject.toml uv.lock app/monitoring/
git commit -m "chore: 升级 langfuse 到最新版本"
```

---

## Task 4: 全量验证

**Files:**
- 无文件修改

- [ ] **Step 1: 运行全量回归测试**

```bash
PYTHONPATH=. uv run pytest tests/ -v --tb=short
```

Expected: 全部 PASS

- [ ] **Step 2: 运行 SLO 门禁**

```bash
PYTHONPATH=. uv run python -m slo.run_regression
```

Expected: 通过（exit code 0）

- [ ] **Step 3: 检查 deprecated warnings**

```bash
PYTHONPATH=. uv run python -W error::DeprecationWarning -c "
from app.main import app
from app.agent.graph_v2 import build_learning_graph_v2
print('No deprecation warnings')
"
```

Expected: 无错误

- [ ] **Step 4: 依赖安全检查**

```bash
uv pip audit
```

Expected: 无高危漏洞

---

## Task 5: 更新文档

**Files:**
- Modify: `README.md`

- [ ] **Step 1: 更新 README 版本信息**

```markdown
## 2. 当前技术栈与架构

- Web/API：FastAPI（`app/main.py`）
- Agent 编排：LangGraph（`app/agent/graph_v2.py`）
- LLM 调用：langchain-openai（兼容 OpenAI 协议服务）
- 可观测：Langfuse v4（`app/monitoring/`）
- ...

### 框架版本（Phase 4b 升级后）

| 框架 | 版本 |
|------|------|
| langchain | X.Y.Z |
| langgraph | X.Y.Z |
| langfuse | X.Y.Z |
```

- [ ] **Step 2: 提交**

```bash
git add README.md
git commit -m "docs: 更新 README - Phase 4b 框架升级完成"
```

---

## Task 6: 合并到主分支

**Files:**
- 无文件修改

- [ ] **Step 1: 确认所有测试通过**

```bash
PYTHONPATH=. uv run pytest tests/ -q
```

- [ ] **Step 2: 推送变更**

```bash
git push origin feature/framework-upgrade
```

- [ ] **Step 3: 创建 PR 或直接合并**

根据项目流程，创建 PR 或直接合并到主分支。

---

## Summary

| Task | 描述 | 风险 |
|------|------|------|
| Task 0 | 版本调研与备份 | 低 |
| Task 1 | 升级 LangGraph | 中 |
| Task 2 | 升级 LangChain | 中 |
| Task 3 | 升级 Langfuse | 中 |
| Task 4 | 全量验证 | 低 |
| Task 5 | 更新文档 | 低 |
| Task 6 | 合并到主分支 | 低 |

**验收标准：**
- 全量回归：0 failed
- SLO 门禁：通过
- Deprecated warnings：0
- 安全检查：无高危漏洞
