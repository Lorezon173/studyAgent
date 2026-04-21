# 编排增强（Phase 2）设计文档

> **状态：** 已交付 ✅
> **开始日期：** 2026-04-21
> **结束日期：** 2026-04-21
> **所属项目：** LearningAgent 12周框架改进
> **前置依赖：** Phase 1 已交付 ✅

---

## 1. 背景与目标

### 1.1 背景

基于 `004-2026-04-20-rag-agent-framework-evolution-design.md` 的12周架构演进规划，Phase 2 聚焦于**编排增强**，在 Phase 1（RAG质量冲刺）交付的基础上，升级 Agent 编排能力。

### 1.2 目标

1. 实现检索策略动态规划节点（`retrieval_planner_node`）
2. 实现证据守门节点（`evidence_gate`）
3. 实现回答策略节点（`answer_policy_node`）
4. 实现统一恢复节点（`recovery_node`）
5. 完成第二轮端到端回归与链路压测

### 1.3 成功标准

| 指标 | 目标值 |
|------|--------|
| 检索策略选择准确率 | >= 90% |
| 证据覆盖度检测准确率 | >= 85% |
| 恢复成功率 | >= 80% |
| 端到端测试通过率 | 100% |

---

## 2. 范围与约束

### 2.1 范围（In Scope）

1. 新增 4 个编排节点并集成到 Graph V2
2. 状态字段扩展与路由逻辑增强
3. 错误分类与恢复策略实现
4. 回答模板库与边界声明机制

### 2.2 约束（Out of Scope）

1. 不替换现有 LangGraph/FastAPI/Celery/Redis 主干技术
2. 不引入多 Agent 协作框架
3. 不涉及 SLO 自动化守门（Phase 3 范围）

### 2.3 对 Phase 1 的依赖（已解除 ✅）

| 依赖项 | 所属周次 | 用途 | 状态 |
|--------|----------|------|------|
| `QueryPlan` 数据类 | Phase 1 W1 | 查询模式识别 | ✅ 已交付 |
| `evaluate_evidence()` | Phase 1 W2 | 证据置信评估 | ✅ 已交付 |
| `rag_confidence_level` 状态字段 | Phase 1 W4 | 置信度路由 | ✅ 已交付 |

**Phase 1 交付的关键模块：**
- `app/services/query_planner.py` - `QueryPlan` 数据类 + `build_query_plan()` 函数
- `app/services/evidence_policy.py` - `EvidenceAssessment` 数据类 + `evaluate_evidence()` 函数
- 状态字段：`rag_confidence_level`, `rag_low_evidence`, `rag_avg_score`

---

## 3. 架构设计

### 3.1 新增节点

| 节点名称 | 职责 | 输入 | 输出 |
|----------|------|------|------|
| `retrieval_planner_node` | 动态选择检索策略组合 | query_plan, topic, user_id | retrieval_strategy |
| `evidence_gate` | 证据覆盖度、冲突度校验 | rag_context, evidence_meta | gate_result, confidence_level |
| `answer_policy_node` | 依据置信等级选择回答模板 | gate_result, user_input | answer_template, boundary_notice |
| `recovery_node` | 统一失败恢复与降级 | error_info, stage | recovery_action, fallback_reply |

### 3.2 图结构变更

**当前路径：**
```
intent_router -> rag_first -> rag_answer/llm_answer -> END
```

**增强后路径：**
```
intent_router -> retrieval_planner_node -> rag_first -> evidence_gate
    -> answer_policy_node -> rag_answer/llm_answer -> END
```

**异常路径：**
```
任意节点失败 -> recovery_node -> 降级响应 -> END
```

### 3.3 状态字段新增

| 字段 | 类型 | 用途 |
|------|------|------|
| `retrieval_strategy` | dict | 检索策略配置 |
| `gate_result` | str | 证据守门结果（pass/supplement/reject） |
| `answer_template` | str | 回答模板标识 |
| `boundary_notice` | str | 边界声明文本 |
| `recovery_action` | str | 恢复动作类型 |
| `fallback_triggered` | bool | 是否触发降级 |
| `error_code` | str | 错误码 |
| `retry_trace` | list | 重试轨迹 |

---

## 4. 周次规划

### 4.1 W5（2026-04-21 ~ 2026-04-27）：检索规划节点

**主题：** `retrieval_planner_node` 落地

**依赖关系：**
- ✅ Phase 1 的 `query_planner.py` 已交付
- 可直接使用 `QueryPlan.mode` 字段确定检索策略

**新增/修改文件：**
```
app/agent/nodes.py                           # 修改：新增 retrieval_planner_node 函数
app/services/retrieval_strategy.py           # 新增：策略配置
tests/test_retrieval_planner_node.py         # 新增：节点测试
```

**核心实现：**
```python
# app/services/retrieval_strategy.py
RETRIEVAL_STRATEGIES = {
    "fact": {
        "bm25_weight": 0.4,
        "vector_weight": 0.6,
        "web_enabled": False,
        "top_k": 3,
    },
    "freshness": {
        "bm25_weight": 0.2,
        "vector_weight": 0.3,
        "web_enabled": True,
        "top_k": 5,
    },
    "comparison": {
        "bm25_weight": 0.5,
        "vector_weight": 0.5,
        "web_enabled": False,
        "top_k": 5,
    },
}


def get_retrieval_strategy(mode: str) -> dict:
    """根据查询模式返回检索策略"""
    return RETRIEVAL_STRATEGIES.get(mode, RETRIEVAL_STRATEGIES["fact"])
```

**验收标准：**
- [ ] 根据查询模式返回正确的检索策略
- [ ] 支持策略热更新（配置化）
- [ ] 单测覆盖率 >= 90%
- [ ] 集成到 Graph V2 并通过路由测试

---

### 4.2 W6（2026-04-28 ~ 2026-05-04）：证据守门节点

**主题：** `evidence_gate` 守门节点落地

**依赖关系：**
- ✅ Phase 1 的 `evidence_policy.py` 已交付
- 可直接使用 `evaluate_evidence()` 函数计算证据置信等级

**新增/修改文件：**
```
app/agent/nodes.py                           # 修改：新增 evidence_gate_node 函数
app/services/evidence_validator.py           # 新增：验证逻辑
tests/test_evidence_gate_node.py             # 新增：节点测试
```

**核心逻辑：**
```python
# app/services/evidence_validator.py
from dataclasses import dataclass


@dataclass
class GateResult:
    status: str  # pass / supplement / reject
    coverage_score: float  # 0.0 ~ 1.0
    conflict_score: float  # 0.0 ~ 1.0
    missing_keywords: list[str]
    conflict_pairs: list[tuple]


def validate_evidence(
    query: str,
    evidence_chunks: list[dict],
    min_coverage: float = 0.7,
    max_conflict: float = 0.3,
) -> GateResult:
    """
    验证证据质量

    检查项：
    1. 覆盖度：证据是否覆盖查询关键词
    2. 冲突度：证据之间是否存在矛盾
    """
    # 1. 提取查询关键词
    keywords = extract_keywords(query)

    # 2. 计算覆盖度
    covered = set()
    for chunk in evidence_chunks:
        text = chunk.get("text", "").lower()
        covered.update(kw for kw in keywords if kw.lower() in text)

    coverage_score = len(covered) / len(keywords) if keywords else 0.0
    missing_keywords = [kw for kw in keywords if kw not in covered]

    # 3. 检测冲突（简化实现）
    conflict_score = detect_conflicts(evidence_chunks)
    conflict_pairs = []

    # 4. 决策
    if coverage_score >= min_coverage and conflict_score <= max_conflict:
        status = "pass"
    elif coverage_score >= 0.4:
        status = "supplement"
    else:
        status = "reject"

    return GateResult(
        status=status,
        coverage_score=coverage_score,
        conflict_score=conflict_score,
        missing_keywords=missing_keywords,
        conflict_pairs=conflict_pairs,
    )
```

**验收标准：**
- [ ] 覆盖度计算准确率 >= 85%
- [ ] 冲突检测误报率 <= 10%
- [ ] 守门延迟 <= 100ms
- [ ] 三级守门决策正确率 >= 90%

---

### 4.3 W7（2026-05-05 ~ 2026-05-11）：回答策略节点

**主题：** `answer_policy_node` 与回答模板落地

**依赖关系：**
- ✅ Phase 1 的 `rag_confidence_level` 状态字段已交付
- 可直接使用置信等级选择回答模板

**新增/修改文件：**
```
app/agent/nodes.py                           # 修改：新增 answer_policy_node 函数
app/services/answer_templates.py             # 新增：回答模板库
tests/test_answer_policy_node.py             # 新增：节点测试
```

**核心实现：**
```python
# app/services/answer_templates.py
from dataclasses import dataclass


@dataclass
class AnswerTemplate:
    template_id: str
    content: str
    boundary_notice: str


ANSWER_TEMPLATES = {
    "high_confidence": AnswerTemplate(
        template_id="high",
        content="{answer}\n\n参考来源：{citations}",
        boundary_notice="",
    ),
    "medium_confidence": AnswerTemplate(
        template_id="medium",
        content="{answer}",
        boundary_notice="基于已有信息回答，建议结合教材核实。",
    ),
    "low_confidence": AnswerTemplate(
        template_id="low",
        content="{answer}",
        boundary_notice="【重要】当前证据不足，以下为推测性回答，请查阅权威资料确认。",
    ),
}


def get_answer_template(confidence_level: str) -> AnswerTemplate:
    """根据置信等级返回回答模板"""
    return ANSWER_TEMPLATES.get(
        confidence_level,
        ANSWER_TEMPLATES["medium"]
    )
```

**验收标准：**
- [ ] 三级置信度对应不同模板
- [ ] 边界声明自动拼接
- [ ] 模板内容可配置
- [ ] 低置信度回答必须包含边界声明

---

### 4.4 W8（2026-05-12 ~ 2026-05-18）：恢复节点与回归

**主题：** `recovery_node` 与端到端回归

**依赖关系：**
- 无强依赖：可独立开发

**新增/修改文件：**
```
app/agent/nodes.py                           # 修改：新增 recovery_node 函数
app/services/error_classifier.py             # 新增：错误分类
tests/test_recovery_node.py                  # 新增：节点测试
tests/test_phase2_e2e.py                     # 新增：端到端测试
```

**核心实现：**
```python
# app/services/error_classifier.py
from enum import Enum
from dataclasses import dataclass


class ErrorType(Enum):
    LLM_TIMEOUT = "llm_timeout"
    LLM_RATE_LIMIT = "llm_rate_limit"
    RAG_FAILURE = "rag_failure"
    RAG_NO_RESULTS = "rag_no_results"
    DB_ERROR = "db_error"
    UNKNOWN = "unknown"


@dataclass
class ErrorClassification:
    error_type: ErrorType
    retryable: bool
    fallback_action: str


ERROR_STRATEGIES = {
    ErrorType.LLM_TIMEOUT: ErrorClassification(
        error_type=ErrorType.LLM_TIMEOUT,
        retryable=True,
        fallback_action="use_cache",
    ),
    ErrorType.RAG_FAILURE: ErrorClassification(
        error_type=ErrorType.RAG_FAILURE,
        retryable=False,
        fallback_action="pure_llm",
    ),
    ErrorType.RAG_NO_RESULTS: ErrorClassification(
        error_type=ErrorType.RAG_NO_RESULTS,
        retryable=False,
        fallback_action="suggest_refine",
    ),
}


def classify_error(error: Exception) -> ErrorClassification:
    """分类错误并返回恢复策略"""
    error_name = type(error).__name__
    error_msg = str(error).lower()

    if "timeout" in error_msg:
        return ERROR_STRATEGIES[ErrorType.LLM_TIMEOUT]
    if "rate limit" in error_msg:
        return ERROR_STRATEGIES[ErrorType.LLM_RATE_LIMIT]
    if "no results" in error_msg or "empty" in error_msg:
        return ERROR_STRATEGIES[ErrorType.RAG_NO_RESULTS]

    return ERROR_STRATEGIES[ErrorType.UNKNOWN]
```

**恢复策略映射：**

| 错误类型 | 重试 | 降级动作 | 降级响应 |
|----------|------|----------|----------|
| LLM超时 | 1次 | 使用缓存 | "正在恢复，请稍候重试" |
| LLM限流 | 1次 | 延迟重试 | "服务繁忙，请稍后" |
| RAG失败 | 否 | 跳过RAG | 纯LLM回答+声明 |
| 检索无结果 | 否 | 扩大范围 | "未找到相关内容，建议换关键词" |

**验收标准：**
- [ ] 错误分类准确率 >= 95%
- [ ] 恢复成功率 >= 80%
- [ ] 端到端回归测试全部通过
- [ ] 链路压测无内存泄漏

---

## 5. 文件结构变更

```text
app/
├── agent/
│   ├── nodes.py                             # 修改：新增节点函数（W5-W8）
│   ├── state.py                             # 修改：新增状态字段
│   ├── routers.py                           # 修改：新增路由逻辑
│   └── graph_v2.py                          # 修改：集成新节点
├── services/
│   ├── retrieval_strategy.py                # 新增：W5
│   ├── evidence_validator.py                # 新增：W6
│   ├── answer_templates.py                  # 新增：W7
│   └── error_classifier.py                  # 新增：W8

tests/
├── test_retrieval_planner_node.py           # 新增：W5
├── test_evidence_gate_node.py               # 新增：W6
├── test_answer_policy_node.py               # 新增：W7
├── test_recovery_node.py                    # 新增：W8
└── test_phase2_e2e.py                       # 新增：W8
```

> **说明：** 新节点函数将添加到现有的 `app/agent/nodes.py` 文件中，保持与现有代码结构一致。

---

## 6. 风险与应对

| 风险 | 影响 | 应对措施 |
|------|------|----------|
| ~~Phase 1 延迟交付~~ | ~~W5-W6 阻塞~~ | ✅ Phase 1 已交付，依赖解除 |
| 证据冲突检测复杂 | W6 延期 | 先实现简化版，后续迭代增强 |
| 恢复路径覆盖不全 | 降级效果差 | 故障注入测试补充用例 |
| 回答模板维护成本高 | 灵活性差 | 配置化 + 版本管理 |

---

## 7. 验收清单

### 7.1 功能验收

- [ ] `retrieval_planner_node` 正确返回检索策略
- [ ] `evidence_gate` 准确判断证据质量
- [ ] `answer_policy_node` 正确选择回答模板
- [ ] `recovery_node` 成功恢复失败场景
- [ ] Graph V2 集成全部新节点

### 7.2 质量验收

- [ ] 所有新增测试通过
- [ ] 端到端回归测试通过
- [ ] 代码覆盖率 >= 80%
- [ ] Ruff 检查无错误

### 7.3 文档验收

- [ ] 更新 `state.py` 字段说明
- [ ] 更新 `graph_v2.py` 图结构说明
- [ ] 更新主设计文档进度备注

---

## 8. 参考文档

- [004-2026-04-20-rag-agent-framework-evolution-design.md](./004-2026-04-20-rag-agent-framework-evolution-design.md) - 12周框架演进设计
- [005-2026-04-20-rag-agent-framework-evolution-phase1.md](../plans/005-2026-04-20-rag-agent-framework-evolution-phase1.md) - Phase 1 实施计划
- [项目报告2026-04-18.md](../../../plan/项目报告2026-04-18.md) - 当前项目状态
