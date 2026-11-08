import asyncio
import datetime
import io
import json
import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Literal, Protocol, TypeAlias
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx
import pymupdf as fitz
from bs4 import BeautifulSoup
from instructor.core import InstructorError
from markdownify import markdownify as html_to_markdown
from openai import APIError
from pydantic import ValidationError
from rapidfuzz import fuzz
from sqlalchemy import and_, delete, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.models import Event, EventChunk, EventTariff, LLMCache, SelectionItem
from app.schemas.event_ingestion import EventIngestionSchema
from app.services.ai_client import (
    LLM_SEMAPHORE,
    get_embedding,
    get_embeddings_batch,
    structured_llm_client,
)
from app.services.rag import (
    _is_quote_grounded,
    build_rag_cache_key,
    invalidate_rag_cache,
)

logger = logging.getLogger(__name__)

DataQualityStatus: TypeAlias = Literal["ready", "needs_enrichment"]
MAX_DOSSIER_CHARS: int = 60_000

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

_STOP_URL_EXTENSIONS: tuple[str, ...] = (
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".svg",
    ".webp",
    ".ico",
    ".css",
    ".js",
    ".zip",
    ".rar",
    ".mp4",
    ".mp3",
)

_STOP_URL_SUBSTRINGS: tuple[str, ...] = (
    "/login",
    "/register",
    "/privacy",
    "/policy",
    "/agreement",
    "/contacts",
    "/about",
    "/advertising",
    "mailto:",
    "tel:",
    "javascript:",
)


@dataclass(frozen=True)
class CustomerSourceConfig:
    """Декларативная конфигурация одной из 9 утвержденных площадок мониторинга ГК «СКАРТ»."""

    source_key: str
    display_name: str
    catalog_url: str
    card_url_patterns: tuple[str, ...]
    encoding: str = "utf-8"
    use_jina_reader: bool = False
    required_cookies: tuple[tuple[str, str], ...] = ()


CUSTOMER_SOURCES_REGISTRY: tuple[CustomerSourceConfig, ...] = (
    CustomerSourceConfig(
        source_key="expomap_construction",
        display_name="Expomap — Строительство",
        catalog_url="https://expomap.ru/expo/city/moscow/theme/stroitelstvo/",
        card_url_patterns=(r"^https?://(?:www\.)?expomap\.ru/expo/[a-z0-9\-]+/?$",),
    ),
    CustomerSourceConfig(
        source_key="expomap_design",
        display_name="Expomap — Дизайн",
        catalog_url="https://expomap.ru/expo/city/moscow/theme/dizain/",
        card_url_patterns=(r"^https?://(?:www\.)?expomap\.ru/expo/[a-z0-9\-]+/?$",),
    ),
    CustomerSourceConfig(
        source_key="architime",
        display_name="ARCHITIME",
        catalog_url="https://www.architime.ru/lecturexibition.htm",
        card_url_patterns=(r"^https?://(?:www\.)?architime\.ru/activity/202\d/[a-z0-9_\-]+\.htm$",),
        encoding="windows-1251",
    ),
    CustomerSourceConfig(
        source_key="archi_ru",
        display_name="Архи.ру",
        catalog_url="https://archi.ru/events",
        card_url_patterns=(r"^https?://(?:www\.)?archi\.ru/events/\d+/[a-z0-9_\-]+",),
        use_jina_reader=True,
    ),
    CustomerSourceConfig(
        source_key="helpinver",
        display_name="Хелпинвер",
        catalog_url="https://helpinver.com/events/",
        card_url_patterns=(r"^https?://(?:www\.)?helpinver\.com/events/[a-z0-9_\-]+/?$",),
        required_cookies=(("beget", "begetok"),),
    ),
    CustomerSourceConfig(
        source_key="archdialog",
        display_name="АрхДиалог (Timepad)",
        catalog_url="https://archdialog.timepad.ru/events/",
        card_url_patterns=(r"^https?://archdialog\.timepad\.ru/event/\d+/?$",),
    ),
    CustomerSourceConfig(
        source_key="design_mate",
        display_name="Design Mate",
        catalog_url="https://design-mate.ru/read/go",
        card_url_patterns=(r"^https?://(?:www\.)?design-mate\.ru/read/go/[a-z0-9_\-]+/?$",),
    ),
    CustomerSourceConfig(
        source_key="votkuda",
        display_name="ВотКуда",
        catalog_url="https://votkuda.ru/moskva/vyistavki",
        card_url_patterns=(r"^https?://(?:www\.)?votkuda\.ru/[a-z\-]+/vyistavki/[a-z0-9_\-]+/?$",),
    ),
    CustomerSourceConfig(
        source_key="archdaily",
        display_name="ArchDaily",
        catalog_url="https://www.archdaily.com/tag/events",
        card_url_patterns=(r"^https?://(?:www\.)?archdaily\.com/\d+/[a-z0-9\-]+/?$",),
    ),
)


class CatalogSourceScraperProtocol(Protocol):
    """Протокол адаптера обхода каталога внешней площадки (2-Hop Scraper)."""

    async def fetch_catalog_urls(self, source: CustomerSourceConfig) -> list[str]: ...


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


# [DEV-STUB: Изолированный провайдер каталогов для автономных unit-тестов без сетевых запросов]
class StubCatalogSourceScraper:
    """
    Изолированный провайдер-заглушка для тестирования пайплайна мониторинга без выхода в интернет.
    """

    async def fetch_catalog_urls(self, source: CustomerSourceConfig) -> list[str]:
        logger.info(
            "[DEV-STUB SCRAPER] Автономный режим для %s (%s).",
            source.display_name,
            source.catalog_url,
        )
        return []


def _normalize_clean_url(raw_href: str, base_url: str) -> str | None:
    """Приводит ссылку к абсолютному виду без fragment/query и отсекает невалидные схемы/расширения."""
    href = raw_href.strip()
    if not href or href.startswith("#"):
        return None
    low_href = href.lower()
    if any(sub in low_href for sub in _STOP_URL_SUBSTRINGS):
        return None

    abs_url = urljoin(base_url, href)
    parts = urlsplit(abs_url)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        return None

    clean_path = parts.path
    if any(clean_path.lower().endswith(ext) for ext in _STOP_URL_EXTENSIONS):
        return None

    normalized = urlunsplit((parts.scheme, parts.netloc, clean_path, "", ""))
    if normalized.rstrip("/") == base_url.rstrip("/"):
        return None
    return normalized


def _extract_urls_from_ld_dict(obj: dict[str, object]) -> list[str]:
    """Извлекает URL из одного объекта JSON-LD (включая вложенный itemListElement)."""
    urls: list[str] = []
    url_val = obj.get("url")
    if isinstance(url_val, str) and url_val.strip():
        urls.append(url_val.strip())

    item_list = obj.get("itemListElement")
    if not isinstance(item_list, list):
        return urls

    for el in item_list:
        if not isinstance(el, dict):
            continue
        nested_item = el.get("item")
        el_url = el.get("url") or (nested_item.get("url") if isinstance(nested_item, dict) else None)
        if isinstance(el_url, str) and el_url.strip():
            urls.append(el_url.strip())
    return urls


def _extract_urls_from_ld_json(soup: BeautifulSoup) -> list[str]:
    """Извлекает URL карточек мероприятий из блоков Schema.org (<script type='application/ld+json'>)."""
    extracted: list[str] = []
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw_json = (script.string or "").strip()
        if not raw_json:
            continue
        try:
            payload = json.loads(raw_json)
        except json.JSONDecodeError:
            continue

        items = payload if isinstance(payload, list) else [payload]
        for obj in items:
            if isinstance(obj, dict):
                extracted.extend(_extract_urls_from_ld_dict(obj))
    return extracted


def _collect_raw_links(raw_content: str) -> list[str]:
    """Собирает все сырые ссылки из HTML (<a>, JSON-LD) и Markdown-разметки."""
    raw_candidates: list[str] = []
    content_lower = raw_content.lower()
    if "<a" in content_lower or "<script" in content_lower:
        soup = BeautifulSoup(raw_content, "lxml")
        raw_candidates.extend(_extract_urls_from_ld_json(soup))
        for a_tag in soup.find_all("a", href=True):
            href_val = a_tag.get("href")
            if isinstance(href_val, str):
                raw_candidates.append(href_val)

    raw_candidates.extend(re.findall(r"\]\((https?://[^\s\)\"']+)\)", raw_content))
    return raw_candidates


def extract_filtered_card_urls(raw_content: str, source: CustomerSourceConfig) -> list[str]:
    """
    Извлекает ссылки на карточки мероприятий из HTML или Markdown (включая ответ r.jina.ai)
    и строго фильтрует их по декларативным regex-паттернам source.card_url_patterns.
    """
    raw_candidates = _collect_raw_links(raw_content)
    compiled_patterns = [re.compile(pat, re.IGNORECASE) for pat in source.card_url_patterns]
    matched_urls: list[str] = []
    seen: set[str] = set()

    for cand in raw_candidates:
        norm_url = _normalize_clean_url(cand, source.catalog_url)
        if norm_url is None or norm_url in seen:
            continue
        if any(regex.search(norm_url) for regex in compiled_patterns):
            seen.add(norm_url)
            matched_urls.append(norm_url)

    return matched_urls


async def _fetch_via_jina_reader(client: httpx.AsyncClient, target_url: str) -> str:
    """Запрашивает очищенный Markdown страницы через облачный рендер r.jina.ai."""
    jina_url = f"https://r.jina.ai/{target_url}"
    headers: dict[str, str] = {"X-With-Links-Summary": "true"}
    if settings.jina_token:
        headers["Authorization"] = f"Bearer {settings.jina_token}"
    resp = await client.get(jina_url, headers=headers)
    resp.raise_for_status()
    return resp.text.strip()


async def _fetch_raw_page_content(
    url: str,
    *,
    encoding: str = "utf-8",
    use_jina_reader: bool = False,
    cookies: dict[str, str] | None = None,
) -> tuple[str, bool]:
    """
    Загружает содержимое веб-страницы с учетом кодировки (windows-1251), cookies (beget=begetok)
    и автоматического фолбэка на r.jina.ai при SPA / JS-защите (< 300 видимых символов).
    Возвращает кортеж (content, is_markdown).
    """
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        )
    }
    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True, cookies=cookies) as client:
        if use_jina_reader:
            md_text = await _fetch_via_jina_reader(client, url)
            return md_text, True

        resp = await client.get(url, headers=headers)
        resp.raise_for_status()
        decoded_html = resp.content.decode(encoding, errors="replace")

        soup = BeautifulSoup(decoded_html, "lxml")
        visible_text = soup.get_text(" ", strip=True)
        if len(visible_text) < 300 or "хостадмин.онлайн" in visible_text.lower():
            md_text = await _fetch_via_jina_reader(client, url)
            return md_text, True

        return decoded_html, False


class HttpCatalogSourceScraper:
    """Боевой адаптер обхода каталогов 9 утвержденных площадок заказчика."""

    async def fetch_catalog_urls(self, source: CustomerSourceConfig) -> list[str]:
        cookies_dict = dict(source.required_cookies) if source.required_cookies else None
        raw_content, _ = await _fetch_raw_page_content(
            source.catalog_url,
            encoding=source.encoding,
            use_jina_reader=source.use_jina_reader,
            cookies=cookies_dict,
        )
        return extract_filtered_card_urls(raw_content, source)


def _convert_html_to_dossier_markdown(html_content: str) -> str:
    """Преобразует HTML-страницу мероприятия в очищенный Markdown с сохранением Schema.org JSON-LD в начале досье."""
    soup = BeautifulSoup(html_content, "lxml")
    ld_blocks = [
        (s.string or "").strip()
        for s in soup.find_all("script", attrs={"type": "application/ld+json"})
        if (s.string or "").strip()
    ]
    for tag in soup(["script", "style", "noscript", "svg", "footer", "nav"]):
        tag.decompose()

    md_body = str(html_to_markdown(str(soup), heading_style="ATX")).strip()
    if ld_blocks:
        ld_section = "--- SCHEMA.ORG LD+JSON ---\n" + "\n".join(ld_blocks)
        return f"{ld_section}\n\n{md_body}".strip()
    return md_body


async def fetch_url_dossier_text(
    url: str,
    source_config: CustomerSourceConfig | None = None,
) -> str:
    """
    Загружает страницу мероприятия по URL и преобразует её в структурированный Markdown-текст
    для передачи в LLM-3 (EventIngestionSchema).
    """
    enc = source_config.encoding if source_config else "utf-8"
    use_jina = source_config.use_jina_reader if source_config else False
    cookies_dict = dict(source_config.required_cookies) if (source_config and source_config.required_cookies) else None

    content, is_markdown = await _fetch_raw_page_content(
        url,
        encoding=enc,
        use_jina_reader=use_jina,
        cookies=cookies_dict,
    )
    return content if is_markdown else _convert_html_to_dossier_markdown(content)


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
    return await asyncio.to_thread(extract_relevant_pdf_text_sync, pdf_bytes)


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


async def _sync_event_chunks(
    session: AsyncSession,
    event_obj: Event,
    regulation_md: str,
) -> None:
    """
    Синхронизирует записи EventChunk для мероприятия.
    Если длина регламента превышает 35 000 символов (раздел 10.4 artifact.md),
    нарезает текст на чанки и выполняет батчевую векторизацию через get_embeddings_batch.
    """
    await session.execute(delete(EventChunk).where(EventChunk.event_id == event_obj.id))
    cleaned_md = regulation_md.strip()
    if len(cleaned_md) <= 35000:
        return

    chunks = split_regulation_into_chunks(cleaned_md)
    if not chunks:
        return

    location_desc = "Онлайн" if event_obj.is_online else (event_obj.city or "Локация не указана")
    date_desc = f"{event_obj.start_date} — {event_obj.end_date}"
    header = f"[Мероприятие: {event_obj.canonical_title} | Локация: {location_desc} | Даты: {date_desc}]\n"
    contextualized_chunks = [f"{header}{ch}" for ch in chunks]

    vectors = await get_embeddings_batch(contextualized_chunks)
    for idx, (chunk_text, vec) in enumerate(zip(contextualized_chunks, vectors)):
        session.add(
            EventChunk(
                event_id=event_obj.id,
                source_type="regulation_markdown",
                chunk_index=idx,
                content=chunk_text,
                embedding=vec,
            )
        )


def evaluate_event_quality(
    *,
    summary: str,
    regulation_md: str,
    has_tariffs: bool,
    is_online: bool,
    city: str | None,
    extra_warnings: Sequence[str] = (),
) -> tuple[DataQualityStatus, list[str]]:
    """
    Оценивает полноту карточки по итоговым (объединенным) полям в базе данных.
    Возвращает кортеж (status: 'ready' | 'needs_enrichment', warnings: list[str]).
    """
    gate_failures: list[str] = []
    if len(summary.strip()) < 250:
        gate_failures.append("summary_too_short")
    if len(regulation_md.strip()) < 600:
        gate_failures.append("regulation_markdown_too_short")
    if not has_tariffs:
        gate_failures.append("no_tariffs_extracted")
    if not is_online and not city:
        gate_failures.append("missing_city_for_offline_event")

    warnings: list[str] = list(dict.fromkeys([*extra_warnings, *gate_failures]))
    status: DataQualityStatus = "needs_enrichment" if gate_failures else "ready"
    return status, warnings


def evaluate_event_quality_gate(
    schema: EventIngestionSchema,
) -> tuple[DataQualityStatus, list[str]]:
    """Совместимая обертка над evaluate_event_quality для работы с исходной Pydantic-схемой."""
    return evaluate_event_quality(
        summary=schema.summary,
        regulation_md=schema.full_regulation_markdown,
        has_tariffs=bool(schema.tariffs),
        is_online=schema.is_online,
        city=schema.city,
        extra_warnings=schema.missing_data_warnings,
    )


def _clean_title_for_comparison(title: str) -> str:
    """Удаляет годы и спецсимволы для надежного сравнения названий мероприятий."""
    cleaned = re.sub(r"\b20\d{2}\b", " ", title.lower())
    return " ".join(re.sub(r"[^\w\s]", " ", cleaned).split())


async def find_duplicate_event(
    session: AsyncSession,
    schema: EventIngestionSchema,
    similarity_threshold: float = 85.0,
) -> Event | None:
    """
    Дедупликация событий через RapidFuzz:
    Сравнивает нормализованные названия через token_sort_ratio и ratio (>= 85%) среди событий
    того же города (или онлайн) в окне start_date +- 1 день.
    """
    date_min = schema.start_date - datetime.timedelta(days=1)
    date_max = schema.start_date + datetime.timedelta(days=1)

    loc_cond = (
        Event.is_online.is_(True)
        if schema.is_online
        else and_(Event.is_online.is_(False), Event.city == schema.city)
    )
    stmt = select(Event).where(
        loc_cond,
        Event.start_date >= date_min,
        Event.start_date <= date_max,
    )
    res = await session.execute(stmt)
    candidates = res.scalars().all()

    norm_new = _clean_title_for_comparison(schema.canonical_title)
    for existing in candidates:
        norm_existing = _clean_title_for_comparison(existing.canonical_title)
        score = max(
            float(fuzz.token_sort_ratio(norm_new, norm_existing)),
            float(fuzz.ratio(norm_new, norm_existing)),
        )
        if score >= similarity_threshold:
            return existing
    return None


async def _extract_structured_event_via_llm(raw_dossier_text: str) -> EventIngestionSchema:
    """Вызывает LLM-3 через Instructor для извлечения EventIngestionSchema из сырого текста досье."""
    if not settings.LLM_API_KEY:
        raise RuntimeError("LLM_API_KEY не задан для извлечения карточки мероприятия.")

    system_prompt = (
        "Ты — аналитик базы знаний B2B-мероприятий. Извлеки из текста структурированную карточку "
        "события по схеме EventIngestionSchema: официальное название, формат, город (или null для онлайн), "
        "даты проведения, содержательное summary (250-850 символов), подробный full_regulation_markdown, "
        "все тарифы и 3 ответа faq_cache строго по вопросам: "
        "'Что входит в рекомендованный тариф?', "
        "'Какие условия раннего бронирования и дедлайны?', "
        "'Формат участия и требования к спикеру'."
    )
    try:
        async with LLM_SEMAPHORE:
            schema: EventIngestionSchema = await asyncio.wait_for(
                structured_llm_client.chat.completions.create(
                    model=settings.LLM_MODEL,
                    response_model=EventIngestionSchema,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": raw_dossier_text},
                    ],
                    max_retries=2,
                ),
                timeout=30.0,
            )
            return schema
    except (TimeoutError, APIError, httpx.HTTPError, InstructorError):
        logger.exception("Сбой LLM при извлечении EventIngestionSchema")
        raise


async def _sync_event_tariffs(
    session: AsyncSession,
    event_obj: Event,
    schema: EventIngestionSchema,
) -> None:
    """
    Выполняет детерминированный UPSERT тарифов мероприятия.
    Предотвращает каскадный сброс recommended_tariff_id=NULL в selection_items
    при обогащении карточки из дополнительного источника.
    """
    if not schema.tariffs:
        return

    existing_tariffs_res = await session.execute(
        select(EventTariff).where(EventTariff.event_id == event_obj.id)
    )
    existing_tariffs = list(existing_tariffs_res.scalars().all())

    # Тарифы, на которые ссылаются активные элементы подборок клиентов
    ref_stmt = (
        select(SelectionItem.recommended_tariff_id)
        .where(
            SelectionItem.event_id == event_obj.id,
            SelectionItem.recommended_tariff_id.is_not(None),
        )
        .distinct()
    )
    referenced_ids = set((await session.execute(ref_stmt)).scalars().all())

    def key_fn(role: str, name: str) -> tuple[str, str]:
        return role, name.strip().lower()

    tariffs_by_key = {key_fn(t.participation_role, t.tariff_name): t for t in existing_tariffs}
    seen_keys: set[tuple[str, str]] = set()

    for t_in in schema.tariffs:
        k = key_fn(t_in.participation_role, t_in.tariff_name)
        seen_keys.add(k)
        row = tariffs_by_key.get(k)
        if row is None:
            row = EventTariff(event_id=event_obj.id)
            session.add(row)

        row.tariff_name = t_in.tariff_name
        row.participation_role = t_in.participation_role
        row.base_price = t_in.base_price
        row.early_bird_price = t_in.early_bird_price
        row.early_bird_deadline = t_in.early_bird_deadline
        row.is_vat_included = t_in.is_vat_included
        row.included_benefits = t_in.included_benefits

    # Удаляем только те старые тарифы, которые не найдены в новом источнике И на которые нет ссылок из подборок
    for k, row in tariffs_by_key.items():
        if k not in seen_keys and row.id not in referenced_ids:
            await session.delete(row)


async def _populate_faq_cache(
    session: AsyncSession,
    event_obj: Event,
    schema: EventIngestionSchema,
) -> None:
    """Предзаполняет FAQ в llm_cache, исключая тарифозависимые вопросы и неподтвержденные ответы."""
    seen_cache_keys: set[str] = set()
    reg_text = (event_obj.full_regulation_markdown or "").lower()
    for faq in schema.faq_cache:
        # Не кэшируем на уровне события (tariff_id=0) ответы, зависящие от рекомендованного тарифа
        if any(kw in faq.question.lower() for kw in ("что входит", "входит в тариф", "рекомендованный тариф")):
            continue
        ans_lower = (faq.answer or "").strip().lower()
        if not ans_lower or any(stub in ans_lower for stub in ("уточняется", "нет информаци", "не указан")):
            continue
        quote = (faq.source_quote or "").strip()
        if not quote or (quote.lower() not in reg_text and not _is_quote_grounded(quote, reg_text)):
            continue

        cache_key = build_rag_cache_key(event_obj.id, 0, faq.question)
        if cache_key in seen_cache_keys:
            continue
        seen_cache_keys.add(cache_key)
        await session.merge(
            LLMCache(
                cache_key=cache_key,
                event_id=event_obj.id,
                response_text=json.dumps(
                    {
                        "is_answer_found": True,
                        "answer_text": faq.answer,
                        "source_quote": faq.source_quote,
                    },
                    ensure_ascii=False,
                ),
            )
        )


def _merge_regulation_markdown(
    existing_md: str | None,
    new_md: str,
    source_url: str | None,
) -> str:
    """Объединяет текст регламента без бесконечного дублирования уже имеющихся параграфов."""
    clean_new = new_md.strip()
    clean_existing = (existing_md or "").strip()
    if not clean_existing:
        return clean_new
    if not clean_new:
        return clean_existing

    def norm(p: str) -> str:
        return re.sub(r"\s+", " ", p).strip().lower()

    known_paragraphs = {norm(p) for p in clean_existing.split("\n\n") if len(p.strip()) > 30}
    fresh_paragraphs = [
        p.strip() for p in clean_new.split("\n\n")
        if len(p.strip()) > 30 and norm(p) not in known_paragraphs
    ]
    if not fresh_paragraphs:
        return clean_existing

    src_label = source_url or "дополнительный источник"
    addition = "\n\n".join(fresh_paragraphs)
    return f"{clean_existing}\n\n--- Дополнение из источника ({src_label}) ---\n\n{addition}"


def _merge_into_existing(
    target: Event,
    schema: EventIngestionSchema,
    embedding_vec: list[float],
    source_url: str | None,
) -> None:
    """Обогащает карточку новыми данными без ухудшения исходных названия, дат и города."""
    if len(schema.summary) > len(target.summary or ""):
        target.summary = schema.summary
        target.summary_embedding = embedding_vec
    if schema.venue and not target.venue:
        target.venue = schema.venue
    target.themes = list(dict.fromkeys([*(target.themes or []), *schema.themes]))

    is_new_source = bool(source_url) and source_url not in (target.source_urls or [])
    if is_new_source and source_url:
        target.full_regulation_markdown = _merge_regulation_markdown(
            target.full_regulation_markdown,
            schema.full_regulation_markdown,
            source_url,
        )
        target.source_urls = [*(target.source_urls or []), source_url]


async def ingest_event_from_text(
    session: AsyncSession,
    raw_dossier_text: str,
    source_url: str | None = None,
    extra_warnings: Sequence[str] = (),
) -> Event:
    """
    Полный цикл извлечения и обогащения карточки мероприятия.
    Внимание: метод выполняет flush(), но не делает commit(). Управлением транзакцией владеет вызывающий код.
    """
    if not raw_dossier_text or not raw_dossier_text.strip():
        raise ValueError("Передан пустой текст досье для извлечения карточки мероприятия.")

    dossier_to_parse = raw_dossier_text.strip()
    collected_warnings = list(extra_warnings)
    if len(dossier_to_parse) > MAX_DOSSIER_CHARS:
        dossier_to_parse = dossier_to_parse[:MAX_DOSSIER_CHARS]
        collected_warnings.append("dossier_truncated_before_llm")

    schema = await _extract_structured_event_via_llm(dossier_to_parse)
    emb_text = f"{schema.canonical_title}. {schema.summary}. Темы: {', '.join(schema.themes)}"
    embedding_vec = await get_embedding(emb_text)

    existing = await find_duplicate_event(session, schema)
    if existing is not None:
        await invalidate_rag_cache(session, existing.id)
        event_obj = existing
        _merge_into_existing(event_obj, schema, embedding_vec, source_url)
    else:
        event_obj = Event(
            canonical_title=schema.canonical_title,
            normalized_title=schema.canonical_title.strip().lower(),
            event_format=schema.event_format,
            city=schema.city,
            is_online=schema.is_online,
            venue=schema.venue,
            start_date=schema.start_date,
            end_date=schema.end_date,
            summary=schema.summary,
            full_regulation_markdown=schema.full_regulation_markdown,
            themes=schema.themes,
            source_urls=[source_url] if source_url else [],
            summary_embedding=embedding_vec,
        )
        session.add(event_obj)
        await session.flush()

    await _sync_event_tariffs(session, event_obj, schema)
    await _sync_event_chunks(session, event_obj, event_obj.full_regulation_markdown or "")
    await _populate_faq_cache(session, event_obj, schema)

    tariffs_count_res = await session.execute(
        select(func.count(EventTariff.id)).where(EventTariff.event_id == event_obj.id)
    )
    tariffs_count = tariffs_count_res.scalar() or 0
    all_warnings = [*collected_warnings, *schema.missing_data_warnings]

    data_status, warnings = evaluate_event_quality(
        summary=event_obj.summary,
        regulation_md=event_obj.full_regulation_markdown or "",
        has_tariffs=tariffs_count > 0,
        is_online=event_obj.is_online,
        city=event_obj.city,
        extra_warnings=all_warnings,
    )
    event_obj.data_status = data_status
    event_obj.missing_data_warnings = warnings
    event_obj.is_active = data_status == "ready"

    await session.flush()
    return event_obj


async def _extract_pdf_dossier_parts(
    pdf_bytes: bytes,
    vision_ocr: VisionOCRProviderProtocol | None,
) -> tuple[list[str], list[str]]:
    """Извлекает текстовый слой и результаты Vision OCR из PDF-документа для общего досье."""
    parts: list[str] = []
    warnings: list[str] = []
    pdf_text, ocr_images = await extract_pdf_text_async(pdf_bytes)
    if pdf_text:
        parts.append(f"=== ТЕКСТ ИЗ PDF-РЕГЛАМЕНТА ===\n{pdf_text}")
    if ocr_images:
        ocr_text = ""
        if vision_ocr is not None:
            ocr_text = await vision_ocr.extract_text_from_images(ocr_images)
        if ocr_text.strip():
            parts.append(f"=== РАСПОЗНАННЫЙ OCR ТЕКСТ PDF ===\n{ocr_text.strip()}")
        else:
            warnings.append("pdf_scanned_pages_not_recognized")
    return parts, warnings


async def ingest_smart_event(
    session: AsyncSession,
    *,
    source_url: str | None = None,
    raw_text: str | None = None,
    pdf_bytes: bytes | None = None,
    vision_ocr: VisionOCRProviderProtocol | None = None,
) -> Event:
    """
    Универсальный 3-режимный умный импорт и обогащение события (get_data.md раздел 6, Способ А):
    объединяет данные из внешнего URL, вставленного текста и/или PDF-брошюры.
    """
    dossier_parts: list[str] = []
    extra_warnings: list[str] = []

    if source_url and source_url.strip():
        clean_url = source_url.strip()
        url_text = await fetch_url_dossier_text(clean_url)
        if url_text:
            dossier_parts.append(f"=== ДАННЫЕ СО СТРАНИЦЫ ({clean_url}) ===\n{url_text}")

    if raw_text and raw_text.strip():
        dossier_parts.append(f"=== ТЕКСТОВОЕ ОПИСАНИЕ / ЗАМЕТКА ===\n{raw_text.strip()}")

    if pdf_bytes:
        pdf_parts, pdf_warnings = await _extract_pdf_dossier_parts(pdf_bytes, vision_ocr)
        dossier_parts.extend(pdf_parts)
        extra_warnings.extend(pdf_warnings)

    if not dossier_parts:
        raise ValueError("Необходимо передать хотя бы один источник данных: source_url, raw_text или pdf_bytes.")

    event_obj = await ingest_event_from_text(
        session=session,
        raw_dossier_text="\n\n".join(dossier_parts),
        source_url=source_url.strip() if source_url else None,
        extra_warnings=extra_warnings,
    )
    await session.commit()
    return event_obj


@dataclass(frozen=True)
class ScrapingRunSummary:
    """Сводный результат запуска фонового мониторинга источников заказчика."""

    checked_sources: int
    discovered_urls: int
    ingested_ready_count: int
    needs_enrichment_count: int
    needs_enrichment_titles: list[str]
    failed_count: int = 0
    failed_urls: list[str] = field(default_factory=list)


async def _load_known_source_urls(session: AsyncSession) -> set[str]:
    """Загружает множество всех уже известных URL из колонки events.source_urls (SQL Delta-Check)."""
    res = await session.execute(select(Event.source_urls))
    known: set[str] = set()
    for urls_list in res.scalars().all():
        if isinstance(urls_list, list):
            for u in urls_list:
                if isinstance(u, str) and u.strip():
                    known.add(u.strip().rstrip("/"))
    return known


_INGEST_ERRORS = (
    TimeoutError,
    APIError,
    httpx.HTTPError,
    InstructorError,
    ValidationError,
    ValueError,
    RuntimeError,
    SQLAlchemyError,
)


async def _ingest_source_new_urls(
    session: AsyncSession,
    src: CustomerSourceConfig,
    new_urls: list[str],
    known_urls: set[str],
) -> tuple[int, list[str], list[str]]:
    """Обходит список новых URL одного источника и возвращает (ready_count, enrichment_titles, failed_urls)."""
    ready_count = 0
    enrichment_titles: list[str] = []
    failed_urls: list[str] = []
    for card_url in new_urls:
        try:
            dossier_text = await fetch_url_dossier_text(card_url, source_config=src)
            ev = await ingest_event_from_text(session, dossier_text, source_url=card_url)
            await session.commit()
            known_urls.add(card_url.strip().rstrip("/"))
            if ev.data_status == "ready":
                ready_count += 1
            else:
                enrichment_titles.append(ev.canonical_title)
        except _INGEST_ERRORS:
            await session.rollback()
            logger.exception("Не удалось импортировать карточку %s из источника %s", card_url, src.source_key)
            failed_urls.append(card_url)
    return ready_count, enrichment_titles, failed_urls


async def run_customer_sources_monitoring(
    session: AsyncSession,
    *,
    source_key: str | None = None,
    catalog_scraper: CatalogSourceScraperProtocol | None = None,
    max_urls_per_source: int = 10,
) -> ScrapingRunSummary:
    """
    Оркестратор мониторинга 9 утвержденных площадок ГК «СКАРТ» (get_data.md раздел 4, Шаг 0):
    1. Выбирает целевые источники из CUSTOMER_SOURCES_REGISTRY.
    2. Получает ссылки на карточки через CatalogSourceScraperProtocol.
    3. Выполняет SQL Delta-Check против уже сохраненных в БД events.source_urls.
    4. Импортирует новые мероприятия и собирает статистику READY vs NEEDS_ENRICHMENT.
    """
    sources = [s for s in CUSTOMER_SOURCES_REGISTRY if source_key is None or s.source_key == source_key]
    if not sources:
        raise LookupError(f"Источник мониторинга с ключом {source_key!r} не найден в CUSTOMER_SOURCES_REGISTRY.")

    scraper = catalog_scraper if catalog_scraper is not None else HttpCatalogSourceScraper()
    known_urls = await _load_known_source_urls(session)

    discovered_count = 0
    ready_count = 0
    enrichment_titles: list[str] = []
    total_failed_urls: list[str] = []

    for src in sources:
        try:
            card_urls = await scraper.fetch_catalog_urls(src)
        except httpx.HTTPError:
            logger.exception("Сбой загрузки каталога площадки %s (%s)", src.display_name, src.catalog_url)
            continue

        new_urls = [u for u in card_urls if u.strip().rstrip("/") not in known_urls][:max_urls_per_source]
        discovered_count += len(new_urls)
        src_ready, src_enrichment, src_failed = await _ingest_source_new_urls(session, src, new_urls, known_urls)
        ready_count += src_ready
        enrichment_titles.extend(src_enrichment)
        total_failed_urls.extend(src_failed)

    return ScrapingRunSummary(
        checked_sources=len(sources),
        discovered_urls=discovered_count,
        ingested_ready_count=ready_count,
        needs_enrichment_count=len(enrichment_titles),
        needs_enrichment_titles=enrichment_titles,
        failed_count=len(total_failed_urls),
        failed_urls=total_failed_urls,
    )
