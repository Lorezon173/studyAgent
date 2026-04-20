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
    """提取文本关键词（简化实现）

    使用简单的分词策略：提取中文字符序列作为关键词。

    Args:
        text: 输入文本

    Returns:
        关键词列表
    """
    # 停用词表
    stopwords = {
        "的", "是", "有", "和", "与", "或", "在", "为", "了", "什么",
        "怎么", "如何", "这", "那", "个", "一", "不", "也", "就", "都",
        "请", "问", "能", "会", "可以", "应该", "要", "想", "需要",
        "一种", "这个", "那个", "哪些", "哪个", "多少", "怎样",
    }
    # 提取英文单词
    english_words = re.findall(r"[a-zA-Z]+", text.lower())

    # 提取中文字符序列（连续的中文字符作为一个词）
    chinese_sequences = re.findall(r"[\u4e00-\u9fa5]+", text)

    # 过滤停用词
    filtered = []
    for seq in chinese_sequences:
        if seq not in stopwords and len(seq) >= 2:
            filtered.append(seq)

    # 合并英文和中文
    all_words = english_words + filtered

    return all_words


def calculate_coverage(query_keywords: list[str], evidence_text: str) -> float:
    """计算关键词覆盖度

    使用子串匹配：检查查询中的中文字符序列是否在证据中出现。

    Args:
        query_keywords: 查询关键词列表
        evidence_text: 证据文本

    Returns:
        覆盖度分数 0.0 ~ 1.0
    """
    if not query_keywords:
        return 1.0

    evidence_lower = evidence_text.lower()

    # 对于中文，检查是否有核心词汇出现在证据中
    # 核心词汇：长度 >= 2 的词
    core_keywords = [kw for kw in query_keywords if len(kw) >= 2]

    if not core_keywords:
        return 1.0  # 没有核心关键词，默认通过

    # 检查核心关键词是否在证据中出现（子串匹配）
    covered = 0
    for kw in core_keywords:
        kw_lower = kw.lower()
        # 检查关键词本身
        if kw_lower in evidence_lower:
            covered += 1
        # 检查关键词的主要部分（取中间部分）
        elif len(kw) >= 4:
            # 尝试匹配关键词的子串
            for i in range(len(kw) - 1):
                sub = kw[i:i+2]
                if sub.lower() in evidence_lower:
                    covered += 0.5
                    break

    return covered / len(core_keywords)


def validate_evidence(
    query: str,
    evidence_chunks: list[dict],
    min_coverage: float = 0.7,
    max_conflict: float = 0.3,
) -> GateResult:
    """验证证据质量

    Args:
        query: 用户查询
        evidence_chunks: 证据块列表，每个包含 text 和 score
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

    # 2. 合并所有证据文本
    all_evidence_text = " ".join(
        chunk.get("text", "") for chunk in evidence_chunks
    )

    # 3. 计算覆盖度
    coverage_score = calculate_coverage(keywords, all_evidence_text)

    # 4. 找出缺失关键词
    evidence_lower = all_evidence_text.lower()
    missing_keywords = [
        kw for kw in keywords if kw.lower() not in evidence_lower
    ]

    # 5. 检测冲突（简化实现：暂不检测）
    conflict_score = 0.0
    conflict_pairs = []

    # 6. 决策
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
