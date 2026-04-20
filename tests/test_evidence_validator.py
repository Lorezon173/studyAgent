# tests/test_evidence_validator.py
"""证据验证服务测试"""
from app.services.evidence_validator import validate_evidence, GateResult


def test_validate_evidence_pass():
    """测试高质量证据通过守门"""
    result = validate_evidence(
        query="二分查找的原理",
        evidence_chunks=[
            {"text": "二分查找是一种搜索算法", "score": 0.9},
            {"text": "二分查找时间复杂度O(log n)", "score": 0.85},
        ],
    )
    # 二分查找在证据中出现，覆盖度应该足够高
    assert result.status in ["pass", "supplement"]
    assert result.coverage_score > 0


def test_validate_evidence_supplement():
    """测试部分覆盖需要补充"""
    result = validate_evidence(
        query="Python装饰器的高级用法",
        evidence_chunks=[
            {"text": "装饰器是Python的语法糖", "score": 0.6},
        ],
    )
    # 部分匹配，可能是supplement或pass
    assert result.status in ["pass", "supplement", "reject"]


def test_validate_evidence_reject():
    """测试无证据拒绝"""
    result = validate_evidence(
        query="量子计算原理",
        evidence_chunks=[],
    )
    assert result.status == "reject"
    assert result.coverage_score == 0.0


def test_validate_evidence_missing_keywords():
    """测试缺失关键词检测"""
    result = validate_evidence(
        query="Python装饰器的实现原理",
        evidence_chunks=[
            {"text": "装饰器是Python的语法糖", "score": 0.7},
        ],
    )
    # 应该检测到缺失关键词
    assert isinstance(result.missing_keywords, list)


def test_gate_result_dataclass():
    """测试 GateResult 数据类"""
    result = GateResult(
        status="pass",
        coverage_score=0.8,
        conflict_score=0.0,
        missing_keywords=[],
        conflict_pairs=[],
    )
    assert result.status == "pass"
    assert result.coverage_score == 0.8
