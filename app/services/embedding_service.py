import math
import re
import warnings
from collections import Counter

from app.core.config import settings


def _tokens(text: str) -> list[str]:
    normalized = (text or "").lower()
    parts = re.findall(r"[0-9a-z]+|[\u4e00-\u9fa5]+", normalized)
    out: list[str] = []
    for part in parts:
        if re.fullmatch(r"[0-9a-z]+", part):
            if len(part) >= 2:
                out.append(part)
            continue
        if len(part) <= 3:
            out.append(part)
        for n in (2, 3):
            if len(part) < n:
                continue
            for idx in range(len(part) - n + 1):
                out.append(part[idx : idx + n])
    return out


def _hash_index(token: str, dim: int) -> int:
    return abs(hash(token)) % dim


def _normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in vec))
    if norm <= 0:
        return vec
    return [x / norm for x in vec]


def _simple_embed(text: str, dim: int) -> list[float]:
    vec = [0.0] * dim
    freq = Counter(_tokens(text))
    for token, count in freq.items():
        idx = _hash_index(token, dim)
        vec[idx] += float(count)
    return _normalize(vec)


def _sentence_transformers_embed(text: str, dim: int) -> list[float]:
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise RuntimeError(
            "当前配置了 sentence_transformers embedding，但未安装 sentence-transformers。"
        ) from exc
    model = SentenceTransformer("BAAI/bge-m3")
    vec = model.encode(text, normalize_embeddings=True).tolist()
    if not isinstance(vec, list):
        raise RuntimeError("sentence-transformers embedding 输出异常。")
    model_dim = len(vec)
    if dim > 0:
        if model_dim > dim:
            vec = _normalize(vec[:dim])
        elif model_dim < dim:
            vec = vec + [0.0] * (dim - model_dim)
    return vec


def _validate_embedding_config() -> None:
    provider = settings.rag_embedding_provider.lower().strip()
    dim = max(16, int(settings.rag_embedding_dim))
    if provider == "sentence_transformers":
        model_dim = 1024
        if dim < int(model_dim * 0.5):
            warnings.warn(
                f"配置的embedding维度({dim})远小于模型维度({model_dim})，建议设置为 {model_dim}",
                UserWarning,
                stacklevel=2,
            )


def embed_text(text: str) -> list[float]:
    provider = settings.rag_embedding_provider.lower().strip()
    dim = max(16, int(settings.rag_embedding_dim))
    if provider == "simple":
        return _simple_embed(text, dim=dim)
    if provider == "sentence_transformers":
        return _sentence_transformers_embed(text, dim=dim)
    raise ValueError(f"不支持的 embedding provider: {settings.rag_embedding_provider}")


def cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    if not vec_a or not vec_b:
        return 0.0
    n = min(len(vec_a), len(vec_b))
    dot = sum(vec_a[i] * vec_b[i] for i in range(n))
    norm_a = math.sqrt(sum(vec_a[i] * vec_a[i] for i in range(n)))
    norm_b = math.sqrt(sum(vec_b[i] * vec_b[i] for i in range(n)))
    if norm_a <= 0 or norm_b <= 0:
        return 0.0
    return dot / (norm_a * norm_b)


_validate_embedding_config()

