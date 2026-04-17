import json
import math
import re
from pathlib import Path
from typing import Any
from uuid import uuid4

from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.core.config import settings
from app.services.embedding_service import cosine_similarity, embed_text
from app.services.rerank_service import rerank_items

_MEMORY_KNOWLEDGE_CHUNKS: list[dict[str, Any]] = []
_DISK_CHUNKS_CACHE: list[dict[str, Any]] | None = None
_LAST_FILE_MTIME: float = 0.0
_LAST_FILE_SIZE: int = 0


def _store_path() -> Path:
    return Path(settings.rag_store_path)


def _tokenize(text: str) -> set[str]:
    normalized = (text or "").lower()
    parts = re.findall(r"[0-9a-z]+|[\u4e00-\u9fa5]+", normalized)
    tokens: set[str] = set()
    for part in parts:
        if re.fullmatch(r"[0-9a-z]+", part):
            if len(part) >= 2:
                tokens.add(part)
            continue

        # 中文连续片段：加入2-gram/3-gram，避免“整句一个token”导致无法命中
        if len(part) <= 3:
            tokens.add(part)
        for n in (2, 3):
            if len(part) < n:
                continue
            for idx in range(len(part) - n + 1):
                tokens.add(part[idx : idx + n])
    return tokens


def _tokenize_with_freq(text: str) -> dict[str, int]:
    normalized = (text or "").lower()
    parts = re.findall(r"[0-9a-z]+|[\u4e00-\u9fa5]+", normalized)
    freq: dict[str, int] = {}
    for part in parts:
        if re.fullmatch(r"[0-9a-z]+", part):
            if len(part) >= 2:
                freq[part] = freq.get(part, 0) + 1
            continue
        if len(part) <= 3:
            freq[part] = freq.get(part, 0) + 1
        for n in (2, 3):
            if len(part) < n:
                continue
            for idx in range(len(part) - n + 1):
                tok = part[idx : idx + n]
                freq[tok] = freq.get(tok, 0) + 1
    return freq


def _split_text(
    text: str,
    chunk_size: int,
    chunk_overlap: int,
    respect_sentences: bool = True,
) -> list[str]:
    normalized = " ".join(text.split())
    if not normalized:
        return []
    if chunk_size <= 0:
        chunk_size = 500
    overlap = _compute_overlap_length(chunk_size=chunk_size, requested_overlap=chunk_overlap)
    if not respect_sentences:
        return _langchain_split(normalized, chunk_size=chunk_size, chunk_overlap=overlap)
    return _sentence_preserving_split(normalized, chunk_size=chunk_size, chunk_overlap=overlap)


def _compute_overlap_length(*, chunk_size: int, requested_overlap: int) -> int:
    ratio_min = max(0.0, float(settings.rag_chunk_overlap_ratio_min))
    ratio_max = min(0.95, float(settings.rag_chunk_overlap_ratio_max))
    if ratio_max < ratio_min:
        ratio_max = ratio_min
    ratio_target = float(settings.rag_chunk_overlap_ratio_target)
    ratio_target = max(ratio_min, min(ratio_target, ratio_max))

    default_overlap = int(chunk_size * ratio_target)
    if requested_overlap > 0:
        default_overlap = requested_overlap

    min_overlap = int(chunk_size * ratio_min)
    max_overlap = int(chunk_size * ratio_max)
    if max_overlap <= 0:
        return 0
    return max(min_overlap, min(default_overlap, max_overlap))


def _langchain_split(text: str, chunk_size: int, chunk_overlap: int) -> list[str]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", "。", "！", "？", ".", "!", "?", "；", ";", "，", ",", " ", ""],
        keep_separator=True,
        is_separator_regex=False,
    )
    return [chunk.strip() for chunk in splitter.split_text(text) if chunk.strip()]


def _split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[。！？.!?])\s*", text)
    return [part.strip() for part in parts if part and part.strip()]


def _collect_tail_sentences(sentences: list[str], target: int, max_allowed: int) -> list[str]:
    overlap: list[str] = []
    total = 0
    for sentence in reversed(sentences):
        sentence_len = len(sentence)
        if overlap and total + sentence_len > max_allowed:
            break
        overlap.insert(0, sentence)
        total += sentence_len
        if total >= target:
            break
    return overlap


def _sentence_preserving_split(text: str, chunk_size: int, chunk_overlap: int) -> list[str]:
    rough_chunks = _langchain_split(text, chunk_size=chunk_size, chunk_overlap=0)
    min_chunk_size = max(1, int(settings.rag_chunk_min_size))
    ratio_max = max(float(settings.rag_chunk_overlap_ratio_min), float(settings.rag_chunk_overlap_ratio_max))
    max_overlap = max(chunk_overlap, int(chunk_size * ratio_max))

    results: list[str] = []
    prev_sentences: list[str] = []
    for rough in rough_chunks:
        sentences = _split_sentences(rough)
        if not sentences:
            continue
        if not results:
            assembled = " ".join(sentences).strip()
            if assembled:
                results.append(assembled)
                prev_sentences = sentences
            continue

        overlap_sentences = _collect_tail_sentences(prev_sentences, target=chunk_overlap, max_allowed=max_overlap)
        merged = overlap_sentences + sentences

        assembled = " ".join(merged).strip()
        if len(assembled) < min_chunk_size and results:
            results[-1] = f"{results[-1]} {assembled}".strip()
            prev_sentences = _split_sentences(results[-1])
            continue

        if assembled:
            results.append(assembled)
            prev_sentences = merged

    return [chunk for chunk in results if chunk]


def _lexical_overlap_score(query_tokens: set[str], text: str) -> float:
    if not query_tokens:
        return 0.0
    c_tokens = _tokenize(text)
    if not c_tokens:
        return 0.0
    overlap = len(query_tokens & c_tokens)
    return overlap / max(1, len(query_tokens))


def _bm25_score(
    *,
    query_tokens: dict[str, int],
    doc_tokens: dict[str, int],
    doc_len: int,
    avg_doc_len: float,
    df_map: dict[str, int],
    doc_count: int,
    k1: float = 1.2,
    b: float = 0.75,
) -> float:
    if not query_tokens or not doc_tokens or doc_count <= 0:
        return 0.0
    score = 0.0
    safe_avg_len = avg_doc_len if avg_doc_len > 0 else 1.0
    for token, qf in query_tokens.items():
        tf = doc_tokens.get(token, 0)
        if tf <= 0:
            continue
        df = df_map.get(token, 0)
        idf = math.log(1.0 + (doc_count - df + 0.5) / (df + 0.5))
        denom = tf + k1 * (1.0 - b + b * (doc_len / safe_avg_len))
        if denom <= 0:
            continue
        score += idf * ((tf * (k1 + 1.0)) / denom) * max(1, qf)
    return score


def _get_file_stats() -> tuple[float, int]:
    path = _store_path()
    if not path.exists():
        return 0.0, 0
    stat = path.stat()
    return float(stat.st_mtime), int(stat.st_size)


def _load_disk_chunks() -> list[dict[str, Any]]:
    global _DISK_CHUNKS_CACHE, _LAST_FILE_MTIME, _LAST_FILE_SIZE
    current_mtime, current_size = _get_file_stats()
    if (
        _DISK_CHUNKS_CACHE is not None
        and current_mtime == _LAST_FILE_MTIME
        and current_size == _LAST_FILE_SIZE
    ):
        return _DISK_CHUNKS_CACHE
    path = _store_path()
    if not path.exists():
        _DISK_CHUNKS_CACHE = []
        _LAST_FILE_MTIME = 0.0
        _LAST_FILE_SIZE = 0
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text:
            continue
        try:
            obj = json.loads(text)
            if isinstance(obj, dict):
                rows.append(obj)
        except json.JSONDecodeError:
            continue
    _DISK_CHUNKS_CACHE = rows
    _LAST_FILE_MTIME = current_mtime
    _LAST_FILE_SIZE = current_size
    return rows


def _persist_chunk(item: dict[str, Any]) -> None:
    path = _store_path()
    if not path.parent.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(item, ensure_ascii=False) + "\n")


def _invalidate_cache() -> None:
    global _DISK_CHUNKS_CACHE
    _DISK_CHUNKS_CACHE = None


def ingest_knowledge(
    *,
    source_type: str,
    scope: str,
    user_id: str | None,
    content: str,
    topic: str | None,
    title: str | None,
    source_uri: str | None,
    chapter: str | None,
    page_no: int | None,
    image_id: str | None,
    chunk_size: int | None,
    chunk_overlap: int | None,
) -> int:
    if source_type not in {"text", "image"}:
        raise ValueError("source_type 仅支持 text 或 image")
    if scope not in {"global", "personal"}:
        raise ValueError("scope 仅支持 global 或 personal")
    if scope == "personal" and not user_id:
        raise ValueError("personal scope 必须提供 user_id")
    if scope == "global":
        user_id = None
    raw = (content or "").strip()
    if not raw:
        raise ValueError("content 不能为空")
    if len(raw) > max(1, int(settings.rag_max_text_length)):
        raise ValueError(
            f"文本长度({len(raw)})超过限制({settings.rag_max_text_length})，请分批入库"
        )

    size = chunk_size or settings.rag_default_chunk_size
    overlap = chunk_overlap if chunk_overlap is not None else settings.rag_default_chunk_overlap
    chunks = _split_text(
        raw,
        chunk_size=size,
        chunk_overlap=overlap,
        respect_sentences=bool(settings.rag_chunk_respect_sentences),
    )
    max_chunks = max(1, int(settings.rag_max_chunks_per_ingest))
    if len(chunks) > max_chunks:
        raise ValueError(
            f"切分后chunk数量({len(chunks)})超过限制({max_chunks})，"
            "建议增大 chunk_size 或拆分文件后再入库"
        )
    inserted = 0
    for idx, chunk in enumerate(chunks):
        embedding = embed_text(chunk)
        item = {
            "chunk_id": str(uuid4()),
            "source_type": source_type,
            "scope": scope,
            "user_id": user_id,
            "topic": topic,
            "title": title,
            "source_uri": source_uri,
            "chapter": chapter,
            "page_no": page_no,
            "image_id": image_id,
            "chunk_index": idx,
            "text": chunk,
            "embedding": embedding,
        }
        _MEMORY_KNOWLEDGE_CHUNKS.append(item)
        _persist_chunk(item)
        inserted += 1
    _invalidate_cache()
    return inserted


def retrieve_knowledge(*, query: str, topic: str | None, top_k: int) -> list[dict[str, Any]]:
    return retrieve_knowledge_by_scope(
        query=query,
        topic=topic,
        top_k=top_k,
        scope="global",
        user_id=None,
    )


def retrieve_knowledge_by_scope(
    *,
    query: str,
    topic: str | None,
    top_k: int,
    scope: str,
    user_id: str | None,
) -> list[dict[str, Any]]:
    q_tokens = _tokenize(query)
    q_tf = _tokenize_with_freq(query)
    if not q_tokens or not q_tf:
        return []
    if scope not in {"global", "personal"}:
        raise ValueError("scope 仅支持 global 或 personal")
    if scope == "personal" and not user_id:
        raise ValueError("personal scope 必须提供 user_id")

    query_embedding = embed_text(query)

    candidates = _MEMORY_KNOWLEDGE_CHUNKS + _load_disk_chunks()
    if scope == "global":
        candidates = [x for x in candidates if x.get("scope", "global") == "global"]
    else:
        candidates = [
            x
            for x in candidates
            if x.get("scope") == "personal" and x.get("user_id") == user_id
        ]
    if topic:
        candidates = [x for x in candidates if x.get("topic") in {None, "", topic}]

    tokenized_docs: list[tuple[dict[str, Any], dict[str, int], int]] = []
    df_map: dict[str, int] = {}
    total_len = 0
    for item in candidates:
        text = str(item.get("text", ""))
        d_tf = _tokenize_with_freq(text)
        d_len = sum(d_tf.values())
        if d_len <= 0:
            continue
        tokenized_docs.append((item, d_tf, d_len))
        total_len += d_len
        for token in d_tf:
            df_map[token] = df_map.get(token, 0) + 1
    if not tokenized_docs:
        return []
    avg_doc_len = total_len / len(tokenized_docs)
    doc_count = len(tokenized_docs)

    bm25_scored: list[tuple[float, dict[str, Any]]] = []
    dense_scored: list[tuple[float, dict[str, Any]]] = []
    for item, d_tf, d_len in tokenized_docs:
        text = str(item.get("text", ""))
        lexical_score = _lexical_overlap_score(q_tokens, text)
        bm25_score = _bm25_score(
            query_tokens=q_tf,
            doc_tokens=d_tf,
            doc_len=d_len,
            avg_doc_len=avg_doc_len,
            df_map=df_map,
            doc_count=doc_count,
        )
        emb = item.get("embedding")
        vector_score = cosine_similarity(query_embedding, emb if isinstance(emb, list) else [])
        vector_score = (vector_score + 1.0) / 2.0
        if bm25_score > 0:
            row_bm25 = item.copy()
            row_bm25["lexical_score"] = lexical_score
            row_bm25["bm25_score"] = bm25_score
            row_bm25["vector_score"] = vector_score
            bm25_scored.append((bm25_score, row_bm25))
        if vector_score > 0:
            row_dense = item.copy()
            row_dense["lexical_score"] = lexical_score
            row_dense["bm25_score"] = bm25_score
            row_dense["vector_score"] = vector_score
            dense_scored.append((vector_score, row_dense))

    bm25_scored.sort(key=lambda pair: pair[0], reverse=True)
    dense_scored.sort(key=lambda pair: pair[0], reverse=True)

    rrf_k = max(1, int(settings.rag_rrf_k))
    rank_window = max(1, int(settings.rag_rrf_rank_window_size))
    fused_map: dict[str, dict[str, Any]] = {}

    def _fuse(scores: list[tuple[float, dict[str, Any]]], key: str) -> None:
        for rank_idx, (_, row) in enumerate(scores[:rank_window], start=1):
            cid = str(row.get("chunk_id"))
            if not cid:
                continue
            current = fused_map.get(cid)
            if current is None:
                current = row.copy()
                current["rrf_score"] = 0.0
                current["rrf_bm25"] = 0.0
                current["rrf_dense"] = 0.0
                fused_map[cid] = current
            contrib = 1.0 / (rrf_k + rank_idx)
            current["rrf_score"] = float(current.get("rrf_score", 0.0)) + contrib
            current[key] = float(current.get(key, 0.0)) + contrib

    _fuse(bm25_scored, "rrf_bm25")
    _fuse(dense_scored, "rrf_dense")

    fused_items = [x for x in fused_map.values() if float(x.get("rrf_score", 0.0)) > 0]
    if not fused_items:
        return []
    fused_items.sort(key=lambda x: float(x.get("rrf_score", 0.0)), reverse=True)

    pre_ranked: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for item in fused_items:
        cid = str(item.get("chunk_id"))
        if cid in seen_ids:
            continue
        seen_ids.add(cid)
        row = item.copy()
        row["hybrid_score"] = float(row.get("rrf_score", 0.0))
        pre_ranked.append(row)
        if len(pre_ranked) >= max(1, int(settings.rag_rerank_top_n)):
            break

    reranked = rerank_items(query, pre_ranked)
    max_rerank = max((float(x.get("rerank_score", 0.0)) for x in reranked), default=0.0)
    final_items: list[dict[str, Any]] = []
    for row in reranked:
        rr = float(row.get("rerank_score", 0.0))
        rr_norm = rr / max_rerank if max_rerank > 0 else 0.0
        final_score = 0.8 * float(row.get("rrf_score", row.get("hybrid_score", 0.0))) + 0.2 * rr_norm
        row["score"] = final_score
        final_items.append(row)

    final_items.sort(key=lambda x: float(x.get("score", 0.0)), reverse=True)
    return final_items[: max(1, top_k)]

