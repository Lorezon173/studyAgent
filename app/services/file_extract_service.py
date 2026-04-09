from __future__ import annotations

import io
from pathlib import Path

from fastapi import UploadFile

from app.services.ocr_service import ocr_extract_text

SUPPORTED_UPLOAD_EXTENSIONS = {".txt", ".docx", ".pdf", ".png", ".jpg", ".jpeg"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg"}


def infer_source_type_from_filename(filename: str | None) -> str:
    ext = Path(filename or "").suffix.lower()
    if ext in IMAGE_EXTENSIONS:
        return "image"
    return "text"


def validate_upload_extension(filename: str | None) -> str:
    ext = Path(filename or "").suffix.lower()
    if ext not in SUPPORTED_UPLOAD_EXTENSIONS:
        raise ValueError("仅支持上传 txt/docx/pdf/png/jpg/jpeg 文件")
    return ext


def extract_text_from_upload(*, filename: str | None, payload: bytes, source_type: str) -> str:
    ext = validate_upload_extension(filename)
    if source_type == "image" or ext in IMAGE_EXTENSIONS:
        text = ocr_extract_text(payload)
        if not text.strip():
            raise ValueError("图片OCR未识别到有效文本，请检查图片质量或切换OCR引擎")
        return text

    if ext == ".txt":
        return _extract_txt(payload)
    if ext == ".docx":
        return _extract_docx(payload)
    if ext == ".pdf":
        return _extract_pdf(payload)
    raise ValueError("不支持的文件类型")


async def read_and_extract_upload(file: UploadFile, source_type: str) -> str:
    payload = await file.read()
    if not payload:
        raise ValueError("上传文件为空")
    return extract_text_from_upload(filename=file.filename, payload=payload, source_type=source_type)


def _extract_txt(payload: bytes) -> str:
    for encoding in ("utf-8", "utf-8-sig", "gb18030"):
        try:
            text = payload.decode(encoding)
            if text.strip():
                return text.strip()
        except UnicodeDecodeError:
            continue
    raise ValueError("txt 文件编码无法识别，请使用 UTF-8 或 GB18030")


def _extract_docx(payload: bytes) -> str:
    try:
        from docx import Document  # type: ignore
    except ImportError as exc:
        raise RuntimeError("未安装 python-docx，无法解析 docx 文件") from exc
    doc = Document(io.BytesIO(payload))
    text = "\n".join(p.text for p in doc.paragraphs if (p.text or "").strip()).strip()
    if not text:
        raise ValueError("docx 文件未提取到文本内容")
    return text


def _extract_pdf(payload: bytes) -> str:
    try:
        from pypdf import PdfReader  # type: ignore
    except ImportError as exc:
        raise RuntimeError("未安装 pypdf，无法解析 pdf 文件") from exc
    reader = PdfReader(io.BytesIO(payload))
    texts: list[str] = []
    for page in reader.pages:
        part = page.extract_text() or ""
        if part.strip():
            texts.append(part.strip())
    text = "\n".join(texts).strip()
    if not text:
        raise ValueError("pdf 文件未提取到文本内容")
    return text

