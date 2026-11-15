import datetime
import logging
import re
from collections import defaultdict
from collections.abc import Sequence

import httpx
from openai import APIError
from sqlalchemy import and_, case, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.models.models import Event, EventTariff
from app.schemas.manager import ClientQueryExtracted, TariffOptionOut
from app.services.matcher.bundles import build_tariff_option
from app.services.matcher.types import ScoredEventCandidate

logger = logging.getLogger(__name__)


def _clean_fts_term(kw: str) -> str | None:
    """Очищает поисковый термин от спецсимволов и оборачивает фразы в кавычки."""
    clean = re.sub(r"\s+", " ", re.sub(r"[^\w\s\-]", " ", kw)).strip()
    if len(clean) < 2:
        return None
    return f'"{clean}"' if " " in clean else clean


def build_fts_or_query(profile: ClientQueryExtracted) -> str:
    """
    Формирует безопасную строку запроса для PostgreSQL websearch_to_tsquery('russian', ...).
    Исключает спецсимволы и гарантирует непустой запрос за счет фолбэка на semantic_search_query (rules.md п. 4.3).
    """
    cleaned_terms = [t for kw in (profile.themes_keywords or []) if (t := _clean_fts_term(kw)) is not None]
    if not cleaned_terms and profile.semantic_search_query:
        words = [re.sub(r"[^\w\-]", "", w).strip() for w in profile.semantic_search_query.split()]
        cleaned_terms = [w for w in words if len(w) >= 3]

    return " OR ".join(cleaned_terms) if cleaned_terms else "мероприятие OR конференция OR форум"


def _build_sql_filter_conditions(
    profile: ClientQueryExtracted,
    today: datetime.date,
    *,
    enforce_dates: bool = True,
    budget_ceiling: float | None = None,
    has_query_vec: bool = True,
) -> list[ColumnElement[bool]]:
    """
    Формирует список предикатов SQL WHERE для гибридного RRF-поиска (artifact.md раздел 10.3).
    Строго проверяет Quality Gate (data_status == 'ready'), локацию, даты и актуальную цену Early Bird через CASE.
    """
    conditions: list[ColumnElement[bool]] = [
        Event.is_active.is_(True),
        Event.data_status == "ready",
        Event.end_date >= today,
    ]
    if has_query_vec:
        conditions.append(Event.summary_embedding.is_not(None))

    if enforce_dates:
        if profile.date_from is not None:
            conditions.append(Event.start_date >= profile.date_from)
        if profile.date_to is not None:
            conditions.append(Event.end_date <= profile.date_to)

    if profile.cities:
        if profile.include_online:
            conditions.append(or_(Event.city.in_(profile.cities), Event.is_online.is_(True)))
        else:
            conditions.append(and_(Event.city.in_(profile.cities), Event.is_online.is_(False)))
    elif not profile.include_online:
        conditions.append(Event.is_online.is_(False))

    max_price = budget_ceiling if budget_ceiling is not None else profile.total_budget_max
    effective_price_expr = case(
        (
            and_(
                EventTariff.early_bird_deadline.is_not(None),
                EventTariff.early_bird_deadline >= today,
                EventTariff.early_bird_price.is_not(None),
            ),
            EventTariff.early_bird_price,
        ),
        else_=EventTariff.base_price,
    )
    tariff_exists_stmt = exists(
        select(1).where(
            and_(
                EventTariff.event_id == Event.id,
                or_(
                    EventTariff.base_price.is_(None),
                    effective_price_expr <= max_price,
                ),
            )
        )
    )
    conditions.append(tariff_exists_stmt)
    return conditions


async def fetch_hybrid_rrf_candidates(
    session: AsyncSession,
    profile: ClientQueryExtracted,
    query_vec: list[float] | None,
    fts_query_str: str,
    today: datetime.date,
    *,
    limit: int = 15,
    enforce_dates: bool = True,
    budget_ceiling: float | None = None,
) -> list[tuple[Event, float]]:
    """
    Выполняет гибридный поиск (векторная близость pgvector + полнотекстовый поиск FTS)
    с объединением рангов по формуле Reciprocal Rank Fusion (k=60).
    При отсутствии векторного эмбеддинга (query_vec is None) выполняет надежный откат на FTS-ранжирование.
    """
    conditions = _build_sql_filter_conditions(
        profile,
        today,
        enforce_dates=enforce_dates,
        budget_ceiling=budget_ceiling,
        has_query_vec=query_vec is not None,
    )

    if query_vec is None:
        ts_query_expr = func.websearch_to_tsquery("russian", fts_query_str)
        fts_rank_expr = func.ts_rank_cd(Event.search_vector, ts_query_expr)
        fts_stmt = (
            select(Event, fts_rank_expr.label("score"))
            .where(*conditions)
            .order_by(fts_rank_expr.desc(), Event.start_date.asc())
            .limit(limit)
        )
        result = await session.execute(fts_stmt)
        return [(row[0], float(row[1] or 0.0)) for row in result.all()]

    vec_dist_expr = Event.summary_embedding.cosine_distance(query_vec)
    ts_query_expr = func.websearch_to_tsquery("russian", fts_query_str)
    fts_rank_expr = func.ts_rank_cd(Event.search_vector, ts_query_expr)

    candidates_cte = (
        select(
            Event.id.label("event_id"),
            vec_dist_expr.label("vec_distance"),
            fts_rank_expr.label("fts_rank"),
        )
        .where(*conditions)
        .cte("candidates")
    )

    r_vec_col = func.row_number().over(order_by=candidates_cte.c.vec_distance.asc()).label("r_vec")
    r_fts_col = func.row_number().over(
        order_by=[candidates_cte.c.fts_rank.desc(), candidates_cte.c.vec_distance.asc()]
    ).label("r_fts")

    ranked_cte = select(
        candidates_cte.c.event_id,
        candidates_cte.c.fts_rank,
        r_vec_col,
        r_fts_col,
    ).cte("ranked")
    fts_rrf_term = case(
        (ranked_cte.c.fts_rank > 0.0, 1.0 / (60.0 + ranked_cte.c.r_fts)),
        else_=0.0,
    )
    rrf_score_expr = ((1.0 / (60.0 + ranked_cte.c.r_vec)) + fts_rrf_term).label("rrf_score")

    final_stmt = (
        select(Event, rrf_score_expr)
        .join(ranked_cte, Event.id == ranked_cte.c.event_id)
        .order_by(rrf_score_expr.desc())
        .limit(limit)
    )
    result = await session.execute(final_stmt)
    return [(row[0], float(row[1] or 0.0)) for row in result.all()]


def _theme_matches_keywords(theme: str, keywords: Sequence[str]) -> bool:
    """Проверяет двустороннее вхождение тега мероприятия и ключевых слов профиля."""
    t_low = theme.lower()
    return any(kw.lower() in t_low or t_low in kw.lower() for kw in keywords)


def _calculate_domain_bonus(ev: Event, profile: ClientQueryExtracted) -> float:
    """Вычисляет дополнительный RRF-бонус за точное совпадение формата, города и тегов."""
    bonus = 0.0
    if profile.preferred_formats and ev.event_format in profile.preferred_formats:
        bonus += 0.004
    if profile.cities and ev.city in profile.cities:
        bonus += 0.003
    if profile.themes_keywords and ev.themes:
        matched_kw = sum(1 for t in ev.themes if _theme_matches_keywords(t, profile.themes_keywords))
        bonus += min(0.006, matched_kw * 0.002)
    return bonus


async def _load_tariffs_by_event(
    session: AsyncSession,
    event_ids: list[int],
    today: datetime.date,
) -> dict[int, list[TariffOptionOut]]:
    """Загружает все тарифы выбранных мероприятий одним плоским SQL-запросом."""
    tariffs_stmt = (
        select(EventTariff)
        .where(EventTariff.event_id.in_(event_ids))
        .order_by(EventTariff.id.asc())
    )
    tariffs_res = await session.execute(tariffs_stmt)
    tariffs_by_event: dict[int, list[TariffOptionOut]] = defaultdict(list)
    for t_orm in tariffs_res.scalars().all():
        tariffs_by_event[t_orm.event_id].append(build_tariff_option(t_orm, today))
    return tariffs_by_event


async def _fetch_filtered_events_map(
    session: AsyncSession,
    profile: ClientQueryExtracted,
    query_vec: list[float] | None,
    fts_query_str: str,
    today: datetime.date,
) -> dict[int, tuple[Event, float]]:
    """
    Выполняет каскадный гибридный RRF-поиск в PostgreSQL:
    1) Топ-15 строго в пределах бюджета и дат;
    2) При нехватке кандидатов (< K) — добор в пределах +10% допуска бюджета;
    3) При нехватке кандидатов (< K) — добор с ослаблением дат при сохранении географии.
    """
    import app.services.matcher as matcher_pkg

    strict_rows = await matcher_pkg.fetch_hybrid_rrf_candidates(
        session,
        profile,
        query_vec,
        fts_query_str,
        today,
        limit=15,
        enforce_dates=True,
        budget_ceiling=profile.total_budget_max,
    )
    events_map: dict[int, tuple[Event, float]] = {
        ev.id: (ev, score + _calculate_domain_bonus(ev, profile)) for ev, score in strict_rows
    }
    if len(events_map) >= profile.target_events_count:
        return events_map

    tolerance_ceiling = profile.total_budget_max * 1.10
    tolerance_rows = await matcher_pkg.fetch_hybrid_rrf_candidates(
        session,
        profile,
        query_vec,
        fts_query_str,
        today,
        limit=15,
        enforce_dates=True,
        budget_ceiling=tolerance_ceiling,
    )
    for ev, score in tolerance_rows:
        if ev.id not in events_map and len(events_map) < 15:
            events_map[ev.id] = (ev, score + _calculate_domain_bonus(ev, profile))
    if len(events_map) >= profile.target_events_count:
        return events_map

    relaxed_rows = await matcher_pkg.fetch_hybrid_rrf_candidates(
        session,
        profile,
        query_vec,
        fts_query_str,
        today,
        limit=15,
        enforce_dates=False,
        budget_ceiling=tolerance_ceiling,
    )
    for ev, score in relaxed_rows:
        if ev.id not in events_map and len(events_map) < 15:
            events_map[ev.id] = (ev, (score + _calculate_domain_bonus(ev, profile)) * 0.85)
    return events_map


async def get_scored_candidates(
    session: AsyncSession,
    profile: ClientQueryExtracted,
    today: datetime.date,
) -> list[ScoredEventCandidate]:
    """
    Собирает ранжированных кандидатов с тарифами через гибридный поиск RRF.
    Строго соблюдает географический фильтр и Quality Gate на уровне SQL.
    При сбое сервиса эмбеддингов выполняет плавный переход (graceful fallback) на FTS-ранжирование.
    """
    import app.services.matcher as matcher_pkg

    query_vec: list[float] | None = None
    try:
        query_vec = await matcher_pkg.get_embedding(profile.semantic_search_query)
    except (RuntimeError, APIError, httpx.HTTPError, TimeoutError, ValueError):
        logger.warning(
            "Не удалось получить эмбеддинг для запроса %r, переключаемся на FTS-only поиск",
            profile.semantic_search_query,
            exc_info=True,
        )
        query_vec = None

    events_map = await _fetch_filtered_events_map(
        session, profile, query_vec, matcher_pkg.build_fts_or_query(profile), today
    )
    if not events_map:
        return []

    tariffs_by_event = await _load_tariffs_by_event(session, list(events_map.keys()), today)
    candidates: list[ScoredEventCandidate] = []
    for ev_id, (ev, total_rrf) in events_map.items():
        all_t = tariffs_by_event.get(ev_id, [])
        if not all_t:
            continue
        candidates.append(
            ScoredEventCandidate(
                event=ev,
                rrf_score=total_rrf,
                all_tariffs=all_t,
                priced_tariffs=[t for t in all_t if t.actual_price is not None],
                on_request_tariffs=[t for t in all_t if t.actual_price is None],
            )
        )

    candidates.sort(key=lambda c: c.rrf_score, reverse=True)
    return candidates
