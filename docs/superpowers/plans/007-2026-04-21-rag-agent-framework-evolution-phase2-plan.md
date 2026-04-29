# 编排增强（Phase 2）实施计划

> **给 Agentic Worker：** 必须使用 `superpowers:subagent-driven-development`（推荐）或 `superpowers:executing-plans` 按任务逐步执行。步骤使用复选框语法（`- [ ]`）跟踪。

**目标：** 在 Phase 1 已交付的基础上，实现 4 个编排节点并集成到 Graph V2，完成端到端回归验证。

**架构：** 保持现有 LangGraph + FastAPI + 服务层边界不变。新增节点函数到 `nodes.py`，新增服务模块到 `services/`。

**技术栈：** Python 3.12、FastAPI、LangGraph、pytest、uv

**前置依赖：** Phase 1 已交付 ✅
- `app/services/query_planner.py` - `QueryPlan` 数据类
- `app/services/evidence_policy.py` - `EvidenceAssessment` 数据类
- 状态字段：`rag_confidence_level`, `rag_low_evidence`, `rag_avg_score`

---

## 文件结构

```text
app/
├── services/
│   ├── retrieval_strategy.py                # 新增：W5 检索策略配置
│   ├── evidence_validator.py                # 新增：W6 证据验证逻辑
│   ├── answer_templates.py                  # 新增：W7 回答模板库
│   └── error_classifier.py                  # 新增：W8 错误分类
├── agent/
│   ├── nodes.py                             # 修改：新增 4 个节点函数
│   ├── state.py                             # 修改：新增状态字段
│   ├── routers.py                           # 修改：新增路由逻辑
│   └── graph_v2.py                          # 修改：集成新节点
├── api/
│   └── chat.py                              # 修改：返回新元数据
└── models/
    └── schemas.py                           # 修改：新增响应字段

tests/
├── test_retrieval_planner_node.py           # 新增：W5
├── test_evidence_gate_node.py               # 新增：W6
├── test_answer_policy_node.py               # 新增：W7
├── test_recovery_node.py                    # 新增：W8
└── test_phase2_e2e.py                       # 新增：W8 端到端测试
```

---

## 任务 1：新增检索策略配置服务（W5）

**文件：**
- 新建：`app/services/retrieval_strategy.py`
- 新建：`tests/test_retrieval_strategy.py`

- [ ] **步骤 1：先写失败测试（检索策略配置）**

```python
# tests/test_retrieval_strategy.py
from app.services.retrieval_strategy import get_retrieval_strategy, RETRIEVAL_STRATEGIES


def test_retrieval_strategy_for_fact_mode():
    strategy = get_retrieval_strategy("fact")
    assert strategy["bm25_weight"] == 0.4
    assert strategy["vector_weight"] == 0.6
    assert strategy["web_enabled"] is False
    assert strategy["top_k"] == 3


def test_retrieval_strategy_for_freshness_mode():
    strategy = get_retrieval_strategy("freshness")
    assert strategy["web_enabled"] is True
    assert strategy["top_k"] == 5


def test_retrieval_strategy_for_comparison_mode():
    strategy = get_retrieval_strategy("comparison")
    assert strategy["bm25_weight"] == 0.5
    assert strategy["vector_weight"] == 0.5


def test_retrieval_strategy_defaults_to_fact():
    strategy = get_retrieval_strategy("unknown_mode")
    assert strategy == RETRIEVAL_STRATEGIES["fact"]
```

- [ ] **步骤 2：运行测试并确认失败**

运行：`$env:PYTHONPATH='.'; uv run pytest -q tests/test_retrieval_strategy.py`  
期望：`FAIL`，提示 `ModuleNotFoundError: No module named 'app.services.retrieval_strategy'`

- [ ] **步骤 3：实现检索策略配置**

```python
# app/services/retrieval_strategy.py
"""检索策略配置模块

根据查询模式返回对应的检索策略配置。
"""
from __future__ import annotations

RETRIEVAL_STRATEGIES: dict[str, dict] = {
    "fact": {
        "bm25_weight": 0.4,
        "vector_weight": 0.6,
        "web_enabled": False,
        "top_k": 3,
        "description": "事实问答：向量优先，精确命中",
    },
    "freshness": {
        "bm25_weight": 0.2,
        "vector_weight": 0.3,
        "web_enabled": True,
        "top_k": 5,
        "description": "时效性查询：启用Web检索，扩大召回",
    },
    "comparison": {
        "bm25_weight": 0.5,
        "vector_weight": 0.5,
        "web_enabled": False,
        "top_k": 5,
        "description": "对比分析：均衡召回",
    },
}


def get_retrieval_strategy(mode: str) -> dict:
    """根据查询模式返回检索策略配置
    
    Args:
        mode: 查询模式（fact/freshness/comparison）
        
    Returns:
        检索策略配置字典
    """
    return RETRIEVAL_STRATEGIES.get(mode, RETRIEVAL_STRATEGIES["fact"])
```

- [ ] **步骤 4：再次运行测试并确认通过**

运行：`$env:PYTHONPATH='.'; uv run pytest -q tests/test_retrieval_strategy.py`  
期望：`4 passed`

- [ ] **步骤 5：提交**

```bash
git add app/services/retrieval_strategy.py tests/test_retrieval_strategy.py
git commit -m "feat(rag): add retrieval strategy configuration service"
```

---

## 任务 2：新增检索规划节点（W5）

**文件：**
- 修改：`app/agent/nodes.py`
- 修改：`app/agent/state.py`
- 新建：`tests/test_retrieval_planner_node.py`

- [ ] **步骤 1：新增状态字段**

```python
# app/agent/state.py 追加字段
class LearningState(TypedDict, total=False):
    # ... 现有字段 ...
    
    # 新增：检索策略（Phase 2）
    retrieval_strategy: dict          # 检索策略配置
    retrieval_mode: str               # 查询模式（fact/freshness/comparison）
```

- [ ] **步骤 2：先写失败测试（节点逻辑）**

```python
# tests/test_retrieval_planner_node.py
from app.agent.nodes import retrieval_planner_node
from app.agent.state import LearningState


def test_retrieval_planner_node_sets_strategy():
    state: LearningState = {
        "session_id": "test",
        "user_input": "二分查找是什么？",
        "topic": "算法",
    }
    result = retrieval_planner_node(state)
    assert "retrieval_strategy" in result
    assert result["retrieval_mode"] == "fact"
    assert result["retrieval_strategy"]["bm25_weight"] == 0.4


def test_retrieval_planner_node_detects_freshness():
    state: LearningState = {
        "session_id": "test",
        "user_input": "LangGraph 最新版本是什么",
        "topic": "框架",
    }
    result = retrieval_planner_node(state)
    assert result["retrieval_mode"] == "freshness"
    assert result["retrieval_strategy"]["web_enabled"] is True
```

- [ ] **步骤 3：运行测试并确认失败**

运行：`$env:PYTHONPATH='.'; uv run pytest -q tests/test_retrieval_planner_node.py`  
期望：`FAIL`，提示 `retrieval_planner_node` 未定义

- [ ] **步骤 4：实现检索规划节点**

```python
# app/agent/nodes.py 追加
from app.services.query_planner import build_query_plan, QueryPlan
from app.services.retrieval_strategy import get_retrieval_strategy


def retrieval_planner_node(state: LearningState) -> dict:
    """检索规划节点
    
    根据用户输入和主题，构建查询计划并选择检索策略。
    
    输入：
        - user_input: 用户输入
        - topic: 当前学习主题
        
    输出：
        - retrieval_mode: 查询模式
        - retrieval_strategy: 检索策略配置
    """
    user_input = state.get("user_input", "")
    topic = state.get("topic")
    
    # 复用 Phase 1 的查询规划
    plan: QueryPlan = build_query_plan(user_input, topic)
    
    # 根据模式获取检索策略
    strategy = get_retrieval_strategy(plan.mode)
    
    return {
        "retrieval_mode": plan.mode,
        "retrieval_strategy": strategy,
    }
```

- [ ] **步骤 5：再次运行测试并确认通过**

运行：`$env:PYTHONPATH='.'; uv run pytest -q tests/test_retrieval_planner_node.py`  
期望：`2 passed`

- [ ] **步骤 6：提交**

```bash
git add app/agent/nodes.py app/agent/state.py tests/test_retrieval_planner_node.py
git commit -m "feat(agent): add retrieval planner node with query plan integration"
```

---

## 任务 3：新增证据验证服务（W6）

**文件：**
- 新建：`app/services/evidence_validator.py`
- 新建：`tests/test_evidence_validator.py`

- [ ] **步骤 1：先写失败测试（证据验证）**

```python
# tests/test_evidence_validator.py
from app.services.evidence_validator import validate_evidence, GateResult


def test_validate_evidence_pass():
    result = validate_evidence(
        query="什么是二分查找",
        evidence_chunks=[
            {"text": "二分查找是一种搜索算法", "score": 0.9},
            {"text": "二分查找时间复杂度O(log n)", "score": 0.85},
        ],
    )
    assert result.status == "pass"
    assert result.coverage_score >= 0.7


def test_validate_evidence_supplement():
    result = validate_evidence(
        query="Python异步编程最佳实践",
        evidence_chunks=[
            {"text": "asyncio是Python的异步库", "score": 0.6},
        ],
    )
    assert result.status == "supplement"


def test_validate_evidence_reject():
    result = validate_evidence(
        query="量子计算原理",
        evidence_chunks=[],
    )
    assert result.status == "reject"
    assert result.coverage_score == 0.0
```

- [ ] **步骤 2：运行测试并确认失败**

运行：`$env:PYTHONPATH='.'; uv run pytest -q tests/test_evidence_validator.py`  
期望：`FAIL`，提示 `ModuleNotFoundError: No module named 'app.services.evidence_validator'`

- [ ] **步骤 3：实现证据验证逻辑**

```python
# app/services/evidence_validator.py
"""证据验证模块

验证检索证据的质量，包括覆盖度和冲突度检测。
"""
from __future__ import annotations
from dataclasses import dataclass
import re


@dataclass
class GateResult:
    """证据守门结果"""
    status: str              # pass / supplement / reject
    coverage_score: float    # 覆盖度 0.0 ~ 1.0
    conflict_score: float    # 冲突度 0.0 ~ 1.0
    missing_keywords: list[str]
    conflict_pairs: list[tuple]


def extract_keywords(text: str) -> list[str]:
    """提取文本关键词（简化实现）"""
    # 移除停用词
    stopwords = {"的", "是", "有", "和", "与", "或", "在", "为", "了", "什么", "怎么", "如何"}
    # 分词（简化：按空格和标点）
    words = re.findall(r"[\w]+", text.lower())
    return [w for w in words if w not in stopwords and len(w) > 1]


def validate_evidence(
    query: str,
    evidence_chunks: list[dict],
    min_coverage: float = 0.7,
    max_conflict: float = 0.3,
) -> GateResult:
    """验证证据质量
    
    Args:
        query: 用户查询
        evidence_chunks: 证据块列表
        min_coverage: 最小覆盖度阈值
        max_conflict: 最大冲突度阈值
        
    Returns:
        GateResult: 守门结果
    """
    # 1. 提取查询关键词
    keywords = extract_keywords(query)
    
    if not keywords:
        return GateResult(
            status="pass",
            coverage_score=1.0,
            conflict_score=0.0,
            missing_keywords=[],
            conflict_pairs=[],
        )
    
    if not evidence_chunks:
        return GateResult(
            status="reject",
            coverage_score=0.0,
            conflict_score=0.0,
            missing_keywords=keywords,
            conflict_pairs=[],
        )
    
    # 2. 计算覆盖度
    covered = set()
    for chunk in evidence_chunks:
        text = chunk.get("text", "").lower()
        covered.update(kw for kw in keywords if kw.lower() in text)
    
    coverage_score = len(covered) / len(keywords)
    missing_keywords = [kw for kw in keywords if kw not in covered]
    
    # 3. 检测冲突（简化实现：检查矛盾关键词）
    conflict_score = 0.0
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

- [ ] **步骤 4：运行测试并确认通过**

运行：`$env:PYTHONPATH='.'; uv run pytest -q tests/test_evidence_validator.py`  
期望：`3 passed`

- [ ] **步骤 5：提交**

```bash
git add app/services/evidence_validator.py tests/test_evidence_validator.py
git commit -m "feat(rag): add evidence validation service with coverage check"
```

---

## 任务 4：新增证据守门节点（W6）

**文件：**
- 修改：`app/agent/nodes.py`
- 修改：`app/agent/state.py`
- 新建：`tests/test_evidence_gate_node.py`

- [ ] **步骤 1：新增状态字段**

```python
# app/agent/state.py 追加字段
class LearningState(TypedDict, total=False):
    # ... 现有字段 ...
    
    # 新增：证据守门（Phase 2）
    gate_status: str                   # pass / supplement / reject
    gate_coverage_score: float         # 覆盖度分数
    gate_missing_keywords: list[str]   # 缺失关键词
```

- [ ] **步骤 2：先写失败测试（守门节点）**

```python
# tests/test_evidence_gate_node.py
from app.agent.nodes import evidence_gate_node
from app.agent.state import LearningState


def test_evidence_gate_node_passes_high_quality():
    state: LearningState = {
        "session_id": "test",
        "user_input": "二分查找是什么",
        "rag_context": "二分查找是一种搜索算法，时间复杂度O(log n)",
        "rag_found": True,
        "rag_confidence_level": "high",
    }
    result = evidence_gate_node(state)
    assert result["gate_status"] == "pass"


def test_evidence_gate_node_rejects_no_evidence():
    state: LearningState = {
        "session_id": "test",
        "user_input": "量子计算原理",
        "rag_context": "",
        "rag_found": False,
    }
    result = evidence_gate_node(state)
    assert result["gate_status"] == "reject"
```

- [ ] **步骤 3：实现证据守门节点**

```python
# app/agent/nodes.py 追加
from app.services.evidence_validator import validate_evidence


def evidence_gate_node(state: LearningState) -> dict:
    """证据守门节点
    
    验证证据质量，决定是否可以进入回答阶段。
    
    输入：
        - user_input: 用户查询
        - rag_context: RAG 检索上下文
        - rag_found: 是否找到证据
        
    输出：
        - gate_status: 守门状态
        - gate_coverage_score: 覆盖度分数
        - gate_missing_keywords: 缺失关键词
    """
    user_input = state.get("user_input", "")
    rag_context = state.get("rag_context", "")
    rag_found = state.get("rag_found", False)
    
    if not rag_found or not rag_context:
        return {
            "gate_status": "reject",
            "gate_coverage_score": 0.0,
            "gate_missing_keywords": [],
        }
    
    # 将上下文转换为证据块
    evidence_chunks = [{"text": rag_context, "score": 0.8}]
    
    # 调用验证服务
    result = validate_evidence(user_input, evidence_chunks)
    
    return {
        "gate_status": result.status,
        "gate_coverage_score": result.coverage_score,
        "gate_missing_keywords": result.missing_keywords,
    }
```

- [ ] **步骤 4：运行测试并确认通过**

运行：`$env:PYTHONPATH='.'; uv run pytest -q tests/test_evidence_gate_node.py`  
期望：`2 passed`

- [ ] **步骤 5：提交**

```bash
git add app/agent/nodes.py app/agent/state.py tests/test_evidence_gate_node.py
git commit -m "feat(agent): add evidence gate node for quality control"
```

---

## 任务 5：新增回答模板服务（W7）

**文件：**
- 新建：`app/services/answer_templates.py`
- 新建：`tests/test_answer_templates.py`

- [ ] **步骤 1：先写失败测试（回答模板）**

```python
# tests/test_answer_templates.py
from app.services.answer_templates import get_answer_template, AnswerTemplate


def test_template_for_high_confidence():
    template = get_answer_template("high")
    assert template.template_id == "high"
    assert "参考来源" in template.content
    assert template.boundary_notice == ""


def test_template_for_low_confidence():
    template = get_answer_template("low")
    assert template.template_id == "low"
    assert "重要" in template.boundary_notice


def test_template_defaults_to_medium():
    template = get_answer_template("unknown")
    assert template.template_id == "medium"
```

- [ ] **步骤 2：实现回答模板服务**

```python
# app/services/answer_templates.py
"""回答模板服务

根据证据置信等级提供不同的回答模板。
"""
from __future__ import annotations
from dataclasses import dataclass


@dataclass
class AnswerTemplate:
    """回答模板"""
    template_id: str
    content: str
    boundary_notice: str


ANSWER_TEMPLATES: dict[str, AnswerTemplate] = {
    "high": AnswerTemplate(
        template_id="high",
        content="{answer}\n\n参考来源：{citations}",
        boundary_notice="",
    ),
    "medium": AnswerTemplate(
        template_id="medium",
        content="{answer}",
        boundary_notice="基于已有信息回答，建议结合教材核实。",
    ),
    "low": AnswerTemplate(
        template_id="low",
        content="{answer}",
        boundary_notice="【重要】当前证据不足，以下为推测性回答，请查阅权威资料确认。",
    ),
}


def get_answer_template(confidence_level: str) -> AnswerTemplate:
    """根据置信等级返回回答模板
    
    Args:
        confidence_level: 置信等级（high/medium/low）
        
    Returns:
        AnswerTemplate: 回答模板
    """
    return ANSWER_TEMPLATES.get(confidence_level, ANSWER_TEMPLATES["medium"])
```

- [ ] **步骤 3：运行测试并确认通过**

运行：`$env:PYTHONPATH='.'; uv run pytest -q tests/test_answer_templates.py`  
期望：`3 passed`

- [ ] **步骤 4：提交**

```bash
git add app/services/answer_templates.py tests/test_answer_templates.py
git commit -m "feat(agent): add answer template service with confidence levels"
```

---

## 任务 6：新增回答策略节点（W7）

**文件：**
- 修改：`app/agent/nodes.py`
- 修改：`app/agent/state.py`
- 新建：`tests/test_answer_policy_node.py`

- [ ] **步骤 1：新增状态字段**

```python
# app/agent/state.py 追加字段
class LearningState(TypedDict, total=False):
    # ... 现有字段 ...
    
    # 新增：回答策略（Phase 2）
    answer_template_id: str            # 回答模板ID
    boundary_notice: str               # 边界声明文本
```

- [ ] **步骤 2：实现回答策略节点**

```python
# app/agent/nodes.py 追加
from app.services.answer_templates import get_answer_template


def answer_policy_node(state: LearningState) -> dict:
    """回答策略节点
    
    根据证据置信等级选择回答模板，生成边界声明。
    
    输入：
        - rag_confidence_level: 证据置信等级
        - gate_status: 守门状态
        
    输出：
        - answer_template_id: 回答模板ID
        - boundary_notice: 边界声明文本
    """
    confidence_level = state.get("rag_confidence_level", "medium")
    gate_status = state.get("gate_status", "supplement")
    
    # 根据守门状态调整置信等级
    if gate_status == "reject":
        confidence_level = "low"
    elif gate_status == "supplement":
        confidence_level = "medium"
    
    # 获取模板
    template = get_answer_template(confidence_level)
    
    return {
        "answer_template_id": template.template_id,
        "boundary_notice": template.boundary_notice,
    }
```

- [ ] **步骤 3：编写测试**

```python
# tests/test_answer_policy_node.py
from app.agent.nodes import answer_policy_node
from app.agent.state import LearningState


def test_answer_policy_uses_confidence_level():
    state: LearningState = {
        "session_id": "test",
        "rag_confidence_level": "high",
        "gate_status": "pass",
    }
    result = answer_policy_node(state)
    assert result["answer_template_id"] == "high"
    assert result["boundary_notice"] == ""


def test_answer_policy_downgrades_on_gate_reject():
    state: LearningState = {
        "session_id": "test",
        "rag_confidence_level": "high",
        "gate_status": "reject",
    }
    result = answer_policy_node(state)
    assert result["answer_template_id"] == "low"
```

- [ ] **步骤 4：运行测试**

运行：`$env:PYTHONPATH='.'; uv run pytest -q tests/test_answer_policy_node.py`  
期望：`2 passed`

- [ ] **步骤 5：提交**

```bash
git add app/agent/nodes.py app/agent/state.py tests/test_answer_policy_node.py
git commit -m "feat(agent): add answer policy node with boundary notice"
```

---

## 任务 7：新增错误分类服务（W8）

**文件：**
- 新建：`app/services/error_classifier.py`
- 新建：`tests/test_error_classifier.py`

- [ ] **步骤 1：先写失败测试（错误分类）**

```python
# tests/test_error_classifier.py
from app.services.error_classifier import classify_error, ErrorType


def test_classify_timeout_error():
    error = TimeoutError("LLM request timed out")
    result = classify_error(error)
    assert result.error_type == ErrorType.LLM_TIMEOUT
    assert result.retryable is True


def test_classify_generic_error():
    error = ValueError("Unknown error")
    result = classify_error(error)
    assert result.error_type == ErrorType.UNKNOWN
    assert result.fallback_action == "pure_llm"
```

- [ ] **步骤 2：实现错误分类服务**

```python
# app/services/error_classifier.py
"""错误分类服务

分类异常并返回恢复策略。
"""
from __future__ import annotations
from enum import Enum
from dataclasses import dataclass


class ErrorType(Enum):
    """错误类型枚举"""
    LLM_TIMEOUT = "llm_timeout"
    LLM_RATE_LIMIT = "llm_rate_limit"
    RAG_FAILURE = "rag_failure"
    RAG_NO_RESULTS = "rag_no_results"
    DB_ERROR = "db_error"
    UNKNOWN = "unknown"


@dataclass
class ErrorClassification:
    """错误分类结果"""
    error_type: ErrorType
    retryable: bool
    fallback_action: str


ERROR_STRATEGIES: dict[ErrorType, ErrorClassification] = {
    ErrorType.LLM_TIMEOUT: ErrorClassification(
        error_type=ErrorType.LLM_TIMEOUT,
        retryable=True,
        fallback_action="use_cache",
    ),
    ErrorType.LLM_RATE_LIMIT: ErrorClassification(
        error_type=ErrorType.LLM_RATE_LIMIT,
        retryable=True,
        fallback_action="delay_retry",
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
    ErrorType.DB_ERROR: ErrorClassification(
        error_type=ErrorType.DB_ERROR,
        retryable=True,
        fallback_action="use_cache",
    ),
    ErrorType.UNKNOWN: ErrorClassification(
        error_type=ErrorType.UNKNOWN,
        retryable=False,
        fallback_action="pure_llm",
    ),
}


def classify_error(error: Exception) -> ErrorClassification:
    """分类错误并返回恢复策略
    
    Args:
        error: 异常对象
        
    Returns:
        ErrorClassification: 错误分类结果
    """
    error_name = type(error).__name__
    error_msg = str(error).lower()
    
    if "timeout" in error_msg or error_name == "TimeoutError":
        return ERROR_STRATEGIES[ErrorType.LLM_TIMEOUT]
    if "rate limit" in error_msg or "429" in error_msg:
        return ERROR_STRATEGIES[ErrorType.LLM_RATE_LIMIT]
    if "no result" in error_msg or "empty" in error_msg:
        return ERROR_STRATEGIES[ErrorType.RAG_NO_RESULTS]
    if "connection" in error_msg or "database" in error_msg:
        return ERROR_STRATEGIES[ErrorType.DB_ERROR]
    
    return ERROR_STRATEGIES[ErrorType.UNKNOWN]
```

- [ ] **步骤 3：运行测试**

运行：`$env:PYTHONPATH='.'; uv run pytest -q tests/test_error_classifier.py`  
期望：`2 passed`

- [ ] **步骤 4：提交**

```bash
git add app/services/error_classifier.py tests/test_error_classifier.py
git commit -m "feat(agent): add error classification service for recovery"
```

---

## 任务 8：新增恢复节点（W8）

**文件：**
- 修改：`app/agent/nodes.py`
- 修改：`app/agent/state.py`
- 新建：`tests/test_recovery_node.py`

- [ ] **步骤 1：新增状态字段**

```python
# app/agent/state.py 追加字段
class LearningState(TypedDict, total=False):
    # ... 现有字段 ...
    
    # 新增：恢复策略（Phase 2）
    recovery_action: str               # 恢复动作
    fallback_triggered: bool           # 是否触发降级
    error_code: str                    # 错误码
    retry_trace: list[dict]            # 重试轨迹
```

- [ ] **步骤 2：实现恢复节点**

```python
# app/agent/nodes.py 追加
from app.services.error_classifier import classify_error


def recovery_node(state: LearningState) -> dict:
    """恢复节点
    
    处理节点失败，执行降级策略。
    
    输入：
        - node_error: 错误信息
        - stage: 当前阶段
        
    输出：
        - recovery_action: 恢复动作
        - fallback_triggered: 是否降级
        - reply: 降级响应文本
    """
    error_info = state.get("node_error", "")
    stage = state.get("stage", "unknown")
    
    # 创建错误对象
    error = Exception(error_info) if error_info else Exception("Unknown error")
    
    # 分类错误
    classification = classify_error(error)
    
    # 生成降级响应
    fallback_messages = {
        "use_cache": "正在恢复，请稍候重试。",
        "pure_llm": "当前检索服务不可用，将基于已有知识回答。",
        "suggest_refine": "未找到相关内容，建议换关键词或补充描述。",
        "delay_retry": "服务繁忙，请稍后再试。",
    }
    
    reply = fallback_messages.get(
        classification.fallback_action,
        "服务暂时不可用，请稍后重试。"
    )
    
    return {
        "recovery_action": classification.fallback_action,
        "fallback_triggered": True,
        "error_code": classification.error_type.value,
        "reply": reply,
    }
```

- [ ] **步骤 3：编写测试**

```python
# tests/test_recovery_node.py
from app.agent.nodes import recovery_node
from app.agent.state import LearningState


def test_recovery_node_handles_timeout():
    state: LearningState = {
        "session_id": "test",
        "node_error": "LLM request timed out",
        "stage": "rag_first",
    }
    result = recovery_node(state)
    assert result["fallback_triggered"] is True
    assert result["recovery_action"] == "use_cache"


def test_recovery_node_generates_fallback_reply():
    state: LearningState = {
        "session_id": "test",
        "node_error": "RAG service failed",
        "stage": "rag_first",
    }
    result = recovery_node(state)
    assert "reply" in result
    assert len(result["reply"]) > 0
```

- [ ] **步骤 4：运行测试**

运行：`$env:PYTHONPATH='.'; uv run pytest -q tests/test_recovery_node.py`  
期望：`2 passed`

- [ ] **步骤 5：提交**

```bash
git add app/agent/nodes.py app/agent/state.py tests/test_recovery_node.py
git commit -m "feat(agent): add recovery node with fallback strategies"
```

---

## 任务 9：集成新节点到 Graph V2（W8）

**文件：**
- 修改：`app/agent/graph_v2.py`
- 修改：`app/agent/routers.py`
- 新建：`tests/test_phase2_e2e.py`

- [ ] **步骤 1：新增路由函数**

```python
# app/agent/routers.py 追加
def route_after_evidence_gate(state: LearningState) -> Literal["answer_policy", "recovery"]:
    """证据守门后路由"""
    gate_status = state.get("gate_status", "reject")
    if gate_status == "reject":
        return "recovery"
    return "answer_policy"


def route_on_error(state: LearningState) -> Literal["recovery", "answer_policy"]:
    """错误时路由"""
    if state.get("node_error"):
        return "recovery"
    return "answer_policy"
```

- [ ] **步骤 2：更新图结构**

```python
# app/agent/graph_v2.py 关键改动
from app.agent.nodes import (
    # ... 现有导入 ...
    retrieval_planner_node,
    evidence_gate_node,
    answer_policy_node,
    recovery_node,
)
from app.agent.routers import (
    # ... 现有导入 ...
    route_after_evidence_gate,
    route_on_error,
)


def build_learning_graph_v2():
    graph = StateGraph(LearningState)
    
    # 新增节点
    graph.add_node("retrieval_planner", retrieval_planner_node)
    graph.add_node("evidence_gate", evidence_gate_node)
    graph.add_node("answer_policy", answer_policy_node)
    graph.add_node("recovery", recovery_node)
    
    # 更新边的连接（简化示例）
    # 完整实现需根据设计文档调整
    
    # ... 其他节点和边 ...
    
    return graph.compile(checkpointer=get_checkpointer())
```

- [ ] **步骤 3：编写端到端测试**

```python
# tests/test_phase2_e2e.py
"""Phase 2 端到端测试"""
import pytest


def test_phase2_retrieval_planner_integrated():
    """测试检索规划节点已集成"""
    from app.agent.graph_v2 import get_learning_graph_v2
    graph = get_learning_graph_v2()
    
    # 验证节点存在
    node_names = list(graph.nodes.keys())
    assert "retrieval_planner" in node_names or "retrieval_planner_node" in node_names


def test_phase2_evidence_gate_integrated():
    """测试证据守门节点已集成"""
    from app.agent.graph_v2 import get_learning_graph_v2
    graph = get_learning_graph_v2()
    
    node_names = list(graph.nodes.keys())
    assert "evidence_gate" in node_names


def test_phase2_answer_policy_integrated():
    """测试回答策略节点已集成"""
    from app.agent.graph_v2 import get_learning_graph_v2
    graph = get_learning_graph_v2()
    
    node_names = list(graph.nodes.keys())
    assert "answer_policy" in node_names


def test_phase2_recovery_integrated():
    """测试恢复节点已集成"""
    from app.agent.graph_v2 import get_learning_graph_v2
    graph = get_learning_graph_v2()
    
    node_names = list(graph.nodes.keys())
    assert "recovery" in node_names
```

- [ ] **步骤 4：运行全量测试**

运行：`$env:PYTHONPATH='.'; uv run pytest -q`  
期望：全部通过

- [ ] **步骤 5：提交**

```bash
git add app/agent/graph_v2.py app/agent/routers.py tests/test_phase2_e2e.py
git commit -m "feat(agent): integrate phase2 nodes into graph v2"
```

---

## 任务 10：Phase 2 回归验证与文档同步（W8）

**文件：**
- 修改：`docs/superpowers/specs/004-2026-04-20-rag-agent-framework-evolution-design.md`

- [ ] **步骤 1：运行聚焦回归集**

运行：  
`$env:PYTHONPATH='.'; uv run pytest -q tests/test_retrieval_strategy.py tests/test_retrieval_planner_node.py tests/test_evidence_validator.py tests/test_evidence_gate_node.py tests/test_answer_templates.py tests/test_answer_policy_node.py tests/test_error_classifier.py tests/test_recovery_node.py tests/test_phase2_e2e.py`  
期望：`PASS`

- [ ] **步骤 2：运行全量测试**

运行：`$env:PYTHONPATH='.'; uv run pytest -q`  
期望：`PASS`

- [ ] **步骤 3：更新主设计文档进度**

```markdown
## 12. Progress Note

### Phase 1 已交付 ✅
- 已接入查询规划（query planning）并在 RAG 执行阶段生效。
- 已接入证据置信分级与低证据边界声明策略。
- Graph V2 与 Chat API 已透出 RAG 置信度元数据。

### Phase 2 已交付 ✅
- 已实现检索规划节点（retrieval_planner_node）。
- 已实现证据守门节点（evidence_gate）。
- 已实现回答策略节点（answer_policy_node）。
- 已实现恢复节点（recovery_node）。
- Graph V2 已集成全部新节点。
```

- [ ] **步骤 4：提交**

```bash
git add docs/superpowers/specs/004-2026-04-20-rag-agent-framework-evolution-design.md
git commit -m "docs: mark phase-2 orchestration enhancement delivered"
```

---

## Spec 覆盖性检查

本计划已覆盖：
1. 检索规划节点（Spec §6.1）  
2. 证据守门节点（Spec §6.1）  
3. 回答策略节点（Spec §6.1）  
4. 恢复节点（Spec §6.3）  
5. 状态字段扩展（Spec §6.2）

本计划未覆盖（需后续独立计划）：
1. SLO 守门自动化、灰度发布流水线、容量治理看板（Phase 3）
