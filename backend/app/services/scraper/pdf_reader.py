import asyncio
import io
import logging
from collections.abc import Sequence
from typing import Protocol

import pymupdf as fitz

logger = logging.getLogger(__name__)

IMPORTANT_PDF_KEYWORDS: tuple[str, ...] = (
    "тариф",
    "стоимость",
    "цена",
    "руб",
    "₽",
    "ндс",
    "пакет",
    "спикер",
    "делегат",
    "спонсор",
    "партнер",
    "early bird",
    "скидк",
    "программа",
    "сессия",
    "круглый стол",
    "регламент",
    "аккредитац",
    "бейд",
    "парковк",
    "трансфер",
    "оферт",
    "возврат",
)


class VisionOCRProviderProtocol(Protocol):
    """Протокол распознавания отсканированных страниц PDF без текстового слоя."""

    async def extract_text_from_images(self, images_png: Sequence[bytes]) -> str: ...


# [DEV-STUB: Распознавание отсканированных страниц PDF без текстового слоя через внешнюю Vision LLM]
class StubVisionOCRProvider:
    """
    Изолированный провайдер-заглушка для распознавания сканов страниц PDF.
    Используется по умолчанию, когда текстовый слой PDF уже извлечен через PyMuPDF.
    """

    async def extract_text_from_images(self, images_png: Sequence[bytes]) -> str:
        logger.info(
            "[DEV-STUB VISION OCR] Пропуск OCR для %d PNG-страниц без текстового слоя.",
            len(images_png),
        )
        return ""


def _validate_pdf_bytes(pdf_bytes: bytes) -> None:
    """Проверяет непустоту и сигнатуру %PDF у переданного байтового потока."""
    if not pdf_bytes:
        raise ValueError("Передан пустой байтовый поток PDF-документа.")
    if not pdf_bytes.lstrip().startswith(b"%PDF"):
        raise ValueError("Переданный файл не является валидным PDF-документом (отсутствует сигнатура %PDF).")


def extract_relevant_pdf_text_sync(pdf_bytes: bytes) -> tuple[str, list[bytes]]:
    """
    Синхронное извлечение текстового слоя из PDF-брошюры через PyMuPDF (fitz).
    Всегда включает первые 2 страницы (обложка + оглавление) и страницы,
    содержащие ключевые слова из IMPORTANT_PDF_KEYWORDS (get_data.md раздел 4, Шаг 4Б и раздел 5.2).
    Вызывается строго внутри asyncio.to_thread.
    """
    _validate_pdf_bytes(pdf_bytes)
    relevant_text_blocks: list[str] = []
    ocr_images_bytes: list[bytes] = []

    with fitz.open(stream=io.BytesIO(pdf_bytes), filetype="pdf") as doc:
        for page_num in range(min(len(doc), 50)):
            page = doc[page_num]
            raw_text = str(page.get_text("text") or "").strip()
            if len(raw_text) < 50:
                if len(ocr_images_bytes) < 5:
                    ocr_images_bytes.append(page.get_pixmap(dpi=150).tobytes("png"))
                continue

            text_lower = raw_text.lower()
            if page_num in (0, 1) or any(kw in text_lower for kw in IMPORTANT_PDF_KEYWORDS):
                relevant_text_blocks.append(f"--- СТРАНИЦА PDF {page_num + 1} ---\n{raw_text}")

    return "\n\n".join(relevant_text_blocks), ocr_images_bytes


async def extract_pdf_text_async(pdf_bytes: bytes) -> tuple[str, list[bytes]]:
    """Асинхронная обертка над CPU-bound парсингом PDF без блокировки Event Loop (rules.md п. 1.6)."""
    import app.services.scraper as scraper_pkg

    return await asyncio.to_thread(scraper_pkg.extract_relevant_pdf_text_sync, pdf_bytes)


def split_regulation_into_chunks(
    markdown_text: str,
    chunk_size: int = 2500,
    overlap: int = 250,
) -> list[str]:
    """
    Нарезает длинный текст регламента на перекрывающиеся смысловые фрагменты для таблицы event_chunks.
    Используется при превышении порога Context Stuffing (35 000 символов, раздел 10.4 artifact.md).
    """
    cleaned = markdown_text.strip()
    if not cleaned:
        return []
    if chunk_size <= overlap:
        raise ValueError("chunk_size должен быть строго больше overlap.")
    if len(cleaned) <= chunk_size:
        return [cleaned]

    chunks: list[str] = []
    step = chunk_size - overlap
    start = 0
    total_len = len(cleaned)
    while start < total_len:
        end = min(start + chunk_size, total_len)
        fragment = cleaned[start:end].strip()
        if fragment:
            chunks.append(fragment)
        if end >= total_len:
            break
        start += step
    return chunks
