# Learning Agent - 学习辅助 Agent v0.2

A Python-based learning assistant agent powered by LangGraph, implementing Feynman learning methodology.

一个基于 LangGraph 的 Python 学习辅助 Agent，实现费曼学习法。

## 运维入口（Phase 3d）

- [Runbook 索引](../docs/runbook/00_index.md)：启停 / 回滚 / 容量 / 故障 / 发布检查
- [Observability 入口](../docs/observability/README.md)：看板 schema 与 SLO 资产链路
- [On-Call 响应](../docs/runbook/oncall_response.md)：3 个值班场景
- SLO 一键检查：`uv run python -m slo.run_regression`

## 📋 项目概览

这是一个 AI 学习辅助系统，使用费曼学习法帮助用户深入理解知识：

- **诊断** - 识别用户的先验知识水平
- **讲解** - 用通俗易懂的语言解释概念
- **复述检测** - 让用户复述以检验理解深度
- **追问** - 基于漏洞进行针对性追问
- **总结** - 输出学习成果和复习建议

## 🚀 快速开始

### 前置条件

- Python 3.12+
- OpenAI API Key

### 安装依赖

```bash
# 使用 uv（推荐）
uv sync

# 或使用 pip
pip install -r requirements.txt
```

### 环境配置

```bash
# 复制环境变量示例
cp .env.example .env

# 编辑 .env（文件位置：项目根目录 `learning-agent/.env`），填入你的 API Key
# OPENAI_API_KEY=sk-...
```

#### 使用 Kimi API 进行测试（兼容 OpenAI SDK）

本项目使用 `langchain-openai`，可以通过自定义 `OPENAI_BASE_URL` 接入兼容 OpenAI 协议的模型服务（如 Kimi）。

在 `.env` 中配置：

```env
OPENAI_API_KEY=你的KimiKey
OPENAI_MODEL=moonshot-v1-8k
OPENAI_BASE_URL=https://api.moonshot.cn/v1
```

说明：
- 默认不设置 `OPENAI_BASE_URL` 时，走 OpenAI 官方地址。
- 设置后会使用该地址发起模型调用，无需改业务代码。

### 运行应用（后端 API）

```bash
# 使用 uv
uv run uvicorn app.main:app --reload

# 或直接使用 Python
python -m uvicorn app.main:app --reload
```

访问 API 文档：http://127.0.0.1:1900/docs

### 运行 Chainlit MVP（Web 聊天）

该项目提供基于 Chainlit 的 MVP 前端壳，优先承接后端能力（聊天流、会话、技能、画像、知识检索）。

```bash
uv run chainlit run app/ui/chainlit_app.py --host 0.0.0.0 --port 2554 -w
```

浏览器访问：http://127.0.0.1:2554

说明：
- 启动 Chainlit 前，请先启动 FastAPI（默认 `http://127.0.0.1:1900`）。
- 可通过 `.env` 中 `BACKEND_BASE_URL` 调整后端地址。
- 默认端口固定为 `2554`（可通过 `CHAINLIT_PORT` 覆盖）。
- 右上角提供“知识库创建”按钮：前端会直接调用 FastAPI 上传接口（默认 `http://127.0.0.1:1900/api/knowledge_base/upload`），文件不经过 Chainlit Python 转发。
- 若需修改上传接口地址，可在浏览器控制台设置：
  - `localStorage.setItem("LA_KB_UPLOAD_ENDPOINT", "你的上传接口地址")`
- JWT Token 默认从本地存储键中读取：`LA_ADMIN_JWT`、`access_token`、`token`、`jwt`、`Authorization`（若使用 Cookie 鉴权，前端会自动携带 `credentials: include`）。

### 命令行聊天界面（CLI）

你可以像 `claude-code` 一样直接在终端进行交互（不需要先启动 HTTP 服务）：

```bash
uv run python main.py
```

常用命令：

```text
/help
/session new
/topic set 二分查找
/chat 我想学习二分查找
/profile overview
/plan show
/trace
/skills
/exit
```

说明：
- 直接输入文本也会发送到当前会话。
- 采用命令注册机制，后续新增命令只需扩展 `app/cli/repl.py`。
- CLI 与 API 复用同一服务层，便于后续扩展与维护。

## 📚 API 文档

### 健康检查

```
GET /health
```

响应示例：
```json
{
  "status": "ok",
  "app": "learning-agent"
}
```

### 学习对话

```
POST /chat
```

请求体示例：
```json
{
  "session_id": "s1",
  "user_id": "u1",
  "topic": "什么是二分查找",
  "user_input": "我想学习二分查找，但我只知道它和有序数组有关"
}
```

响应示例：
```json
{
  "session_id": "s1",
  "stage": "summarized",
  "reply": "...",
  "summary": "...",
  "citations": []
}
```

### 知识库（RAG）

```
POST /knowledge/ingest
POST /knowledge/retrieve
```

- `ingest` 支持 `source_type=text|image`。
- `image` 会先进入 OCR 文本化处理，再按统一切块/检索链路入库。
- 支持双轨知识：`scope=global|personal`。
- `scope=personal` 时，`user_id` 必填，并在检索时强隔离同一用户数据。
- `retrieve` 返回匹配片段及来源元数据，可用于回答引用。
- 检索流程采用 BM25 + Dense 双路召回，经 RRF 融合后再 rerank（默认 simple，可切换 bge）。
- `profile` 路由顺序已调整，优先匹配固定路径（如 `/profile/overview`），规避参数路由遮蔽风险。

## 📂 项目结构

```
learning-agent/
├─ app/
│  ├─ api/               # API 端点
│  │  └─ chat.py
│  ├─ agent/             # LangGraph 工作流
│  │  ├─ graph.py
│  │  └─ state.py
│  ├─ skills/            # 技能模块（预留）
│  │  └─ base.py
│  ├─ services/          # 服务层
│  │  └─ llm.py
│  ├─ models/            # Pydantic 数据模型
│  │  └─ schemas.py
│  ├─ core/              # 核心配置
│  │  ├─ config.py
│  │  └─ prompts.py
│  └─ main.py            # 应用入口
├─ tests/                # 测试
├─ .env.example          # 环境变量示例
├─ pyproject.toml        # 项目配置
└─ README.md             # 本文件
```

## 🧪 测试

```bash
# 运行所有测试
uv run pytest

# 运行特定测试
uv run pytest tests/test_health.py

# 显示覆盖率
uv run pytest --cov=app tests/
```

## 🔍 代码规范

```bash
# 使用 Ruff 检查代码
uv run ruff check app/

# 自动格式化代码
uv run ruff format app/
```

## 🏗️ 当前开发阶段

**v0.2 - 学习档案与可查询能力已完成**

### ✅ 已完成（v0.1 + v0.2）
- 费曼学习法核心工作流（诊断→讲解→复述检测→追问→总结）
- 多轮会话流转（A/B/C 阶段）
- 分层架构：`api -> agent_service -> graph`
- 会话管理 API（`/sessions` 查询、详情、清理）
- 会话存储后端切换（`memory/sqlite`）
- Skill 注册与查询（registry + 内置技能 + `/skills`）
- 学习档案沉淀（summary/mastery/errors/review）
- Profile 查询 API：
  - `/profile/{session_id}`
  - `/profile/{session_id}/summary`
  - `/profile/{session_id}/mastery`
  - `/profile/{session_id}/errors`
  - `/profile/{session_id}/review-plan`
- v0.2 收尾查询 API：
  - `/profile/overview`
  - `/profile/topic/{topic}`
  - `/profile/topic/{topic}/memory`
  - `/profile/session/{session_id}/timeline`
- worklog 全流程留痕 + 模块手动测试手册 + 总测试导航 `worklog/TEST_INDEX.md`

### ⏳ 尚未完成（后续版本）
- RAG（文档 ingest/chunking/embedding/retriever）
- MCP Client / Server 集成
- 更完善的观测与评测体系（LangSmith/Phoenix/OTel）
- 数据层升级到 PostgreSQL + SQLAlchemy + Alembic

## 📈 未来规划

- **v0.3**: RAG、文档检索、pgvector 集成、MCP 初步接入
- **v0.4**: Skill 模块化、权限控制
- **v0.5**: MCP 集成、外部服务调用
- **v1.0**: 完整评测体系、生产就绪

详见 [bluegraph.md](./bluegraph.md)

## 📝 配置说明

### 环境变量

| 变量 | 说明 | 示例 |
|------|------|------|
| `OPENAI_API_KEY` | OpenAI API 密钥 | sk-... |
| `OPENAI_MODEL` | 使用的模型 | gpt-4.1-mini |
| `OPENAI_BASE_URL` | 模型服务地址（用于 Kimi 等兼容 OpenAI 协议服务） | https://api.moonshot.cn/v1 |
| `LLM_TIMEOUT_SECONDS` | LLM 调用超时秒数 | 30 |
| `LLM_MAX_RETRIES` | LLM 最大重试次数 | 2 |
| `LLM_RETRY_BACKOFF_SECONDS` | LLM 重试退避基数秒 | 0.5 |
| `APP_NAME` | 应用名称 | learning-agent |
| `DEBUG` | 调试模式 | true |
| `SESSION_STORE_BACKEND` | 会话存储后端（memory/sqlite） | memory |
| `SESSION_SQLITE_PATH` | sqlite 会话库文件路径 | data/sessions.db |
| `PERSONAL_RAG_STORE_PATH` | 个人长期记忆（JSONL）落盘路径 | data/personal_rag.jsonl |
| `RAG_ENABLED` | 是否启用知识检索上下文注入 | false |
| `RAG_STORE_PATH` | 知识切块 JSONL 存储路径 | data/knowledge_chunks.jsonl |
| `RAG_DEFAULT_CHUNK_SIZE` | 知识切块大小 | 500 |
| `RAG_DEFAULT_CHUNK_OVERLAP` | 知识切块重叠长度 | 100 |
| `RAG_RETRIEVE_TOP_K` | 每轮注入的检索证据数量 | 3 |
| `RAG_OCR_ENGINE` | OCR 引擎（simple/paddleocr） | simple |
| `RAG_EMBEDDING_PROVIDER` | embedding 实现（simple/sentence_transformers） | simple |
| `RAG_EMBEDDING_DIM` | simple embedding 维度 | 128 |
| `RAG_RERANK_PROVIDER` | 重排实现（simple/bge） | simple |
| `RAG_RRF_K` | RRF 排名常数 | 60 |
| `RAG_RRF_RANK_WINDOW_SIZE` | RRF 每路参与融合的窗口大小 | 100 |
| `RAG_RERANK_TOP_N` | 进入重排的候选数量 | 10 |
| `BACKEND_BASE_URL` | Chainlit 调用后端 API 的基地址 | http://127.0.0.1:1900 |
| `CHAINLIT_HOST` | Chainlit 监听地址 | 0.0.0.0 |
| `CHAINLIT_PORT` | Chainlit 监听端口 | 2554 |
| `CHAINLIT_AUTH_SECRET` | Chainlit 登录认证 JWT 密钥（启用右上角登录必填） | your-random-secret |

知识库接口关键字段补充：

- `POST /knowledge/ingest` 新增 `scope`（默认 `global`）与 `user_id`（`personal` 时必填）
- `POST /knowledge/retrieve` 新增 `scope`（默认 `global`）与 `user_id`（`personal` 时必填）

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

## 📄 许可证

MIT License

## 📚 参考资源

- [LangGraph Documentation](https://langchain-ai.github.io/langgraph/)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Pydantic Documentation](https://docs.pydantic.dev/)

---

**项目状态**: 🚀 v0.2 功能开发完成（待统一测试）  
**最后更新**: 2026-03-23
