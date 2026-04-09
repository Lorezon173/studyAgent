import re

from app.core.config import settings


def _simple_overlap_score(query: str, text: str) -> float:
    q = set(re.findall(r"[0-9a-zA-Z\u4e00-\u9fa5]{2,}", query.lower()))
    t = set(re.findall(r"[0-9a-zA-Z\u4e00-\u9fa5]{2,}", text.lower()))
    if not q or not t:
        return 0.0
    return float(len(q & t))


def _cross_encoder_score(query: str, text: str) -> float:
    try:
        from sentence_transformers import CrossEncoder
    except ImportError as exc:
        raise RuntimeError(
            "当前配置了 bge reranker，但未安装 sentence-transformers。"
        ) from exc
    model = CrossEncoder("BAAI/bge-reranker-base")
    score = model.predict([(query, text)])
    if hasattr(score, "__len__"):
        return float(score[0])
    return float(score)


def rerank_items(query: str, items: list[dict]) -> list[dict]:
    provider = settings.rag_rerank_provider.lower().strip()
    scored: list[tuple[float, dict]] = []
    for item in items:
        text = str(item.get("text", ""))
        if provider == "simple":
            rs = _simple_overlap_score(query, text)
        elif provider == "bge":
            rs = _cross_encoder_score(query, text)
        else:
            raise ValueError(f"不支持的 rerank provider: {settings.rag_rerank_provider}")
        row = item.copy()
        row["rerank_score"] = rs
        scored.append((rs, row))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [row for _, row in scored]

