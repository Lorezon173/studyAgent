# BlueGraph: Python 学习辅助 Agent 项目蓝图

## 📋 项目概览

**项目名称**: learning-agent  
**项目目标**: 构建一个基于费曼学习法的 Python 学习辅助 Agent，支持高扩展性架构  
**核心理念**: 先做单 Agent + 显式工作流，再逐步扩展到 RAG、Skills、MCP

---

## 🎯 核心价值主张

学习辅助 Agent 的价值不在于"知道很多"，而在于：

1. **识别用户当前理解程度** - 诊断先验知识水平
2. **用费曼学习法重述知识点** - 用通俗、准确的语言讲解
3. **让用户"反讲给 Agent 听"** - 检验理解的深度
4. **识别知识漏洞** - 发现关键薄弱点
5. **生成追问、反例、类比和小测** - 深化理解
6. **形成本轮学习总结与后续复习建议** - 形成闭环

---

## 🏗️ 分层架构设计

### 第一层：API 层 (FastAPI)
- `/chat` - 对话主入口
- `/sessions` - 学习会话管理
- `/skills/*` - 技能接口
- `/knowledge/*` - 知识库接口
- `/eval/*` - 评测接口
- `/admin/*` - 后台运维接口

### 第二层：Agent 编排层 (LangGraph)
负责流程控制：
- **当前处于哪个学习阶段** - 状态管理
- **该不该解释、追问、出题、总结** - 工作流决策
- **是否需要调用知识检索或搜索** - 条件路由
- **是否需要进入复盘分支** - 动态决策

### 第三层：Skill / Tool 层
负责具体能力实现：
- `explain_skill` - 知识讲解
- `quiz_skill` - 出题生成
- `retrieve_skill` - 知识库检索
- `search_skill` - 网络搜索
- `assess_skill` - 答案评分
- `summarize_skill` - 学习总结

### 第四层：数据与配置层
- **数据模型** - Pydantic schemas
- **配置管理** - 环境变量与配置
- **数据存储** - PostgreSQL + SQLAlchemy
- **向量检索** - pgvector (RAG 阶段)

---

## 🔧 首版技术栈推荐

### 核心框架与库
| 组件 | 选择 | 理由 |
|------|------|------|
| **Agent 编排** | LangGraph | 图式建模、流程可追踪、后期易扩展 |
| **Web 框架** | FastAPI | 依赖注入、异步支持、类型安全 |
| **数据模型** | Pydantic | 类型验证、结构化输出、Schema 管理 |
| **数据库** | PostgreSQL | ACID、扩展性强、支持 Vector 扩展 |
| **ORM 工具** | SQLAlchemy + Alembic | 成熟、灵活、迁移友好 |
| **向量检索** | pgvector | 单一数据库、早期成本低 |
| **MCP** | 官方 Python SDK | 统一协议、未来接搜索和工具 |

### 工程工具
| 工具 | 用途 |
|------|------|
| **uv** | Python 包/项目管理 |
| **Ruff** | Linter + Formatter |
| **pytest** | 单元测试和集成测试 |
| **Docker** | 开发/测试/部署一致性 |
| **LangSmith/Phoenix** | 可观测性与评测 |
| **OpenTelemetry** | 统一 Traces/Metrics/Logs |

---

## 📁 v0.1 项目目录结构

```
learning-agent/
├─ app/
│  ├─ api/
│  │  └─ chat.py           # 对话 API 端点
│  ├─ agent/
│  │  ├─ graph.py          # LangGraph 主工作流
│  │  ├─ state.py          # 学习状态定义
│  │  └─ nodes/
│  │     ├─ diagnose.py    # 诊断节点
│  │     ├─ explain.py     # 讲解节点
│  │     ├─ restate_check.py # 复述检测节点
│  │     ├─ followup.py    # 追问节点
│  │     └─ summarize.py   # 总结节点
│  ├─ skills/
│  │  └─ base.py           # Skill 基类接口
│  ├─ services/
│  │  └─ llm.py            # LLM 统一服务层
│  ├─ models/
│  │  └─ schemas.py        # Pydantic 数据模型
│  ├─ core/
│  │  ├─ config.py         # 配置管理
│  │  └─ prompts.py        # Prompt 模板库
│  └─ main.py              # 应用入口
├─ tests/
│  └─ test_health.py       # 基础测试
├─ .env.example            # 环境变量示例
├─ pyproject.toml          # 项目依赖配置
└─ README.md               # 项目说明
```

---

## 🎓 费曼学习法工作流

v0.1 版本的学习闭环：

```
┌─────────────────────────────────────────────────────┐
│  用户输入学习主题 + 当前理解描述                        │
└─────────────────┬──────────────────────────────────┘
                  │
                  ▼
        ┌─────────────────────┐
        │  Step 1: 诊断       │
        │ 识别用户先验知识水平 │
        └─────────────┬───────┘
                      │
                      ▼
        ┌─────────────────────┐
        │  Step 2: 讲解       │
        │ 用费曼法讲解概念    │
        │ 加入类比和例子      │
        └─────────────┬───────┘
                      │
                      ▼
        ┌─────────────────────────┐
        │  Step 3: 复述检测       │
        │ 要求用户用自己的话重述  │
        │ 识别知识漏洞和误解      │
        └─────────────┬───────────┘
                      │
                      ▼
        ┌─────────────────────┐
        │  Step 4: 追问       │
        │ 基于漏洞针对性追问  │
        │ 深化薄弱点理解      │
        └─────────────┬───────┘
                      │
                      ▼
        ┌─────────────────────────┐
        │  Step 5: 总结与复习建议 │
        │ 输出本轮学习成果        │
        │ 生成复习计划            │
        └─────────────────────────┘
```

---

## 📊 六个核心能力模块

| 模块 | 职责 | 实现阶段 |
|------|------|--------|
| **知识讲解器** | 把复杂概念讲清楚，用类比和例子 | v0.1 |
| **反向讲解检测器** | 让用户复述后，判断哪里没懂 | v0.1 |
| **追问器** | 根据漏洞继续发问和举例 | v0.1 |
| **错因归纳器** | 总结误区和薄弱点 | v0.2 |
| **学习档案管理器** | 记录掌握情况、历史问题、复习建议 | v0.2 |
| **知识增强器** | 未来接入 RAG / 搜索 / 外部资料 | v0.3+ |

---

## 🔄 开发阶段规划

### Phase 0: 需求与领域建模（Week 0）
**目标**: 明确产品边界和数据模型

需要确定：
- 目标用户是谁（中学生/大学生/自学者/程序员）
- 学习材料来源是什么（用户提问/文档/教材/网页）
- 学习结果如何衡量（能否复述/做题/迁移应用）
- 每轮学习结束后要保存什么（薄弱点/关键词/错因/复习建议）

产出物：
- 功能清单
- 数据实体图
- 关键用户流程图
- 第一版评测标准

### Phase 1: 核心学习闭环（Week 1-2）
**目标**: 验证费曼学习闭环是否成立

**关键工作**:
- [ ] 建立项目仓库
- [ ] 搭好 FastAPI、日志、配置
- [ ] 建立核心数据表
- [ ] 写出 LangGraph 主工作流骨架
- [ ] 实现 5 个节点
- [ ] 完成基础单元测试

**不做什么**:
- ❌ 不要接文档、搜索、知识库
- ❌ 不要多 Agent 协作
- ❌ 不要复杂的持久化

**验证指标**:
- 用户反馈是否表示理解加深
- 复述漏洞识别的准确性
- 追问是否有针对性

### Phase 2: 记忆与用户画像系统（Week 3-4）
**目标**: 让 Agent 记住用户学习历史

**关键工作**:
- [ ] 用户长期画像建立
- [ ] 知识点掌握度追踪
- [ ] 错误模式归纳
- [ ] 复习计划生成
- [ ] 会话摘要沉淀

**为什么优先于 RAG**:
学习 Agent 和普通问答 Agent 的差别就在这里——它必须知道"这个用户以前哪里不会、这次进步了多少、下次应该复习什么"。

### Phase 3: RAG 与知识检索（Week 5-6）
**目标**: 升级为"基于指定材料辅学的导师"

**限定范围**:
- 教材、讲义、课程笔记
- PDF / Markdown / 网页

**需要做**:
- [ ] 文档解析和 chunk 切分
- [ ] Embedding 和向量存储
- [ ] 检索与重排序
- [ ] 引文回溯和出处标注
- [ ] 检索质量评测

**关键原则**:
RAG 不是"装饰功能"，而是把系统从"泛解释器"升级为"基于指定材料辅学的导师"。

### Phase 4: Skill 模块化与抽象（Week 7-8）
**目标**: 将工具层标准化，为未来扩展奠定基础

**需要做**:
- [ ] 抽象 Skill 基类和注册机制
- [ ] 所有解释、评分、出题、检索都包装成 Skill
- [ ] 每个 Skill 具备 schema、日志、评测用例、权限配置
- [ ] Agent 只面向 Skill 接口编程

**每个 Skill 的必要属性**:
```
- name: 技能名称
- description: 功能描述
- input_schema: 输入模式
- output_schema: 输出模式
- dependencies: 依赖关系
- permission_scope: 权限范围
- timeout: 超时时间
- retry_policy: 重试策略
- eval_cases: 评测用例
```

### Phase 5: MCP 接入（Week 9-10）
**目标**: 让系统能调用和被调用

**两步走**:

**第一步**: 成为 MCP Client
- 调用搜索 MCP
- 调用本地文件 MCP
- 调用文档库 MCP
- 调用笔记工具 MCP

**第二步**: 成为 MCP Server
- 开放 `explain_concept`
- 开放 `generate_quiz`
- 开放 `assess_student_answer`
- 开放 `summarize_session`
- 开放 `build_review_plan`

### Phase 6: 评测与可观测（Week 11-12）
**目标**: 工程化和生产就绪

**评测指标**:
- 对话质量评测
- 费曼闭环成功率
- 回答可理解性得分
- 检索命中率
- 幻觉率
- 学习进步度量

**监控指标**:
- 成本、延迟、失败率
- 用户满意度
- 知识掌握度提升

**工具选择**:
- **LangSmith** - 集成观测、评测、部署
- **Phoenix** - 开源 Tracing、Evaluation、Debugging
- **OpenTelemetry** - Vendor-neutral 标准
- **promptfoo** - 自动化评测与红队测试

---

## ⚙️ Skill 设计规范

每个 Skill 都是一个带契约的能力单元，而不是普通函数。

### Skill 示例

```python
class ExplainTermSkill(BaseSkill):
    name = "explain_term"
    description = "用费曼法解释一个术语或概念"
    
    input_schema = {
        "term": str,
        "audience_level": str,  # beginner, intermediate, advanced
        "include_examples": bool
    }
    
    output_schema = {
        "explanation": str,
        "analogy": str,
        "key_points": List[str],
        "follow_up_question": str
    }
    
    permission_scope = "public"
    timeout = 30
    retry_policy = {"max_retries": 2, "backoff": "exponential"}
    
    eval_cases = [...]  # 评测用例
```

### Skill 好处

- ✅ 能挂到 LangGraph 节点中
- ✅ 能包装成 MCP tools
- ✅ 能单独评测和监控
- ✅ 能做权限控制
- ✅ 能复用到别的 Agent 项目中

---

## 📌 MCP 集成策略

MCP（模型上下文协议）是连接 AI 应用与外部系统的开放标准。

### 传输方式选择

| 场景 | 传输方式 | 用途 |
|------|--------|------|
| **本地工具** | stdio | 本地进程式集成 |
| **远程服务** | Streamable HTTP | 远程搜索、线上知识服务 |

### 安全考虑

⚠️ **重点**: MCP 官方强调授权与安全问题
- 权限隔离必须一开始就设计
- 工具白名单必须严格控制
- 接外部搜索或敏感知识库时，认证机制不可少

---

## 🛠️ 最小可行版本 (v0.1) 任务清单

### 第 1 周
- [ ] 建立项目仓库
- [ ] 搭好 FastAPI、数据库、日志、配置
- [ ] 建立核心数据表：users, sessions, messages
- [ ] 写出 LangGraph 主工作流骨架
- [ ] 实现 5 个节点：diagnose, explain, restate_check, followup, summarize

### 第 2 周
- [ ] 完成首版学习会话流程
- [ ] 保存会话摘要与薄弱点
- [ ] 做基础单元测试和集成测试
- [ ] 用 Swagger 文档测试 API

### 第 3 周（可选）
- [ ] 做用户掌握度模型
- [ ] 做错因归纳系统
- [ ] 做复习建议生成
- [ ] 接入可观测（LangSmith 或 Phoenix）

### 第 4 周（可选）
- [ ] 引入文档 ingest 与 pgvector
- [ ] 做受限范围 RAG
- [ ] 给知识检索加引用返回
- [ ] 做第一版评测集

---

## ⚠️ 不建议一开始做的事

| 事项 | 原因 |
|------|------|
| ❌ **多 Agent 协作** | 前期需要教学闭环稳定性，多 Agent 复杂度太高 |
| ❌ **同时接 3 种向量库** | 早期数据量小，pgvector 足够，后期再评估 Qdrant |
| ❌ **把搜索、RAG、记忆全部揉进主流程** | 难以调试问题根源，应该分阶段隔离 |
| ❌ **Prompt 直接写死在业务函数里** | 难以维护和测试，应该集中管理 |
| ❌ **跳过评测体系直接堆功能** | 难以衡量效果，后期难以优化 |

---

## 🎁 快速开始命令

```bash
# 初始化项目（已完成）
uv init learning-agent
cd learning-agent

# 安装依赖（已完成）
uv add fastapi uvicorn pydantic pydantic-settings langgraph langchain langchain-openai python-dotenv
uv add pytest ruff --dev

# 设置环境变量
cp .env.example .env
# 编辑 .env，填入你的 OPENAI_API_KEY

# 运行项目
uv run uvicorn app.main:app --reload

# 访问 API 文档
# http://127.0.0.1:8000/docs

# 测试
uv run pytest tests/

# Linting
uv run ruff check app/
uv run ruff format app/
```

---

## 📈 成功指标

### v0.1 阶段
- [ ] API 能正常启动
- [ ] `/health` 端点返回 200
- [ ] `/chat` 端点能完整走通工作流
- [ ] 输出 5 个阶段的信息

### v0.2 阶段
- [ ] 会话能分阶段进行
- [ ] 用户数据能持久化到数据库
- [ ] 能识别和记录用户薄弱点
- [ ] 能生成个性化复习建议

### v0.3 阶段
- [ ] RAG 能准确检索相关文档
- [ ] Skill 能作为独立单元评测
- [ ] 能统计学习进度和掌握度
- [ ] 能接入外部 MCP 服务

---

## 📚 参考资源

### 官方文档
- [LangGraph Documentation](https://langchain-ai.github.io/langgraph/)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Pydantic Documentation](https://docs.pydantic.dev/)
- [MCP Protocol](https://modelcontextprotocol.io/)

### 项目内文档
- 见 `README.md` - 项目快速开始
- 见 `app/core/prompts.py` - Prompt 设计思路
- 见 `app/agent/graph.py` - 工作流设计

---

## 🤝 开发规范

### 代码风格
- 使用 Ruff 做 Linting 和 Formatting
- 行长限制 100 字符
- Python 3.12+ 类型注解

### 提交规范
- 清晰的 commit message
- 一次提交一个功能
- 包含相关测试

### 文档规范
- 每个模块都有 docstring
- 复杂逻辑添加注释
- 重要决策记录到 ARCHITECTURE.md

---

**最后更新**: 2026-03-23  
**项目状态**: 🚀 v0.1 筹备中
