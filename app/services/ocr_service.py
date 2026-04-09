import re
from typing import Any

from app.core.config import settings


def _normalize_image_payload(image_payload: Any) -> str:
    if isinstance(image_payload, bytes):
        for encoding in ("utf-8", "utf-8-sig", "gb18030", "latin1"):
            try:
                return image_payload.decode(encoding, errors="ignore")
            except Exception:
                continue
        return ""
    if isinstance(image_payload, str):
        return image_payload
    return str(image_payload or "")


def _simple_ocr(image_payload: str | bytes) -> str:
    raw = _normalize_image_payload(image_payload)
    normalized = " ".join((raw or "").split())
    return re.sub(r"\s+", " ", normalized).strip()


def _paddle_ocr(image_payload: str | bytes) -> str:
    """
    PaddleOCR 占位入口。

    说明：
    - 当前工程环境未强制安装 paddleocr
    - 若配置 rag_ocr_engine=paddleocr 且未安装依赖，抛明确错误
    """
    try:
        import paddleocr  # noqa: F401
    except ImportError as exc:
        raise RuntimeError(
            "当前配置了 rag_ocr_engine=paddleocr，但未安装 paddleocr。"
            "请安装后再启用，或将 RAG_OCR_ENGINE 设置为 simple。"
        ) from exc
    # 当前先保留统一文本化链路，真实图像识别接入时在此替换。
    return _simple_ocr(image_payload)


def ocr_extract_text(image_payload: str | bytes) -> str:
    engine = settings.rag_ocr_engine.lower().strip()
    if engine == "simple":
        return _simple_ocr(image_payload)
    if engine == "paddleocr":
        return _paddle_ocr(image_payload)
    raise ValueError(f"不支持的 OCR 引擎: {settings.rag_ocr_engine}")

