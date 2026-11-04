import asyncio
import datetime
import json
import logging
from dataclasses import dataclass
from typing import Literal, Protocol, TypeAlias

import httpx
from openai import APIError
from rapidfuzz import fuzz
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.models import Event, EventTariff, LLMCache
from app.schemas.event_ingestion import EventIngestionSchema
from app.services.ai_client import LLM_SEMAPHORE, get_embedding, structured_llm_client
from app.services.rag import build_rag_cache_key, invalidate_rag_cache

logger = logging.getLogger(__name__)

DataQualityStatus: TypeAlias = Literal["ready", "needs_enrichment"]

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


@dataclass(frozen=True)
class CustomerSourceConfig:
    """Декларативная конфигурация одной из 9 утвержденных площадок мониторинга ГК «СКАРТ»."""

    source_key: str
    display_name: str
    catalog_url: str
    encoding: str = "utf-8"
    use_jina_reader: bool = False
    required_cookies: tuple[tuple[str, str], ...] = ()


CUSTOMER_SOURCES_REGISTRY: tuple[CustomerSourceConfig, ...] = (
    CustomerSourceConfig(
        source_key="expomap_construction",
        display_name="Expomap — Строительство",
        catalog_url="https://expomap.ru/expo/city/moscow/theme/stroitelstvo/",
    ),
    CustomerSourceConfig(
        source_key="expomap_design",
        display_name="Expomap — Дизайн",
        catalog_url="https://expomap.ru/expo/city/moscow/theme/dizain/",
    ),
    CustomerSourceConfig(
        source_key="architime",
        display_name="ARCHITIME",
        catalog_url="https://www.architime.ru/lecturexibition.htm",
        encoding="windows-1251",
    ),
    CustomerSourceConfig(
        source_key="archi_ru",
        display_name="Архи.ру",
        catalog_url="https://archi.ru/events",
        use_jina_reader=True,
    ),
    CustomerSourceConfig(
        source_key="helpinver",
        display_name="Хелпинвер",
        catalog_url="https://helpinver.com/events/",
        required_cookies=(("beget", "begetok"),),
    ),
    CustomerSourceConfig(
        source_key="archdialog",
        display_name="АрхДиалог (Timepad)",
        catalog_url="https://archdialog.timepad.ru/events/",
    ),
    CustomerSourceConfig(
        source_key="design_mate",
        display_name="Design Mate",
        catalog_url="https://design-mate.ru/read/go",
    ),
    CustomerSourceConfig(
        source_key="votkuda",
        display_name="ВотКуда",
        catalog_url="https://votkuda.ru/moskva/vyistavki",
    ),
    CustomerSourceConfig(
        source_key="archdaily",
        display_name="ArchDaily",
        catalog_url="https://www.archdaily.com/tag/events",
    ),
)


class CatalogSourceScraperProtocol(Protocol):
    """Протокол адаптера обхода каталога внешней площадки (2-Hop Scraper)."""

    async def fetch_catalog_urls(self, source: CustomerSourceConfig) -> list[str]: ...


# [DEV-STUB: Двухшаговый фоновый обход 9 внешних порталов заказчика (Hop 1 -> Hop 2) и селекторы карточек]
class StubCatalogSourceScraper:
    """
    Изолированный провайдер-заглушка для фонового краулинга внешних каталогов.
    Возвращает пустой список новых URL до подключения парсеров отдельных площадок в Спринте 3.
    """

    async def fetch_catalog_urls(self, source: CustomerSourceConfig) -> list[str]:
        logger.info(
            "[DEV-STUB SCRAPER] Пропуск обхода внешнего каталога %s (%s): адаптер в разработке.",
            source.display_name,
            source.catalog_url,
        )
        return []


def extract_relevant_pdf_text_sync(pdf_bytes: bytes) -> tuple[str, list[bytes]]:
    """
    Синхронное извлечение текстового слоя из PDF-брошюры (вызывается строго внутри asyncio.to_thread).
    # [DEV-STUB: Интеграция PyMuPDF (fitz) и рендеринг PNG-страниц для Vision LLM OCR]
    """
    if not pdf_bytes:
        raise ValueError("Передан пустой байтовый поток PDF-документа.")
    decoded_preview = pdf_bytes.decode("utf-8", errors="ignore").strip()
    return decoded_preview, []


async def extract_pdf_text_async(pdf_bytes: bytes) -> tuple[str, list[bytes]]:
    """Асинхронная обертка над CPU-bound парсингом PDF без блокировки Event Loop (rules.md п. 1.6)."""
    return await asyncio.to_thread(extract_relevant_pdf_text_sync, pdf_bytes)


def evaluate_event_quality_gate(
    schema: EventIngestionSchema,
) -> tuple[DataQualityStatus, list[str]]:
    """
    Оценивает полноту извлеченной карточки по критериям Quality Gate (get_data.md раздел 2).
    Возвращает кортеж (status: 'ready' | 'needs_enrichment', warnings: list[str]).
    """
    gate_failures: list[str] = []
    if len(schema.summary.strip()) < 250:
        gate_failures.append("summary_too_short")
    if len(schema.full_regulation_markdown.strip()) < 600:
        gate_failures.append("regulation_markdown_too_short")
    if not schema.tariffs:
        gate_failures.append("no_tariffs_extracted")
    if not schema.is_online and not schema.city:
        gate_failures.append("missing_city_for_offline_event")

    warnings: list[str] = [*schema.missing_data_warnings, *gate_failures]
    status: DataQualityStatus = "needs_enrichment" if gate_failures else "ready"
    return status, warnings


async def find_duplicate_event(
    session: AsyncSession,
    schema: EventIngestionSchema,
    similarity_threshold: float = 82.0,
) -> Event | None:
    """
    Дедупликация событий через RapidFuzz (get_data.md раздел 4, Шаг 6):
    Сравнивает нормализованные названия среди событий того же города (или онлайн) в окне start_date +- 1 день.
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

    norm_new = schema.canonical_title.strip().lower()
    for existing in candidates:
        norm_existing = (existing.normalized_title or existing.canonical_title).strip().lower()
        score = float(fuzz.token_sort_ratio(norm_new, norm_existing))
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
        "все тарифы с НДС и 3 ответа faq_cache."
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
    except (TimeoutError, APIError, httpx.HTTPError):
        logger.exception("Сбой LLM при извлечении EventIngestionSchema")
        raise


def _populate_event_tariffs_and_faq(
    session: AsyncSession,
    event_obj: Event,
    schema: EventIngestionSchema,
) -> None:
    """Создает связанные записи EventTariff и предзаполняет LLMCache из EventIngestionSchema."""
    for t_in in schema.tariffs:
        session.add(
            EventTariff(
                event_id=event_obj.id,
                tariff_name=t_in.tariff_name,
                participation_role=t_in.participation_role,
                base_price=t_in.base_price,
                early_bird_price=t_in.early_bird_price,
                early_bird_deadline=t_in.early_bird_deadline,
                is_vat_included=t_in.is_vat_included,
                included_benefits=t_in.included_benefits,
            )
        )

    for faq in schema.faq_cache:
        cache_key = build_rag_cache_key(event_obj.id, 0, faq.question)
        session.add(
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


def _apply_schema_to_event(
    target: Event,
    schema: EventIngestionSchema,
    data_status: DataQualityStatus,
    warnings: list[str],
    embedding_vec: list[float],
    source_url: str | None,
) -> None:
    """Копирует атрибуты EventIngestionSchema и статус Quality Gate в ORM-объект Event."""
    target.canonical_title = schema.canonical_title
    target.normalized_title = schema.canonical_title.strip().lower()
    target.event_format = schema.event_format
    target.city = schema.city
    target.is_online = schema.is_online
    target.venue = schema.venue
    target.start_date = schema.start_date
    target.end_date = schema.end_date
    target.summary = schema.summary
    target.full_regulation_markdown = schema.full_regulation_markdown
    target.themes = list(schema.themes)
    target.data_status = data_status
    target.missing_data_warnings = warnings
    target.is_active = data_status == "ready"
    target.summary_embedding = embedding_vec
    if source_url and source_url not in (target.source_urls or []):
        target.source_urls = [*(target.source_urls or []), source_url]


async def ingest_event_from_text(
    session: AsyncSession,
    raw_dossier_text: str,
    source_url: str | None = None,
) -> Event:
    """
    Полный цикл импорта и обогащения карточки мероприятия:
    1. Извлекает EventIngestionSchema через LLM-3.
    2. Проверяет Quality Gate (ready vs needs_enrichment) и дубли через RapidFuzz.
    3. Вычисляет 1024-мерный эмбеддинг summary_embedding через Jina AI.
    4. Сохраняет/обновляет мероприятие, его тарифы и сбрасывает устаревший кэш RAG.
    """
    schema = await _extract_structured_event_via_llm(raw_dossier_text)
    data_status, warnings = evaluate_event_quality_gate(schema)
    emb_text = f"{schema.canonical_title}. {schema.summary}. Темы: {', '.join(schema.themes)}"
    embedding_vec = await get_embedding(emb_text)

    existing = await find_duplicate_event(session, schema)
    if existing is not None:
        await invalidate_rag_cache(session, existing.id)
        event_obj = existing
        _apply_schema_to_event(event_obj, schema, data_status, warnings, embedding_vec, source_url)
    else:
        event_obj = Event(source_urls=[source_url] if source_url else [])
        _apply_schema_to_event(event_obj, schema, data_status, warnings, embedding_vec, source_url)
        session.add(event_obj)
        await session.flush()

    _populate_event_tariffs_and_faq(session, event_obj, schema)
    await session.commit()
    return event_obj
