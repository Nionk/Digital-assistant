import logging
from dataclasses import dataclass, field

import httpx
from instructor.core import InstructorError
from openai import APIError
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Event
from app.services.scraper.sources import (
    CatalogSourceScraperProtocol,
    CustomerSourceConfig,
)

logger = logging.getLogger(__name__)


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
    import app.services.scraper as scraper_pkg

    ready_count = 0
    enrichment_titles: list[str] = []
    failed_urls: list[str] = []
    for card_url in new_urls:
        try:
            dossier_text = await scraper_pkg.fetch_url_dossier_text(card_url, source_config=src)
            ev = await scraper_pkg.ingest_event_from_text(session, dossier_text, source_url=card_url)
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
    import app.services.scraper as scraper_pkg

    sources = [s for s in scraper_pkg.CUSTOMER_SOURCES_REGISTRY if source_key is None or s.source_key == source_key]
    if not sources:
        raise LookupError(f"Источник мониторинга с ключом {source_key!r} не найден в CUSTOMER_SOURCES_REGISTRY.")

    scraper = catalog_scraper if catalog_scraper is not None else scraper_pkg.HttpCatalogSourceScraper()
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
