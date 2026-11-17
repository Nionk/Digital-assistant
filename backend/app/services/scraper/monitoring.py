import datetime
import hashlib
import inspect
import json
import logging
import re
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from urllib.parse import urlsplit, urlunsplit

import httpx
from instructor.core import InstructorError
from openai import APIError
from pydantic import ValidationError
from rapidfuzz import fuzz
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Event, ScraperSeenUrl, ScraperSource
from app.services.scraper.crawler import CollectedEventDossier, _filter_supported_kwargs
from app.services.scraper.ingestion import _clean_title_for_comparison, _get_app_today
from app.services.scraper.pdf_reader import OcrBudgetTracker, VisionOCRProviderProtocol
from app.services.scraper.sources import (
    CatalogSourceScraperProtocol,
    CustomerSourceConfig,
    DiscoveredCandidate,
    DiscoveryResult,
    canonicalize_url,
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
    dry_run: bool = False
    rejected_b2c_count: int = 0
    rejected_geo_count: int = 0
    per_source_report: list[dict[str, object]] = field(default_factory=list)
    candidate_urls_preview: list[str] = field(default_factory=list)
    rejected_past_count: int = 0
    vision_ocr_pages_used: int = 0
    events_created_count: int = 0
    events_updated_count: int = 0


@dataclass
class _SeenUrlState:
    outcome: str
    recheck_attempts: int
    content_hash: str | None = None
    event_id: int | None = None


@dataclass
class _SourceIngestResult:
    ready_count: int = 0
    enrichment_titles: list[str] = field(default_factory=list)
    failed_urls: list[str] = field(default_factory=list)
    rejected_b2c: int = 0
    rejected_geo: int = 0
    rejected_past: int = 0
    created_count: int = 0
    updated_count: int = 0
    saved_events: list[dict[str, object]] = field(default_factory=list)


def _url_lookup_key(url: str) -> str:
    canon = canonicalize_url(url) or url.strip()
    parts = urlsplit(canon)
    if parts.scheme and parts.netloc:
        clean_path = parts.path.rstrip("/")
        return urlunsplit((parts.scheme, parts.netloc, clean_path, parts.query, ""))
    return canon.rstrip("/")


async def _load_known_source_urls(session: AsyncSession) -> set[str]:
    """Загружает множество всех уже известных URL из колонки events.source_urls (SQL Delta-Check)."""
    res = await session.execute(select(Event.source_urls))
    known: set[str] = set()
    for urls_list in res.scalars().all():
        if isinstance(urls_list, list):
            for u in urls_list:
                if isinstance(u, str) and u.strip():
                    known.add(_url_lookup_key(u))
    return known


_OCR_SECTION_RE = re.compile(
    r"===\s*РАСПОЗНАННЫЙ OCR ТЕКСТ PDF\s*===.*?(?=(?:\n===\s+[^\n]+?\s+===)|\Z)",
    re.DOTALL,
)


def _compute_dossier_hash(
    dossiers: Sequence[CollectedEventDossier],
    *,
    include_text: bool = True,
) -> str:
    """
    Детерминированный SHA-256 хэш досье для проверки изменений страницы без вызова LLM/OCR.
    Исключает OCR-блок, чтобы recheck без Vision OCR давал тот же хэш при неизменном сайте.
    """
    payload: list[dict[str, object]] = []
    for dossier in dossiers:
        sorted_urls = sorted(
            {
                _url_lookup_key(u)
                for u in (dossier.source_urls or [])
                if isinstance(u, str) and u.strip()
            }
        )
        entry: dict[str, object] = {"urls": sorted_urls}
        if include_text:
            raw_text = _OCR_SECTION_RE.sub("", dossier.dossier_text or "")
            entry["text"] = re.sub(r"\s+", " ", raw_text).strip()
        payload.append(entry)
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


async def _load_active_ready_events(
    session: AsyncSession,
) -> list[tuple[int, str, datetime.date, datetime.date, str]]:
    """Загружает компактный список активных ready-событий для раннего pre-dedup до краулинга."""
    stmt = select(
        Event.id,
        Event.canonical_title,
        Event.start_date,
        Event.end_date,
        Event.data_status,
    ).where(Event.data_status == "ready", Event.is_active.is_(True))
    try:
        res = await session.execute(stmt)
        rows = res.all()
    except (TypeError, AttributeError, SQLAlchemyError):
        return []
    ready_list: list[tuple[int, str, datetime.date, datetime.date, str]] = []
    for row in rows:
        if (
            isinstance(row, tuple)
            or hasattr(row, "__len__")
        ) and len(row) >= 5:
            ev_id, title, start_dt, end_dt, status_val = row[0], row[1], row[2], row[3], row[4]
            if (
                isinstance(ev_id, int)
                and isinstance(title, str)
                and isinstance(start_dt, datetime.date)
                and isinstance(end_dt, datetime.date)
            ):
                ready_list.append((ev_id, title, start_dt, end_dt, str(status_val)))
    return ready_list


def _find_pre_dedup_event_id(
    candidate_title: str | None,
    ready_events: Sequence[tuple[int, str, datetime.date, datetime.date, str]],
    today: datetime.date,
) -> int | None:
    """Возвращает ID уже готового актуального события при высоком совпадении заголовка (>= 92%)."""
    if not candidate_title or len(candidate_title.strip()) < 6:
        return None
    cand_clean = _clean_title_for_comparison(candidate_title)
    if len(cand_clean) < 6:
        return None
    for ev_id, ev_title, _start_dt, end_dt, _status in ready_events:
        if end_dt < today:
            continue
        ev_clean = _clean_title_for_comparison(ev_title)
        if not ev_clean:
            continue
        if float(fuzz.token_set_ratio(cand_clean, ev_clean)) >= 92.0:
            return ev_id
    return None


async def _load_seen_urls_map(session: AsyncSession) -> dict[str, _SeenUrlState]:
    """Загружает историю проверенных URL из scraper_seen_urls в виде plain Python состояний."""
    res = await session.execute(select(ScraperSeenUrl))
    seen_map: dict[str, _SeenUrlState] = {}
    for row in res.scalars().all():
        if not isinstance(row, ScraperSeenUrl) or not row.url or not row.url.strip():
            continue
        seen_map[_url_lookup_key(row.url)] = _SeenUrlState(
            outcome=row.outcome,
            recheck_attempts=int(row.recheck_attempts or 0),
            content_hash=getattr(row, "content_hash", None),
            event_id=getattr(row, "event_id", None),
        )
    return seen_map


def _should_skip_url(
    url_key: str,
    seen_map: dict[str, _SeenUrlState],
    known_urls: set[str],
) -> bool:
    """
    Проверяет, следует ли пропустить URL:
    - ingested_ready / rejected_b2c / rejected_geo / rejected_past / ignored -> пропуск;
    - ingested_needs_enrichment -> разрешена ровно 1 повторная проверка (recheck_attempts < 1);
    - failed -> разрешен повторный обход;
    - legacy events.source_urls (отсутствующие в scraper_seen_urls) -> пропуск.
    """
    state = seen_map.get(url_key)
    if state is not None:
        if state.outcome in (
            "ingested_ready",
            "rejected_b2c",
            "rejected_geo",
            "rejected_past",
            "ignored",
        ):
            return True
        if state.outcome == "ingested_needs_enrichment":
            return state.recheck_attempts >= 1
        return False
    return url_key in known_urls


async def _upsert_seen_url(
    session: AsyncSession,
    *,
    raw_url: str,
    source_key: str,
    outcome: str,
    event_id: int | None,
    last_error: str | None,
    seen_map: dict[str, _SeenUrlState],
    content_hash: str | None = None,
) -> None:
    canon_url = canonicalize_url(raw_url) or raw_url.strip()
    url_key = _url_lookup_key(canon_url)
    prev_state = seen_map.get(url_key)
    was_needs_enrichment = prev_state is not None and prev_state.outcome == "ingested_needs_enrichment"

    res = await session.execute(select(ScraperSeenUrl).where(ScraperSeenUrl.url == url_key))
    row_obj = res.scalar_one_or_none()
    if row_obj is None:
        legacy_candidates = [u for u in (f"{url_key}/", canon_url) if u and u != url_key]
        for legacy_url in legacy_candidates:
            legacy_res = await session.execute(
                select(ScraperSeenUrl).where(ScraperSeenUrl.url == legacy_url)
            )
            row_obj = legacy_res.scalar_one_or_none()
            if isinstance(row_obj, ScraperSeenUrl):
                row_obj.url = url_key
                break
    now_ts = datetime.datetime.now(datetime.UTC)

    effective_hash = content_hash if content_hash is not None else (
        row_obj.content_hash if isinstance(row_obj, ScraperSeenUrl) else (
            prev_state.content_hash if prev_state is not None else None
        )
    )

    if isinstance(row_obj, ScraperSeenUrl):
        if row_obj.outcome == "ingested_needs_enrichment" or was_needs_enrichment:
            row_obj.recheck_attempts = int(row_obj.recheck_attempts or 0) + 1
        row_obj.url = url_key
        row_obj.source_key = source_key
        row_obj.outcome = outcome
        row_obj.event_id = event_id
        row_obj.content_hash = effective_hash
        row_obj.last_error = last_error
        row_obj.last_checked_at = now_ts
        new_attempts = row_obj.recheck_attempts
    else:
        new_attempts = (prev_state.recheck_attempts + 1) if was_needs_enrichment and prev_state else 0
        row_obj = ScraperSeenUrl(
            url=url_key,
            source_key=source_key,
            outcome=outcome,
            event_id=event_id,
            recheck_attempts=new_attempts,
            content_hash=effective_hash,
            last_error=last_error,
            last_checked_at=now_ts,
        )
        session.add(row_obj)

    seen_map[url_key] = _SeenUrlState(
        outcome=outcome,
        recheck_attempts=new_attempts,
        content_hash=effective_hash,
        event_id=event_id,
    )


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


async def _ingest_source_candidates(
    session: AsyncSession,
    src: CustomerSourceConfig,
    new_candidates: Sequence[DiscoveredCandidate | str],
    known_urls: set[str],
    seen_map: dict[str, _SeenUrlState] | None = None,
    *,
    vision_ocr: VisionOCRProviderProtocol | None = None,
    ocr_budget: OcrBudgetTracker | None = None,
) -> _SourceIngestResult:
    """Выполняет триаж (при b2b_filter_enabled), 2-Hop краулинг и LLM-3/гео/дату-ингест кандидатов источника."""
    import app.services.scraper as scraper_pkg

    active_seen_map = seen_map if seen_map is not None else {}
    res = _SourceIngestResult()
    today = _get_app_today()
    active_ready_events = await _load_active_ready_events(session)

    for raw_item in new_candidates:
        candidate = (
            raw_item
            if isinstance(raw_item, DiscoveredCandidate)
            else DiscoveredCandidate(url=raw_item, source_key=src.source_key)
        )
        card_url = candidate.url
        url_key = _url_lookup_key(card_url)
        prev_state = active_seen_map.get(url_key)
        try:
            matched_ready_id = _find_pre_dedup_event_id(
                candidate.title, active_ready_events, today
            )
            if matched_ready_id is not None:
                logger.info(
                    "Ранний pre-dedup: кандидат %s (%r) совпал с ready-событием ID=%d",
                    card_url,
                    candidate.title,
                    matched_ready_id,
                )
                await _upsert_seen_url(
                    session,
                    raw_url=card_url,
                    source_key=src.source_key,
                    outcome="ingested_ready",
                    event_id=matched_ready_id,
                    last_error=None,
                    seen_map=active_seen_map,
                )
                await session.commit()
                known_urls.add(url_key)
                continue

            if src.b2b_filter_enabled:
                decision = await scraper_pkg.triage_discovery_candidate(candidate, src)
                if not decision.is_b2b_target or not decision.is_russia_or_online:
                    rej_outcome = "rejected_b2c" if not decision.is_b2b_target else "rejected_geo"
                    await _upsert_seen_url(
                        session,
                        raw_url=card_url,
                        source_key=src.source_key,
                        outcome=rej_outcome,
                        event_id=None,
                        last_error=decision.reason[:500] if decision.reason else None,
                        seen_map=active_seen_map,
                    )
                    await session.commit()
                    if rej_outcome == "rejected_b2c":
                        res.rejected_b2c += 1
                    else:
                        res.rejected_geo += 1
                    continue

            is_recheck_with_hash = (
                prev_state is not None
                and prev_state.outcome == "ingested_needs_enrichment"
                and bool(prev_state.content_hash)
            )
            if is_recheck_with_hash and prev_state is not None:
                no_ocr_kwargs = _filter_supported_kwargs(
                    scraper_pkg.collect_event_dossiers,
                    {"vision_ocr": None, "ocr_budget": None},
                )
                dossiers = await scraper_pkg.collect_event_dossiers(
                    candidate, src, **no_ocr_kwargs  # type: ignore[arg-type]
                )
                new_hash = _compute_dossier_hash(dossiers)
                if new_hash == prev_state.content_hash:
                    logger.info(
                        "Контент %s (%s) не изменился (content_hash=%s), пропуск LLM/OCR.",
                        card_url,
                        src.source_key,
                        new_hash[:12],
                    )
                    await _upsert_seen_url(
                        session,
                        raw_url=card_url,
                        source_key=src.source_key,
                        outcome="ingested_needs_enrichment",
                        event_id=prev_state.event_id,
                        last_error=None,
                        seen_map=active_seen_map,
                        content_hash=new_hash,
                    )
                    await session.commit()
                    continue
                if vision_ocr is not None:
                    crawler_kwargs = _filter_supported_kwargs(
                        scraper_pkg.collect_event_dossiers,
                        {"vision_ocr": vision_ocr, "ocr_budget": ocr_budget},
                    )
                    dossiers = await scraper_pkg.collect_event_dossiers(
                        candidate, src, **crawler_kwargs  # type: ignore[arg-type]
                    )
                    new_hash = _compute_dossier_hash(dossiers)
            else:
                crawler_kwargs = _filter_supported_kwargs(
                    scraper_pkg.collect_event_dossiers,
                    {"vision_ocr": vision_ocr, "ocr_budget": ocr_budget},
                )
                dossiers = await scraper_pkg.collect_event_dossiers(
                    candidate, src, **crawler_kwargs  # type: ignore[arg-type]
                )
                new_hash = _compute_dossier_hash(dossiers)

            url_ready = 0
            url_enrichment_ids: list[int] = []
            first_event_id: int | None = None
            url_rej_past = 0
            url_rej_geo = 0
            url_ignored = 0
            last_rej_reason: str | None = None
            sub_errors: list[str] = []

            for dossier in dossiers:
                try:
                    ev = await scraper_pkg.ingest_event_from_text(
                        session,
                        dossier.dossier_text,
                        source_url=card_url,
                        extra_warnings=dossier.warnings,
                        enforce_russia_online=src.russia_online_only,
                        allow_global_online=(src.source_key != "archdaily"),
                        reject_past=True,
                        extra_source_urls=dossier.source_urls,
                    )
                    was_created_attr = getattr(ev, "_was_created_in_ingest", None)
                    if isinstance(was_created_attr, bool):
                        is_created = was_created_attr
                    else:
                        u_key = _url_lookup_key(card_url)
                        prev_seen = active_seen_map.get(u_key)
                        is_created = u_key not in known_urls and not (
                            prev_seen is not None and prev_seen.outcome.startswith("ingested_")
                        )
                    await session.commit()
                    if is_created:
                        res.created_count += 1
                    else:
                        res.updated_count += 1
                    ev_id = getattr(ev, "id", None)
                    ev_start = getattr(ev, "start_date", None)
                    saved_url = (
                        str(dossier.source_urls[0])
                        if dossier.source_urls
                        else card_url
                    )
                    res.saved_events.append(
                        {
                            "event_id": int(ev_id) if isinstance(ev_id, int) else None,
                            "title": ev.canonical_title,
                            "url": saved_url,
                            "action": "created" if is_created else "updated",
                            "data_status": ev.data_status or "ready",
                            "start_date": ev_start.isoformat() if ev_start is not None else None,
                            "city": getattr(ev, "city", None),
                        }
                    )
                    if first_event_id is None:
                        first_event_id = ev.id
                    if ev.data_status == "ready":
                        url_ready += 1
                        res.ready_count += 1
                    else:
                        url_enrichment_ids.append(ev.id)
                        res.enrichment_titles.append(ev.canonical_title)
                except scraper_pkg.EventRejectedError as rej_exc:
                    await session.rollback()
                    logger.info(
                        "Секция/кандидат %s (%s) отсеян [%s]: %s",
                        card_url,
                        src.source_key,
                        rej_exc.outcome,
                        rej_exc.reason,
                    )
                    last_rej_reason = rej_exc.reason[:500]
                    if rej_exc.outcome == "ignored":
                        url_ignored += 1
                    elif rej_exc.outcome == "rejected_past":
                        url_rej_past += 1
                        res.rejected_past += 1
                    else:
                        url_rej_geo += 1
                        res.rejected_geo += 1
                except _INGEST_ERRORS as sub_exc:
                    await session.rollback()
                    if len(dossiers) == 1:
                        raise
                    logger.exception(
                        "Ошибка обработки секции дайджеста %s (%s)",
                        card_url,
                        src.source_key,
                    )
                    sub_errors.append(str(sub_exc).strip() or type(sub_exc).__name__)

            if url_ready > 0:
                seen_outcome = "ingested_ready"
                seen_err: str | None = None
            elif url_enrichment_ids:
                seen_outcome = "ingested_needs_enrichment"
                seen_err = None
            elif sub_errors:
                raise RuntimeError(sub_errors[0])
            elif url_ignored > 0 and url_rej_past == 0 and url_rej_geo == 0:
                seen_outcome = "ignored"
                seen_err = last_rej_reason
            elif url_rej_past > 0 and url_rej_geo == 0:
                seen_outcome = "rejected_past"
                seen_err = last_rej_reason
            elif url_rej_geo > 0:
                seen_outcome = "rejected_geo"
                seen_err = last_rej_reason
            else:
                seen_outcome = "failed"
                seen_err = "Дайджест не дал ни одного сохраненного события."

            await _upsert_seen_url(
                session,
                raw_url=card_url,
                source_key=src.source_key,
                outcome=seen_outcome,
                event_id=first_event_id,
                last_error=seen_err,
                seen_map=active_seen_map,
                content_hash=new_hash,
            )
            await session.commit()
            if url_ready > 0 or url_enrichment_ids:
                known_urls.add(_url_lookup_key(card_url))
        except _INGEST_ERRORS as exc:
            await session.rollback()
            logger.exception("Не удалось импортировать карточку %s из источника %s", card_url, src.source_key)
            res.failed_urls.append(card_url)
            err_text = str(exc).strip() or type(exc).__name__
            try:
                await _upsert_seen_url(
                    session,
                    raw_url=card_url,
                    source_key=src.source_key,
                    outcome="failed",
                    event_id=None,
                    last_error=err_text[:1000],
                    seen_map=active_seen_map,
                )
                await session.commit()
            except SQLAlchemyError:
                await session.rollback()
                logger.exception("Не удалось сохранить статус failed в scraper_seen_urls для %s", card_url)

    return res


async def _ingest_source_new_urls(
    session: AsyncSession,
    src: CustomerSourceConfig,
    new_urls: Sequence[DiscoveredCandidate | str],
    known_urls: set[str],
    seen_map: dict[str, _SeenUrlState] | None = None,
) -> tuple[int, list[str], list[str]]:
    """Обходит список новых URL одного источника и возвращает (ready_count, enrichment_titles, failed_urls)."""
    res = await _ingest_source_candidates(
        session,
        src,
        new_urls,
        known_urls,
        seen_map=seen_map,
    )
    return res.ready_count, res.enrichment_titles, res.failed_urls


async def _discover_source(
    scraper: CatalogSourceScraperProtocol,
    src: CustomerSourceConfig,
) -> DiscoveryResult:
    discover_fn = getattr(scraper, "discover_catalog", None)
    if callable(discover_fn):
        res = await discover_fn(src)
        if isinstance(res, DiscoveryResult):
            return res
    urls = await scraper.fetch_catalog_urls(src)
    return DiscoveryResult(
        candidates=[DiscoveredCandidate(url=u, source_key=src.source_key) for u in urls]
    )


async def run_customer_sources_monitoring(
    session: AsyncSession,
    *,
    source_key: str | None = None,
    catalog_scraper: CatalogSourceScraperProtocol | None = None,
    max_urls_per_source: int | None = None,
    dry_run: bool = False,
    on_source_progress: Callable[[dict[str, object], dict[str, int]], Awaitable[None] | None] | None = None,
) -> ScrapingRunSummary:
    """
    Оркестратор мониторинга площадок ГК «СКАРТ»:
    1. Синхронизирует и загружает источники из таблицы scraper_sources.
    2. При source_key=<manual_only> поднимает ValueError; при source_key=None пропускает manual_only и disabled.
    3. Выполняет Discovery (HTML/XML/RSS + B2C/Geo pre-filter).
    4. Проверяет scraper_seen_urls + events.source_urls (допуская 1 recheck для needs_enrichment).
    5. При dry_run=True не вызывает LLM/эмбеддинги и не пишет в events / scraper_seen_urls.
    """
    import app.services.scraper as scraper_pkg

    source_rows = await scraper_pkg.ensure_builtin_scraper_sources(session)
    if not dry_run:
        session_new = getattr(session, "new", ())
        if isinstance(session_new, (list, tuple, set)) or hasattr(session_new, "__iter__"):
            try:
                if any(isinstance(obj, ScraperSource) for obj in session_new):
                    await session.commit()
            except TypeError:
                pass
    all_configs = [
        CustomerSourceConfig.from_orm(row)
        for row in source_rows
        if isinstance(row, ScraperSource)
    ]

    if source_key is not None:
        target_cfg = next((s for s in all_configs if s.source_key == source_key), None)
        if target_cfg is None:
            raise LookupError(f"Источник мониторинга с ключом {source_key!r} не найден в scraper_sources.")
        if target_cfg.adapter_type == "manual_only":
            raise ValueError("Источник работает только в режиме ручного Умного импорта.")
        sources = [target_cfg] if target_cfg.is_enabled else []
    else:
        sources = [
            s for s in all_configs if s.is_enabled and s.adapter_type != "manual_only"
        ]

    scraper = catalog_scraper if catalog_scraper is not None else scraper_pkg.HttpCatalogSourceScraper()
    known_urls = await _load_known_source_urls(session)
    seen_map = await _load_seen_urls_map(session)

    ocr_budget: OcrBudgetTracker | None = None
    vision_ocr: VisionOCRProviderProtocol | None = None
    if not dry_run:
        ocr_budget = scraper_pkg.OcrBudgetTracker(
            remaining_pages=scraper_pkg.settings.VISION_OCR_MAX_PAGES_PER_RUN
        )
        vision_ocr = scraper_pkg.build_vision_ocr_provider()

    discovered_count = 0
    ready_count = 0
    enrichment_titles: list[str] = []
    total_failed_urls: list[str] = []
    rejected_b2c_count = 0
    rejected_geo_count = 0
    rejected_past_count = 0
    events_created_count = 0
    events_updated_count = 0
    per_source_report: list[dict[str, object]] = []
    candidate_urls_preview: list[str] = []

    async def _emit_progress(src_report: dict[str, object]) -> None:
        if on_source_progress is None:
            return
        totals: dict[str, int] = {
            "sources_total": len(sources),
            "sources_done": len(per_source_report),
            "urls_discovered": discovered_count,
            "events_created": events_created_count,
            "events_updated": events_updated_count,
            "rejected_b2c": rejected_b2c_count,
            "rejected_geo": rejected_geo_count,
            "rejected_past": rejected_past_count,
            "errors_count": len(total_failed_urls),
        }
        maybe_awaitable = on_source_progress(src_report, totals)
        if inspect.isawaitable(maybe_awaitable):
            await maybe_awaitable

    for src in sources:
        effective_limit = max_urls_per_source if max_urls_per_source is not None else src.max_urls_per_run
        try:
            discovery = await _discover_source(scraper, src)
        except (httpx.HTTPError, ValueError, RuntimeError) as exc:
            logger.warning("Сбой загрузки каталога площадки %s (%s): %s", src.display_name, src.catalog_url, exc)
            total_failed_urls.append(src.catalog_url or src.source_key)
            err_report: dict[str, object] = {
                "source_key": src.source_key,
                "display_name": src.display_name,
                "adapter_type": src.adapter_type,
                "catalog_urls": list(src.catalog_urls),
                "discovered_total": 0,
                "selected_new_count": 0,
                "events_created": 0,
                "events_updated": 0,
                "rejected_b2c": 0,
                "rejected_geo": 0,
                "rejected_past": 0,
                "errors_count": 1,
                "candidate_urls": [],
                "saved_events": [],
                "error": str(exc),
            }
            per_source_report.append(err_report)
            await _emit_progress(err_report)
            continue

        rejected_b2c_count += discovery.rejected_b2c
        rejected_geo_count += discovery.rejected_geo

        new_candidates: list[DiscoveredCandidate] = []
        if effective_limit > 0:
            for cand in discovery.candidates:
                u_key = _url_lookup_key(cand.url)
                if _should_skip_url(u_key, seen_map, known_urls):
                    continue
                new_candidates.append(cand)
                if len(new_candidates) >= effective_limit:
                    break

        new_urls = [c.url for c in new_candidates]
        discovered_count += len(new_urls)
        candidate_urls_preview.extend(new_urls)

        src_report: dict[str, object] = {
            "source_key": src.source_key,
            "display_name": src.display_name,
            "adapter_type": src.adapter_type,
            "catalog_urls": list(src.catalog_urls),
            "discovered_total": len(discovery.candidates),
            "selected_new_count": len(new_urls),
            "events_created": 0,
            "events_updated": 0,
            "rejected_b2c": discovery.rejected_b2c,
            "rejected_geo": discovery.rejected_geo,
            "rejected_past": 0,
            "errors_count": 0,
            "candidate_urls": list(new_urls),
            "saved_events": [],
            "error": None,
        }

        if not dry_run and new_candidates:
            ingest_res = await _ingest_source_candidates(
                session,
                src,
                new_candidates,
                known_urls,
                seen_map=seen_map,
                vision_ocr=vision_ocr,
                ocr_budget=ocr_budget,
            )
            ready_count += ingest_res.ready_count
            enrichment_titles.extend(ingest_res.enrichment_titles)
            total_failed_urls.extend(ingest_res.failed_urls)
            rejected_b2c_count += ingest_res.rejected_b2c
            rejected_geo_count += ingest_res.rejected_geo
            rejected_past_count += ingest_res.rejected_past
            events_created_count += ingest_res.created_count
            events_updated_count += ingest_res.updated_count
            src_report["events_created"] = ingest_res.created_count
            src_report["events_updated"] = ingest_res.updated_count
            src_report["rejected_b2c"] = discovery.rejected_b2c + ingest_res.rejected_b2c
            src_report["rejected_geo"] = discovery.rejected_geo + ingest_res.rejected_geo
            src_report["rejected_past"] = ingest_res.rejected_past
            src_report["errors_count"] = len(ingest_res.failed_urls)
            src_report["saved_events"] = list(ingest_res.saved_events)

        per_source_report.append(src_report)
        await _emit_progress(src_report)

    return ScrapingRunSummary(
        checked_sources=len(sources),
        discovered_urls=discovered_count,
        ingested_ready_count=ready_count,
        needs_enrichment_count=len(enrichment_titles),
        needs_enrichment_titles=enrichment_titles,
        failed_count=len(total_failed_urls),
        failed_urls=total_failed_urls,
        dry_run=dry_run,
        rejected_b2c_count=rejected_b2c_count,
        rejected_geo_count=rejected_geo_count,
        per_source_report=per_source_report,
        candidate_urls_preview=candidate_urls_preview,
        rejected_past_count=rejected_past_count,
        vision_ocr_pages_used=ocr_budget.used_pages if ocr_budget is not None else 0,
        events_created_count=events_created_count,
        events_updated_count=events_updated_count,
    )
