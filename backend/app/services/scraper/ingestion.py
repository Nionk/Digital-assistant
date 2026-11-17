import asyncio
import datetime
import json
import logging
import re
from collections.abc import Sequence
from typing import Literal, TypeAlias
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx
from instructor.core import InstructorError
from openai import APIError
from rapidfuzz import fuzz
from sqlalchemy import and_, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import CITY_ALIASES, normalize_city
from app.models.models import Event, EventChunk, EventTariff, LLMCache, SelectionItem
from app.schemas.event_ingestion import EventIngestionSchema
from app.services.scraper.pdf_reader import VisionOCRProviderProtocol

logger = logging.getLogger(__name__)

DataQualityStatus: TypeAlias = Literal["ready", "needs_enrichment"]
MAX_DOSSIER_CHARS: int = 60_000

_RUSSIA_COUNTRY_ALIASES: frozenset[str] = frozenset(
    {"россия", "рф", "российская федерация", "russia", "russian federation"}
)
_NON_RUSSIA_CIS_CITIES: frozenset[str] = frozenset(
    {"Минск", "Алматы", "Астана", "Ереван", "Ташкент", "Бишкек", "Баку"}
)
_RUSSIA_CITY_SET: frozenset[str] = frozenset(CITY_ALIASES.keys()) - _NON_RUSSIA_CIS_CITIES


class EventRejectedError(ValueError):
    """Контролируемое отклонение события на валидации даты, географии или архивного статуса ДО вызова эмбеддингов."""

    def __init__(
        self,
        outcome: Literal["rejected_past", "rejected_geo", "ignored"],
        reason: str,
    ) -> None:
        self.outcome = outcome
        self.reason = reason
        super().__init__(reason)


def _get_app_today() -> datetime.date:
    import app.services.scraper as scraper_pkg

    tz_name = scraper_pkg.settings.APP_TIMEZONE or "Europe/Moscow"
    tz: datetime.tzinfo
    try:
        tz = ZoneInfo(tz_name)
    except ZoneInfoNotFoundError:
        tz = datetime.UTC
    return datetime.datetime.now(tz).date()


def is_russia_or_online_event(
    schema: EventIngestionSchema,
    *,
    allow_online: bool = True,
) -> bool:
    """
    Проверяет, относится ли извлеченное событие к РФ или допустимому онлайну.
    Переиспользует CITY_ALIASES и normalize_city из app/core/constants.py.
    """
    norm_country = re.sub(r"\s+", " ", (schema.country or "").strip().lower())
    is_russia_country = norm_country in _RUSSIA_COUNTRY_ALIASES

    if schema.is_online:
        if is_russia_country:
            return True
        if not norm_country and schema.city:
            norm_city = normalize_city(schema.city)
            if norm_city and norm_city in _RUSSIA_CITY_SET:
                return True
        return allow_online

    if norm_country and not is_russia_country:
        return False
    if is_russia_country:
        return True
    if schema.city:
        norm_city = normalize_city(schema.city)
        if norm_city and norm_city in _RUSSIA_CITY_SET:
            return True
    return False


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
    import app.services.scraper as scraper_pkg

    await session.execute(delete(EventChunk).where(EventChunk.event_id == event_obj.id))
    cleaned_md = regulation_md.strip()
    if len(cleaned_md) <= 35000:
        return

    chunks = scraper_pkg.split_regulation_into_chunks(cleaned_md)
    if not chunks:
        return

    location_desc = "Онлайн" if event_obj.is_online else (event_obj.city or "Локация не указана")
    date_desc = f"{event_obj.start_date} — {event_obj.end_date}"
    header = f"[Мероприятие: {event_obj.canonical_title} | Локация: {location_desc} | Даты: {date_desc}]\n"
    contextualized_chunks = [f"{header}{ch}" for ch in chunks]

    vectors = await scraper_pkg.get_embeddings_batch(contextualized_chunks)
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
            float(fuzz.token_set_ratio(norm_new, norm_existing)),
        )
        if score >= similarity_threshold:
            return existing
    return None


async def _extract_structured_event_via_llm(raw_dossier_text: str) -> EventIngestionSchema:
    """Вызывает LLM-3 через Instructor для извлечения EventIngestionSchema из сырого текста досье."""
    import app.services.scraper as scraper_pkg

    if not scraper_pkg.settings.LLM_API_KEY:
        raise RuntimeError("LLM_API_KEY не задан для извлечения карточки мероприятия.")

    today_str = _get_app_today().isoformat()
    system_prompt = (
        f"Сегодняшняя дата: {today_str}.\n"
        "Ты — аналитик базы знаний B2B-мероприятий. Извлеки из текста структурированную карточку "
        "события по схеме EventIngestionSchema: официальное название, формат, город (или null для онлайн), "
        "страну проведения country (например, 'Россия' для российских городов или фактическую зарубежную страну; "
        "для глобальных онлайн-вебинаров без привязки к стране — null), "
        "даты проведения, содержательное summary (250-850 символов), максимально подробный full_regulation_markdown "
        "(сохраняй конкретные факты без сокращений: программу, аудиторию и статистику участников, требования к посетителям/участникам, "
        "спикеров и VIP-гостей, партнеров/СМИ, условия участия и стендов, контакты и материалы из PDF), "
        "все тарифы и 3 ответа faq_cache строго по вопросам: "
        "'Что входит в рекомендованный тариф?', "
        "'Какие условия раннего бронирования и дедлайны?', "
        "'Формат участия и требования к спикеру'."
    )
    try:
        async with scraper_pkg.LLM_SEMAPHORE:
            schema: EventIngestionSchema = await asyncio.wait_for(
                scraper_pkg.structured_llm_client.chat.completions.create(
                    model=scraper_pkg.settings.LLM_MODEL,
                    response_model=EventIngestionSchema,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": raw_dossier_text},
                    ],
                    max_retries=2,
                ),
                timeout=90.0,
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
    import app.services.scraper as scraper_pkg

    seen_cache_keys: set[str] = set()
    reg_text = (event_obj.full_regulation_markdown or "").lower()
    for faq in schema.faq_cache:
        # Не кэшируем на уровне события (tariff_id=0) ответы, зависящие от рекомендованного тарифа
        q_low = faq.question.lower()
        if any(
            kw in q_low
            for kw in ("что входит", "входит в тариф", "рекомендованный тариф", "раннего бронирования", "early bird")
        ):
            continue
        ans_lower = (faq.answer or "").strip().lower()
        if not ans_lower or any(stub in ans_lower for stub in ("уточняется", "нет информаци", "не указан")):
            continue
        quote = (faq.source_quote or "").strip()
        if not quote or (quote.lower() not in reg_text and not scraper_pkg._is_quote_grounded(quote, reg_text)):
            continue

        cache_key = scraper_pkg.build_rag_cache_key(event_obj.id, 0, faq.question)
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


def _strip_schema_org_json_prefix(text: str) -> str:
    """Удаляет технический блок --- SCHEMA.ORG LD+JSON --- из текста карточки перед сохранением в регламент."""
    marker = "--- SCHEMA.ORG LD+JSON ---"
    stripped = text.lstrip()
    if not stripped.startswith(marker):
        return text.strip()
    rest = stripped[len(marker) :].lstrip()
    decoder = json.JSONDecoder()
    while rest and rest[0] in ("{", "["):
        try:
            _, idx = decoder.raw_decode(rest)
            rest = rest[idx:].lstrip()
        except json.JSONDecodeError:
            break
    return rest.strip()


_DOSSIER_SECTION_HEADER_RE = re.compile(r"(?m)^(===\s+[^\n]+?\s+===)\s*$")


def _extract_clean_dossier_materials(
    raw_dossier_text: str,
    base_regulation_md: str,
    *,
    max_chars: int = 22_000,
) -> str:
    """
    Извлекает содержательные материалы из досье (PDF, OCR, страницы организатора, текст),
    очищает от сырого LD+JSON и уже включенных параграфов, чтобы RAG видел все детали первоисточников.
    """
    raw = raw_dossier_text.strip()
    if not raw:
        return ""

    matches = list(_DOSSIER_SECTION_HEADER_RE.finditer(raw))
    priority_blocks: list[tuple[str, str]] = []
    secondary_blocks: list[tuple[str, str]] = []

    if not matches:
        cleaned = _strip_schema_org_json_prefix(raw)
        if len(cleaned) >= 120:
            secondary_blocks.append(("Текст первоисточника", cleaned))
    else:
        for idx, match in enumerate(matches):
            header = match.group(1).strip()
            body_start = match.end()
            body_end = matches[idx + 1].start() if idx + 1 < len(matches) else len(raw)
            body = _strip_schema_org_json_prefix(raw[body_start:body_end])
            if len(body) < 80:
                continue
            h_low = header.lower()
            if any(
                tag in h_low
                for tag in (
                    "pdf",
                    "ocr",
                    "официальный сайт",
                    "подстраница организатора",
                    "данные со страницы",
                    "текстовое описание",
                )
            ):
                priority_blocks.append((header, body))
            else:
                secondary_blocks.append((header, body))

    selected_blocks = priority_blocks if priority_blocks else secondary_blocks
    if not selected_blocks:
        return ""

    def _norm(s: str) -> str:
        return re.sub(r"\s+", " ", s).strip().lower()

    base_paragraphs = {
        _norm(p)
        for p in base_regulation_md.split("\n\n")
        if len(p.strip()) >= 30
    }
    base_norm_full = _norm(base_regulation_md)

    rendered_sections: list[str] = []
    for header, body in selected_blocks:
        kept_paragraphs: list[str] = []
        for para in re.split(r"\n{2,}", body):
            p_clean = para.strip()
            if not p_clean:
                continue
            p_norm = _norm(p_clean)
            if len(p_norm) >= 40 and (p_norm in base_paragraphs or p_norm in base_norm_full):
                continue
            kept_paragraphs.append(p_clean)
        if kept_paragraphs:
            rendered_sections.append(f"### {header.strip('= ')}\n" + "\n\n".join(kept_paragraphs))

    combined = "\n\n".join(rendered_sections).strip()
    if len(combined) < 120:
        return ""
    if len(combined) > max_chars:
        return f"{combined[:max_chars].rstrip()}\n...[материалы сокращены]"
    return combined


def _build_detailed_regulation_markdown(
    base_regulation_md: str,
    raw_dossier_text: str,
) -> str:
    """Дополняет выжимку LLM очищенными материалами первоисточников (PDF/сайт) для полноты RAG."""
    base_clean = (base_regulation_md or "").strip()
    appendix = _extract_clean_dossier_materials(raw_dossier_text, base_clean)
    if not appendix:
        return base_clean
    if not base_clean:
        return appendix
    return f"{base_clean}\n\n---\n\n## Подробные материалы и первоисточники\n\n{appendix}"


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
    extra_source_urls: Sequence[str] = (),
) -> None:
    """Обогащает карточку новыми данными без ухудшения исходных названия, дат и города."""
    if len(schema.summary) > len(target.summary or ""):
        target.summary = schema.summary
        target.summary_embedding = embedding_vec
    if schema.venue and not target.venue:
        target.venue = schema.venue
    target.themes = list(dict.fromkeys([*(target.themes or []), *schema.themes]))

    if schema.full_regulation_markdown and schema.full_regulation_markdown.strip():
        target.full_regulation_markdown = _merge_regulation_markdown(
            target.full_regulation_markdown,
            schema.full_regulation_markdown,
            source_url,
        )

    incoming_urls = [u.strip() for u in (source_url, *extra_source_urls) if u and u.strip()]
    if incoming_urls:
        target.source_urls = list(dict.fromkeys([*(target.source_urls or []), *incoming_urls]))

    target.last_scraped_at = datetime.datetime.now(datetime.UTC)


async def ingest_event_from_text(
    session: AsyncSession,
    raw_dossier_text: str,
    source_url: str | None = None,
    extra_warnings: Sequence[str] = (),
    *,
    enforce_russia_online: bool = False,
    allow_global_online: bool = True,
    reject_past: bool = False,
    skip_archived: bool | None = None,
    extra_source_urls: Sequence[str] = (),
) -> Event:
    """
    Полный цикл извлечения и обогащения карточки мероприятия.
    Внимание: метод выполняет flush(), но не делает commit(). Управлением транзакцией владеет вызывающий код.
    """
    import app.services.scraper as scraper_pkg

    if not raw_dossier_text or not raw_dossier_text.strip():
        raise ValueError("Передан пустой текст досье для извлечения карточки мероприятия.")

    dossier_to_parse = raw_dossier_text.strip()
    collected_warnings = list(extra_warnings)
    if len(dossier_to_parse) > MAX_DOSSIER_CHARS:
        dossier_to_parse = dossier_to_parse[:MAX_DOSSIER_CHARS]
        collected_warnings.append("dossier_truncated_before_llm")

    schema = await _extract_structured_event_via_llm(dossier_to_parse)
    detailed_regulation_md = _build_detailed_regulation_markdown(
        schema.full_regulation_markdown,
        dossier_to_parse,
    )
    if detailed_regulation_md != schema.full_regulation_markdown:
        schema = schema.model_copy(
            update={"full_regulation_markdown": detailed_regulation_md}
        )

    if reject_past:
        today = _get_app_today()
        if schema.end_date < today:
            raise EventRejectedError(
                "rejected_past",
                f"Мероприятие уже завершилось ({schema.end_date.isoformat()} < {today.isoformat()}).",
            )

    if enforce_russia_online and not is_russia_or_online_event(
        schema, allow_online=allow_global_online
    ):
        raise EventRejectedError(
            "rejected_geo",
            f"Локация вне РФ/допустимого онлайна (country={schema.country!r}, city={schema.city!r}, is_online={schema.is_online}).",
        )

    emb_text = f"{schema.canonical_title}. {schema.summary}. Темы: {', '.join(schema.themes)}"
    embedding_vec = await scraper_pkg.get_embedding(emb_text)

    existing = await scraper_pkg.find_duplicate_event(session, schema)
    should_skip_archived = reject_past if skip_archived is None else skip_archived
    if existing is not None and existing.data_status == "archived" and should_skip_archived:
        raise EventRejectedError(
            "ignored",
            f"Мероприятие '{existing.canonical_title}' (ID={existing.id}) находится в архиве.",
        )

    was_created = existing is None
    was_ready = existing is not None and existing.data_status == "ready"
    if existing is not None:
        await scraper_pkg.invalidate_rag_cache(session, existing.id)
        event_obj = existing
        _merge_into_existing(
            event_obj,
            schema,
            embedding_vec,
            source_url,
            extra_source_urls=extra_source_urls,
        )
    else:
        initial_urls = list(
            dict.fromkeys([u.strip() for u in (source_url, *extra_source_urls) if u and u.strip()])
        )
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
            source_urls=initial_urls,
            summary_embedding=embedding_vec,
            last_scraped_at=datetime.datetime.now(datetime.UTC),
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
    if was_ready and data_status == "needs_enrichment":
        event_obj.data_status = "ready"
        event_obj.is_active = True
    else:
        event_obj.data_status = data_status
        event_obj.missing_data_warnings = warnings
        event_obj.is_active = data_status == "ready"

    await session.flush()
    event_obj._was_created_in_ingest = was_created  # type: ignore[attr-defined]
    return event_obj


async def _extract_pdf_dossier_parts(
    pdf_bytes: bytes,
    vision_ocr: VisionOCRProviderProtocol | None,
    existing_dossier_text: str = "",
    max_ocr_pages: int | None = None,
) -> tuple[list[str], list[str]]:
    """Извлекает текстовый слой и результаты Vision OCR из PDF-документа для общего досье."""
    import app.services.scraper as scraper_pkg

    parts: list[str] = []
    warnings: list[str] = []
    effective_max_pages = (
        max_ocr_pages
        if max_ocr_pages is not None
        else scraper_pkg.settings.VISION_OCR_MAX_PAGES_MANUAL
    )
    pdf_text, ocr_images = await scraper_pkg.extract_pdf_text_async(
        pdf_bytes,
        max_ocr_pages=effective_max_pages,
        include_all_if_compact=True,
    )
    if pdf_text:
        parts.append(f"=== ТЕКСТ ИЗ PDF-РЕГЛАМЕНТА ===\n{pdf_text}")
    if ocr_images and scraper_pkg.should_run_vision_ocr(
        existing_dossier_text, pdf_text, ocr_images
    ):
        if vision_ocr is None:
            warnings.append("vision_ocr_not_configured")
        else:
            try:
                ocr_text = await vision_ocr.extract_text_from_images(ocr_images)
            except (TimeoutError, APIError, httpx.HTTPError, RuntimeError, ValueError) as exc:
                logger.warning("Сбой Vision OCR при ручном импорте PDF: %s", exc)
                ocr_text = ""
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
    import app.services.scraper as scraper_pkg

    dossier_parts: list[str] = []
    extra_warnings: list[str] = []

    if source_url and source_url.strip():
        clean_url = source_url.strip()
        url_text = await scraper_pkg.fetch_url_dossier_text(clean_url)
        if url_text:
            dossier_parts.append(f"=== ДАННЫЕ СО СТРАНИЦЫ ({clean_url}) ===\n{url_text}")

    if raw_text and raw_text.strip():
        dossier_parts.append(f"=== ТЕКСТОВОЕ ОПИСАНИЕ / ЗАМЕТКА ===\n{raw_text.strip()}")

    if pdf_bytes:
        effective_vision_ocr = (
            vision_ocr
            if vision_ocr is not None
            else scraper_pkg.build_vision_ocr_provider()
        )
        pdf_parts, pdf_warnings = await _extract_pdf_dossier_parts(
            pdf_bytes,
            effective_vision_ocr,
            existing_dossier_text="\n\n".join(dossier_parts),
            max_ocr_pages=scraper_pkg.settings.VISION_OCR_MAX_PAGES_MANUAL,
        )
        dossier_parts.extend(pdf_parts)
        extra_warnings.extend(pdf_warnings)

    if not dossier_parts:
        if pdf_bytes:
            raise ValueError(
                "Не удалось извлечь текст из PDF-файла (возможно, это скан без настроенного Vision OCR)."
            )
        raise ValueError("Необходимо передать хотя бы один источник данных: source_url, raw_text или pdf_bytes.")

    event_obj = await scraper_pkg.ingest_event_from_text(
        session=session,
        raw_dossier_text="\n\n".join(dossier_parts),
        source_url=source_url.strip() if source_url else None,
        extra_warnings=extra_warnings,
    )
    await session.commit()
    return event_obj
