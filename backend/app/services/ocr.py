from __future__ import annotations

import io

from app.core.logging import get_logger

log = get_logger(__name__)

MAX_OCR_CHARS = 4000


def image_to_text(data: bytes) -> str | None:
    if not data:
        return None
    try:
        import pytesseract
        from PIL import Image
    except ImportError:
        log.warning("ocr_unavailable", reason="pytesseract не установлен")
        return None
    try:
        image = Image.open(io.BytesIO(data))
        text = pytesseract.image_to_string(image, lang="rus+eng")
    except Exception as exc:
        log.warning("ocr_failed", error=str(exc))
        return None
    cleaned = str(text).strip()
    if not cleaned:
        return None
    return cleaned[:MAX_OCR_CHARS]
