import asyncio
import base64
import io
import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol, cast

import httpx
import pymupdf as fitz
from openai import APIError
from openai.types.chat import ChatCompletionMessageParam

logger = logging.getLogger(__name__)

_VISION_OCR_SYSTEM_PROMPT = (
    "Ты — OCR-экстрактор для B2B-мероприятий. Извлеки со сканов весь читаемый текст "
    "максимально точно: названия тарифов и пакетов участия, цены (с указанием с НДС / + НДС), "
    "скидки Early Bird и дедлайны, даты, город, условия участия и спикерства. "
    "Не выдумывай цифры, сохраняй таблицы в Markdown."
)

_PRICE_CURRENCY_RE = re.compile(
    r"\b\d[\d\s\u00a0.,]{0,15}(?:тыс\.?\s*)?"
    r"(?:₽|руб(?:лей|ля|ль)?(?=\s|$|[.,;:!?)/»\"])|rub\b|"
    r"т\.\s*р\.?(?=\s|$|[.,;:!?)/»\"])|р\.(?=\s|$|[.,;:!?)/»\"]))",
    re.IGNORECASE,
)
_TARIFF_KEYWORD_RE = re.compile(
    r"(?:тариф|пакет|стоимост|\bцен(?:а|ы|е|у|ой)?\b|взнос|\bearly[\s\-_]*bird\b|бесплатн)",
    re.IGNORECASE,
)
_FREE_PARTICIPATION_RE = re.compile(
    r"(?<!не\s)(?:участие\s+бесплатн|бесплатн\w+\s+участи|вход\s+свободн|"
    r"свободн\w+\s+вход|бесплатн\w+\s+посещени|посещени\w+\s+бесплатн|"
    r"бесплатн\w+\s+регистрац|регистрац\w+\s+бесплатн|"
    r"free\s+(?:admission|entry|attendance|registration))",
    re.IGNORECASE,
)

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
    "посетител",
    "аудитор",
    "участник",
    "компани",
    "организатор",
    "контакт",
    "телефон",
    "vip",
    "гост",
    "стенд",
    "выстав",
    "деловая",
    "журнал",
    "сми",
    "требован",
    "формат",
    "куратор",
    "манифест",
    "медиа",
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


@dataclass
class OcrBudgetTracker:
    """Трекер квоты страниц Vision OCR на один прогон мониторинга для защиты бюджета."""

    remaining_pages: int
    used_pages: int = 0

    def reserve(self, requested: int, *, per_doc_limit: int) -> int:
        """Резервирует не более per_doc_limit страниц в пределах оставшегося лимита."""
        if requested <= 0 or per_doc_limit <= 0 or self.remaining_pages <= 0:
            return 0
        allowed = min(requested, per_doc_limit, self.remaining_pages)
        self.remaining_pages -= allowed
        self.used_pages += allowed
        return allowed


def _has_price_tariff_signal(text: str, *, max_distance: int = 300) -> bool:
    price_spans = [(m.start(), m.end()) for m in _PRICE_CURRENCY_RE.finditer(text)]
    if not price_spans:
        return False
    kw_spans = [(m.start(), m.end()) for m in _TARIFF_KEYWORD_RE.finditer(text)]
    if not kw_spans:
        return False
    for p_start, p_end in price_spans:
        for k_start, k_end in kw_spans:
            gap = max(0, max(p_start - k_end, k_start - p_end))
            if gap <= max_distance:
                return True
    return False


def should_run_vision_ocr(
    existing_text: str,
    pdf_text: str,
    ocr_images: Sequence[bytes],
) -> bool:
    """
    Budget Gate для Vision OCR:
    - без картинок OCR не нужен;
    - если текстовый слой PDF почти пуст (< 200 символов), PDF является сканом -> нужен OCR;
    - иначе, если объединенный текст (>= 600 символов) уже содержит явные цены рядом с
      тарифными словами или явный сигнал бесплатного участия, не тратим бюджет на Vision OCR.
    """
    if not ocr_images:
        return False
    if len((pdf_text or "").strip()) < 200:
        return True
    combined = f"{existing_text or ''}\n{pdf_text or ''}".strip()
    if len(combined) < 600:
        return True
    return not (_has_price_tariff_signal(combined) or _FREE_PARTICIPATION_RE.search(combined))


def _detect_image_mime(image_bytes: bytes) -> str:
    if image_bytes.startswith(b"\xff\xd8"):
        return "image/jpeg"
    return "image/png"


def _extract_message_text(content: object) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                text_val = item.get("text")
                if isinstance(text_val, str) and text_val.strip():
                    parts.append(text_val.strip())
            elif hasattr(item, "text"):
                text_val = getattr(item, "text", None)
                if isinstance(text_val, str) and text_val.strip():
                    parts.append(text_val.strip())
        return "\n".join(parts).strip()
    return ""


class OpenAICompatibleVisionOCRProvider:
    """Бюджетный Vision OCR-провайдер через OpenAI-совместимый шлюз (RuOpenRouter)."""

    def __init__(
        self,
        model: str,
        *,
        max_pages: int = 6,
        batch_size: int = 3,
        max_tokens: int = 4000,
        timeout_sec: float = 45.0,
    ) -> None:
        self.model = model
        self.max_pages = max_pages
        self.batch_size = max(1, batch_size)
        self.max_tokens = max(1, max_tokens)
        self.timeout_sec = timeout_sec
        self.last_usage: dict[str, int] | None = None

    async def extract_text_from_images(self, images_png: Sequence[bytes]) -> str:
        import app.services.scraper as scraper_pkg

        valid_images = [img for img in images_png if img]
        if not valid_images or self.max_pages <= 0:
            return ""

        limited_images = valid_images[: self.max_pages]
        extracted_batches: list[str] = []
        total_prompt_tokens = 0
        total_completion_tokens = 0
        total_tokens = 0
        has_usage = False

        for start in range(0, len(limited_images), self.batch_size):
            batch = limited_images[start : start + self.batch_size]
            user_content: list[dict[str, object]] = [
                {
                    "type": "text",
                    "text": (
                        f"Распознай текст с {len(batch)} отсканированных страниц PDF-документа "
                        "и верни извлеченный текст в Markdown."
                    ),
                }
            ]
            for img_bytes in batch:
                mime = _detect_image_mime(img_bytes)
                b64 = base64.b64encode(img_bytes).decode("ascii")
                user_content.append(
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{mime};base64,{b64}",
                            "detail": "auto",
                        },
                    }
                )

            messages = cast(
                list[ChatCompletionMessageParam],
                [
                    {"role": "system", "content": _VISION_OCR_SYSTEM_PROMPT},
                    {"role": "user", "content": user_content},
                ],
            )

            try:
                async with scraper_pkg.LLM_SEMAPHORE:
                    response = await asyncio.wait_for(
                        scraper_pkg.raw_openai_client.chat.completions.create(
                            model=self.model,
                            messages=messages,
                            max_tokens=self.max_tokens,
                            temperature=0.0,
                        ),
                        timeout=self.timeout_sec,
                    )
            except (TimeoutError, APIError, httpx.HTTPError, OSError) as exc:
                logger.warning(
                    "Сбой Vision OCR (model=%s, batch_pages=%d): %s",
                    self.model,
                    len(batch),
                    exc,
                )
                continue

            usage = getattr(response, "usage", None)
            if usage is not None:
                has_usage = True
                total_prompt_tokens += int(getattr(usage, "prompt_tokens", 0) or 0)
                total_completion_tokens += int(getattr(usage, "completion_tokens", 0) or 0)
                total_tokens += int(getattr(usage, "total_tokens", 0) or 0)

            choices = getattr(response, "choices", None) or []
            if not choices:
                continue
            msg = getattr(choices[0], "message", None)
            batch_text = _extract_message_text(getattr(msg, "content", None))
            if batch_text:
                extracted_batches.append(batch_text)

        if has_usage:
            self.last_usage = {
                "prompt_tokens": total_prompt_tokens,
                "completion_tokens": total_completion_tokens,
                "total_tokens": total_tokens,
            }
        return "\n\n".join(extracted_batches).strip()


def build_vision_ocr_provider() -> VisionOCRProviderProtocol | None:
    """
    Создает Vision OCR-провайдер только при явно заданных VISION_OCR_MODEL и LLM_API_KEY.
    Никогда не подставляет текстовую модель settings.LLM_MODEL.
    """
    import app.services.scraper as scraper_pkg

    model = (scraper_pkg.settings.VISION_OCR_MODEL or "").strip()
    api_key = (scraper_pkg.settings.LLM_API_KEY or "").strip()
    if not model or not api_key:
        return None
    max_pages = max(
        scraper_pkg.settings.VISION_OCR_MAX_PAGES_AUTO,
        scraper_pkg.settings.VISION_OCR_MAX_PAGES_MANUAL,
    )
    return OpenAICompatibleVisionOCRProvider(model=model, max_pages=max_pages)


def _validate_pdf_bytes(pdf_bytes: bytes) -> None:
    """Проверяет непустоту и сигнатуру %PDF у переданного байтового потока."""
    if not pdf_bytes:
        raise ValueError("Передан пустой байтовый поток PDF-документа.")
    if not pdf_bytes.lstrip().startswith(b"%PDF"):
        raise ValueError("Переданный файл не является валидным PDF-документом (отсутствует сигнатура %PDF).")


def extract_relevant_pdf_text_sync(
    pdf_bytes: bytes,
    max_ocr_pages: int = 5,
    max_image_side_px: int = 1280,
    include_all_if_compact: bool = False,
    compact_char_threshold: int = 18_000,
) -> tuple[str, list[bytes]]:
    """
    Синхронное извлечение текстового слоя из PDF-брошюры через PyMuPDF (fitz).
    Всегда включает первые 2 страницы (обложка + оглавление) и страницы,
    содержащие ключевые слова из IMPORTANT_PDF_KEYWORDS (get_data.md раздел 4, Шаг 4Б и раздел 5.2).
    При include_all_if_compact=True и суммарном текстовом слое <= compact_char_threshold
    сохраняет все текстовые страницы без фильтрации по ключевым словам.
    Страницы без текстового слоя (< 50 символов) рендерятся с адаптивным масштабированием
    так, чтобы длинная сторона не превышала max_image_side_px.
    Вызывается строго внутри asyncio.to_thread.
    """
    _validate_pdf_bytes(pdf_bytes)
    if max_image_side_px <= 0:
        raise ValueError("max_image_side_px должен быть положительным числом.")

    all_text_pages: list[tuple[int, str]] = []
    relevant_text_blocks: list[str] = []
    ocr_images_bytes: list[bytes] = []

    with fitz.open(stream=io.BytesIO(pdf_bytes), filetype="pdf") as doc:
        for page_num in range(min(len(doc), 50)):
            page = doc[page_num]
            raw_text = str(page.get_text("text") or "").strip()
            if len(raw_text) < 50:
                if max_ocr_pages > 0 and len(ocr_images_bytes) < max_ocr_pages:
                    max_side = max(page.rect.width, page.rect.height, 1.0)
                    scale = min(135.0 / 72.0, max_image_side_px / max_side)
                    pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
                    ocr_images_bytes.append(pix.tobytes("png"))
                continue

            all_text_pages.append((page_num, raw_text))
            text_lower = raw_text.lower()
            if page_num in (0, 1) or any(kw in text_lower for kw in IMPORTANT_PDF_KEYWORDS):
                relevant_text_blocks.append(f"--- СТРАНИЦА PDF {page_num + 1} ---\n{raw_text}")

    if include_all_if_compact and all_text_pages:
        total_chars = sum(len(txt) for _, txt in all_text_pages)
        if total_chars <= compact_char_threshold:
            relevant_text_blocks = [
                f"--- СТРАНИЦА PDF {page_num + 1} ---\n{raw_text}"
                for page_num, raw_text in all_text_pages
            ]

    return "\n\n".join(relevant_text_blocks), ocr_images_bytes


async def extract_pdf_text_async(
    pdf_bytes: bytes,
    max_ocr_pages: int = 5,
    max_image_side_px: int = 1280,
    include_all_if_compact: bool = False,
) -> tuple[str, list[bytes]]:
    """Асинхронная обертка над CPU-bound парсингом PDF без блокировки Event Loop (rules.md п. 1.6)."""
    import app.services.scraper as scraper_pkg

    kwargs = {
        "max_ocr_pages": max_ocr_pages,
        "max_image_side_px": max_image_side_px,
    }
    if include_all_if_compact:
        kwargs["include_all_if_compact"] = True
    return await asyncio.to_thread(
        scraper_pkg.extract_relevant_pdf_text_sync,
        pdf_bytes,
        **kwargs,  # type: ignore[arg-type]
    )


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
