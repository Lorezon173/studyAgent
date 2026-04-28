"""LearningState 的类型化访问视图。

视图不持有独立状态；构造时接收一个 LearningState dict，
读写直接落到原 dict。这避免了 LangGraph reducer 的兼容性问题，
同时为开发者提供清晰的字段分组与默认值。

Phase 5 引入 RagView 一个视图。其他视图视使用情况在 Phase 6 扩展。
"""
from __future__ import annotations

from typing import Any, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from app.agent.state import LearningState
    from app.services.rag_coordinator import RAGExecutionMeta


class RagView:
    """RAG 字段族的类型化访问门面。

    覆盖字段：rag_found, rag_context, rag_citations, rag_confidence_level,
    rag_low_evidence, rag_avg_score, rag_meta_last。
    """

    __slots__ = ("_state",)

    def __init__(self, state: "LearningState") -> None:
        self._state = state

    # ---- 读取 ----
    @property
    def found(self) -> bool:
        return bool(self._state.get("rag_found", False))

    @property
    def context(self) -> str:
        return str(self._state.get("rag_context", ""))

    @property
    def citations(self) -> List[dict]:
        return list(self._state.get("rag_citations", []) or [])

    @property
    def confidence_level(self) -> str:
        return str(self._state.get("rag_confidence_level", "low"))

    @property
    def low_evidence(self) -> bool:
        return bool(self._state.get("rag_low_evidence", True))

    @property
    def avg_score(self) -> float:
        return float(self._state.get("rag_avg_score", 0.0))

    @property
    def meta_last(self) -> "Optional[RAGExecutionMeta]":
        return self._state.get("rag_meta_last")

    # ---- 写入 ----
    def reset(self) -> None:
        """初始化所有 RAG 字段到默认值。"""
        self._state["rag_found"] = False
        self._state["rag_context"] = ""
        self._state["rag_citations"] = []
        self._state["rag_confidence_level"] = "low"
        self._state["rag_low_evidence"] = True
        self._state["rag_avg_score"] = 0.0

    def record_hit(
        self,
        *,
        context: str,
        citations: List[dict],
        avg_score: float,
        confidence_level: str,
        meta: "Optional[RAGExecutionMeta]" = None,
    ) -> None:
        """记录一次成功命中。"""
        self._state["rag_found"] = True
        self._state["rag_context"] = context
        self._state["rag_citations"] = citations
        self._state["rag_avg_score"] = avg_score
        self._state["rag_confidence_level"] = confidence_level
        self._state["rag_low_evidence"] = confidence_level == "low"
        if meta is not None:
            self._state["rag_meta_last"] = meta

    def record_meta(self, meta: "Optional[RAGExecutionMeta]") -> None:
        """单独记录 meta，用于在命中前先存元数据。"""
        if meta is not None:
            self._state["rag_meta_last"] = meta

    def to_return_dict(self) -> dict[str, Any]:
        """构造 LangGraph 节点应返回的 dict（仅包含 RAG 字段族）。"""
        return {
            "rag_found": self.found,
            "rag_context": self.context,
            "rag_citations": self.citations,
            "rag_confidence_level": self.confidence_level,
            "rag_low_evidence": self.low_evidence,
            "rag_avg_score": self.avg_score,
            "rag_meta_last": self.meta_last,
        }


__all__ = ["RagView"]
