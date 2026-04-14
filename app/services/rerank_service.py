import re

from app.core.config import settings

_RERANKER_MODEL = None
_RERANKER_MODEL_NAME: str | None = None


def _get_reranker_model():
    provider = settings.rag_rerank_provider.lower().strip()
    if provider != "bge":
        return None

    model_name = "BAAI/bge-reranker-base"
    global _RERANKER_MODEL, _RERANKER_MODEL_NAME
    if _RERANKER_MODEL is not None and _RERANKER_MODEL_NAME == model_name:
        return _RERANKER_MODEL

    try:
        from sentence_transformers import CrossEncoder
    except ImportError as exc:
        raise RuntimeError(
            "当前配置了 bge reranker，但未安装 sentence-transformers。"
        ) from exc

    _RERANKER_MODEL = CrossEncoder(model_name)
    _RERANKER_MODEL_NAME = model_name
    return _RERANKER_MODEL


def _simple_overlap_score(query: str, text: str) -> float:
    q = set(re.findall(r"[0-9a-zA-Z\u4e00-\u9fa5]{2,}", query.lower()))
    t = set(re.findall(r"[0-9a-zA-Z\u4e00-\u9fa5]{2,}", text.lower()))
    if not q or not t:
        return 0.0
    return float(len(q & t))


def _cross_encoder_score(query: str, text: str) -> float:
    model = _get_reranker_model()
    if model is None:
        return _simple_overlap_score(query, text)
    score = model.predict([(query, text)])
    if hasattr(score, "__len__"):
        return float(score[0])
    return float(score)


def _batch_cross_encoder_score(query: str, texts: list[str]) -> list[float]:
    model = _get_reranker_model()
    if model is None:
        return [_simple_overlap_score(query, text) for text in texts]
    scores = model.predict([(query, text) for text in texts])
    if hasattr(scores, "__iter__"):
        return [float(score) for score in scores]
    return [float(scores)]


def rerank_items(query: str, items: list[dict]) -> list[dict]:
    provider = settings.rag_rerank_provider.lower().strip()
    scored: list[tuple[float, dict]] = []
    if provider == "simple":
        for item in items:
            text = str(item.get("text", ""))
            rs = _simple_overlap_score(query, text)
            row = item.copy()
            row["rerank_score"] = rs
            scored.append((rs, row))
    elif provider == "bge":
        texts = [str(item.get("text", "")) for item in items]
        scores = _batch_cross_encoder_score(query, texts)
        for item, score in zip(items, scores):
            row = item.copy()
            row["rerank_score"] = score
            scored.append((score, row))
    else:
        raise ValueError(f"不支持的 rerank provider: {settings.rag_rerank_provider}")

    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [row for _, row in scored]


def clear_reranker_cache() -> None:
    global _RERANKER_MODEL, _RERANKER_MODEL_NAME
    _RERANKER_MODEL = None
    _RERANKER_MODEL_NAME = None

