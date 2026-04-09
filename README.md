# Learning Agent（学习辅助 Agent）项目现状与进度说明

本项目是一个面向学习场景的 Agent 系统，核心目标是将“提问—理解—复述—纠偏—总结”做成可持续迭代、可追踪的学习闭环。  
当前代码已从 v0.1 原型演进到 **v0.2（含 RAG 双轨与工具路由能力）**，并进入 **P0 稳定性收口阶段**。

---

## 1. 项目定位

Learning Agent 以费曼学习法为主线，提供以下核心流程：

1. 诊断用户已有认知
2. 用更易理解的方式讲解
3. 要求用户复述并评估理解程度
4. 针对错误点追问与补救
5. 输出总结与复习建议

系统不是“单轮聊天助手”，而是“可沉淀学习轨迹”的学习编排系统。

---

## 2. 当前技术栈与架构

- Web/API：FastAPI
- Agent 编排：LangGraph
- LLM 调用：langchain-openai（兼容 OpenAI 协议服务）
- 数据模型：Pydantic + TypedDict
- 存储：
  - 会话：memory / sqlite（可切换）
  - RAG：JSONL + 内存索引（当前实现）
  - 用户：SQLite
- 前端交互：
  - CLI（`main.py` -> `app/cli/repl.py`）
  - Chainlit MVP（`app/ui/chainlit_app.py`）

分层结构（当前代码）：

- `app/api/`：`chat`、`knowledge`、`sessions`、`skills`、`profile`、`auth`
- `app/services/`：`agent_service`、`agent_runtime`、`evaluation_service`、`rag_service`、`tool_executor` 等
- `app/services/orchestration/`：`context_builder`、`stage_orchestrator`、`persistence_coordinator`
- `app/agent/`：学习状态与子图执行
- `app/skills/`：技能注册与内置检索技能

---

## 3. 当前已落地能力（代码与文档一致）

### 3.1 学习主链路

- 多轮学习会话（阶段推进）
- 意图路由分支（teach_loop / qa_direct / review / replan）
- 自动重规划分支与分支轨迹记录（`branch_trace`）

### 3.2 RAG 能力（已从基础版升级）

- 入库：`text` / `image`（图片走 OCR）
- 检索：`global` / `personal` 双轨
- 隔离：`personal` 强制 `user_id`，实现用户级隔离
- 算法：BM25 + Dense + RRF + rerank
- Chat 注入：返回 `citations`，包含 `tool/scope/user_id` 等元信息

### 3.3 用户与会话能力

- 用户注册 / 登录（`/auth/register`、`/auth/login`）
- 会话列表、详情、清理（`/sessions`）
- 学习档案与聚合查询（`/profile/*`）

### 3.4 工具化检索与扩展

- 已有工具技能：
  - `search_local_textbook`
  - `search_personal_memory`
  - `search_web`（provider 可插拔，默认 stub/mock）
- `tool_route + tool_executor` 已接入主执行链路

### 3.5 交互层

- CLI 命令式交互（支持 `/plan show`、`/trace`）
- Chainlit MVP（默认 2554 端口）
- 前端知识库上传交互（直连后端上传接口的方案已记录并接入前端脚本）

---

## 4. 里程碑进度

### 已完成主线（001~025 + 2026-03-24 模块）

- 001：整理 `plan/` 与 RAG 实施方案
- 002~005：RAG 图文统一检索基础、中文召回修复、OCR/embedding/重排能力落地
- 006~009：架构演进修复、编排职责拆分、LLM 结构化评估接入
- 010~012：RAG 双轨隔离、混合检索升级、用户体系与 `user_id` 全链路
- 013~018：qa 子图流转、retriever 抽象、工具化入口与 route/executor/web provider 接入
- 019~020：Chainlit MVP 接入与交互优化
- 021~025：知识库管理与上传方案持续完善（含文件上传入库与前端上传能力）
- 2026-03-24：自动分支与自动重规划能力（agent runtime）落地

### 当前阶段结论

项目已经完成从“原型学习闭环”到“可检索、可隔离、可追踪”的 v0.2 核心闭环，进入稳定性与质量收口阶段。

---

## 5. 当前测试与可观测状态

- `tests/` 下已具备较完整测试集（chat、knowledge、skills、sessions、profile、auth、tool 路由等）
- 新增全流程观测脚本：`tests/full_flow_observer.py`
- 测试留痕与手动验收索引：`worklog/TEST_INDEX.md`

---

## 6. 仍在推进 / 下一步重点（P0 -> P1）

依据 `plan/P0-稳定性收口计划.md`，当前重点为：

1. 回归矩阵与基线锁定（核心链路全量回归）
2. 多用户隔离与权限边界补强（越权、串号、会话绑定）
3. 工具路由与执行链路一致性验证（含无结果回退）
4. 错误处理语义统一（避免 silent failure）
5. 文档与代码状态持续对齐

后续演进方向：

- 更稳定的检索底座（保留 Retriever 接口、逐步替换 JSONL 内核）
- 更系统化的检索评测指标与观测体系
- MCP / ToolNode 深化（在稳定性基线后推进）

---

## 7. 快速启动（当前推荐）

### 7.1 安装依赖

```bash
uv sync
```

### 7.2 启动后端 API

```bash
uv run uvicorn app.main:app --host 0.0.0.0 --port 1900 --reload
```

文档地址：`http://127.0.0.1:1900/docs`

### 7.3 启动 CLI

```bash
uv run python main.py
```

### 7.4 启动 Chainlit MVP

```bash
uv run chainlit run app/ui/chainlit_app.py --host 0.0.0.0 --port 2554 -w
```

访问地址：`http://127.0.0.1:2554`

---

## 8. 关键文档索引（建议阅读顺序）

1. `plan/README.md`（历史主说明）
2. `plan/架构演进.md`（目标架构蓝图）
3. `plan/架构修改建议.md`（结合实际代码的落地路径）
4. `plan/RAG实现现状详解.md`（当前 RAG 事实基线）
5. `plan/用户功能使用说明.md`（用户侧操作）
6. `plan/P0-稳定性收口计划.md`（当前阶段任务）
7. `worklog/README.md` 与 `worklog/TEST_INDEX.md`（迭代与测试留痕入口）

---

## 9. 项目现状一句话总结

**Learning Agent 当前已完成 v0.2 核心功能闭环：学习编排 + 双轨 RAG + 工具路由 + 用户隔离 + CLI/Chainlit 双入口，正在进行 P0 稳定性收口，目标是进入更高可靠性的下一阶段。**

