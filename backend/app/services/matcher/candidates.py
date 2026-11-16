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

# Параметры весов тематической и доменной релевантности (поверх базового RRF k=60).
# Базовый vector-only RRF лежит в [0.013, 0.0164], vector+FTS — в [0.026, 0.0328].
# Тематический вклад масштабирован так, чтобы реальное совпадение тегов/текста
# гарантированно перевешивало шум косинусного расстояния и бонусы формата/города.
THEME_TAG_MATCH_WEIGHT = 0.012
THEME_TAG_COVERAGE_WEIGHT = 0.018
TEXT_MATCH_WEIGHT = 0.006
TEXT_COVERAGE_WEIGHT = 0.008
FORMAT_BONUS_WEIGHT = 0.004
CITY_BONUS_WEIGHT = 0.003

# Минимальный порог RRF, выше которого при наличии query_vec гарантированно присутствует вклад FTS (1/(60+1) = 0.016393).
_MAX_VECTOR_ONLY_RRF = 1.0 / 60.0

# Узкий словарь прямых доменных эквивалентов основ (Zero-Local-ML),
# компенсирующий расхождение русских словообразовательных основ (например, "стройка" <-> "строительство").
_DIRECT_LEXICAL_EQUIVALENTS: dict[str, tuple[str, ...]] = {
    "стройк": ("строител", "застрой"),
    "строит": ("стройк", "застрой"),
    "застро": ("стройк", "строител"),
    "цифров": ("digital",),
    "digital": ("цифров",),
    "bim": ("тим", "информационн моделирован"),
    "тим": ("bim", "информационн моделирован"),
    "proptech": ("проптех",),
    "проптех": ("proptech",),
    "ижс": ("малоэтаж", "загородн"),
    "крт": ("комплексн развит территор",),
}


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


def _tokenize_lower(text: str) -> list[str]:
    """Разбивает строку на нормализованные буквенно-цифровые токены в нижнем регистре."""
    return re.findall(r"[a-zа-яё0-9\-]+", text.lower())


def _single_token_matches_text(tok: str, text_low: str) -> bool:
    """
    Проверяет вхождение одного слова/токена в текст с учетом:
    - границ слов для коротких аббревиатур (BIM, КРТ, AI);
    - префиксной основы (6 символов) для русских и латинских слов длиной >= 6;
    - прямых доменных лексических эквивалентов ("стройка" <-> "строительство").
    """
    if not tok or not text_low:
        return False

    if len(tok) < 4:
        if re.search(rf"(?<!\w){re.escape(tok)}(?!\w)", text_low):
            return True
        for eq in _DIRECT_LEXICAL_EQUIVALENTS.get(tok, ()):
            if re.search(rf"(?<!\w){re.escape(eq)}", text_low):
                return True
        return False

    if re.search(rf"(?<!\w){re.escape(tok)}", text_low):
        return True

    stem = tok[:6] if len(tok) >= 6 else tok
    if len(stem) >= 6 and re.search(rf"(?<!\w){re.escape(stem)}", text_low):
        return True

    for eq in _DIRECT_LEXICAL_EQUIVALENTS.get(stem, ()) or _DIRECT_LEXICAL_EQUIVALENTS.get(tok, ()):
        if re.search(rf"(?<!\w){re.escape(eq)}", text_low):
            return True
    return False


def _keyword_matches_text(kw: str, text: str) -> bool:
    """Проверяет совпадение ключевого слова или фразы с текстом (с поддержкой основ и аббревиатур)."""
    kw_low = kw.strip().lower()
    text_low = text.lower()
    if not kw_low or not text_low:
        return False

    if len(kw_low) >= 4 and kw_low in text_low:
        return True

    tokens = [t for t in _tokenize_lower(kw_low) if len(t) >= 2]
    if not tokens:
        return False
    if len(tokens) == 1:
        return _single_token_matches_text(tokens[0], text_low)

    significant = [t for t in tokens if len(t) >= 3] or tokens
    return all(_single_token_matches_text(t, text_low) for t in significant)


def _theme_matches_keywords(theme: str, keywords: Sequence[str]) -> bool:
    """Проверяет двустороннее вхождение тега мероприятия и ключевых слов профиля."""
    t_low = theme.strip().lower()
    if not t_low:
        return False
    for kw in keywords:
        kw_low = kw.strip().lower()
        if not kw_low:
            continue
        if _keyword_matches_text(kw_low, t_low) or (len(t_low) >= 4 and t_low in kw_low):
            return True
    return False


def _count_thematic_hits(ev: Event, keywords: Sequence[str]) -> tuple[int, int]:
    """
    Возвращает (matched_in_themes, matched_in_text) — количество уникальных ключевых слов
    профиля, совпавших с тегами `ev.themes` и с текстовым описанием (`canonical_title` + `summary`).
    """
    if not keywords:
        return 0, 0
    themes_list = [t for t in (ev.themes or []) if t]
    theme_hits = sum(1 for kw in keywords if any(_theme_matches_keywords(t, [kw]) for t in themes_list))
    text_blob = f"{ev.canonical_title or ''} {ev.summary or ''}"
    text_hits = sum(1 for kw in keywords if _keyword_matches_text(kw, text_blob))
    return theme_hits, text_hits


def _has_fts_match(raw_rrf: float, has_query_vec: bool) -> bool:
    """Определяет по SQL-оценке RRF, сработал ли полнотекстовый поиск FTS (fts_rank > 0)."""
    if has_query_vec:
        return raw_rrf > _MAX_VECTOR_ONLY_RRF
    return raw_rrf > 0.0


def _calculate_domain_bonus(ev: Event, profile: ClientQueryExtracted) -> float:
    """
    Вычисляет дополнительный бонус за совпадение тематических тегов, текста события,
    предпочтительного формата и города.
    """
    bonus = 0.0
    if profile.preferred_formats and ev.event_format in profile.preferred_formats:
        bonus += FORMAT_BONUS_WEIGHT
    if profile.cities and ev.city in profile.cities:
        bonus += CITY_BONUS_WEIGHT
    if profile.themes_keywords:
        n_kw = len(profile.themes_keywords)
        theme_hits, text_hits = _count_thematic_hits(ev, profile.themes_keywords)
        bonus += min(0.036, theme_hits * THEME_TAG_MATCH_WEIGHT) + THEME_TAG_COVERAGE_WEIGHT * (theme_hits / n_kw)
        bonus += min(0.018, text_hits * TEXT_MATCH_WEIGHT) + TEXT_COVERAGE_WEIGHT * (text_hits / n_kw)
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


def _is_candidate_thematically_relevant(
    ev: Event,
    raw_rrf: float,
    profile: ClientQueryExtracted,
    has_query_vec: bool,
) -> bool:
    """Определяет, есть ли у кандидата тематическое совпадение (FTS, теги или текст)."""
    if not profile.themes_keywords:
        return True
    if _has_fts_match(raw_rrf, has_query_vec):
        return True
    theme_hits, text_hits = _count_thematic_hits(ev, profile.themes_keywords)
    return (theme_hits + text_hits) > 0


async def _fetch_filtered_events_map(
    session: AsyncSession,
    profile: ClientQueryExtracted,
    query_vec: list[float] | None,
    fts_query_str: str,
    today: datetime.date,
) -> dict[int, tuple[Event, float, bool]]:
    """
    Выполняет каскадный гибридный RRF-поиск в PostgreSQL:
    1) Топ-15 строго в пределах бюджета и дат;
    2) При нехватке кандидатов (< K) — добор в пределах +10% допуска бюджета;
    3) При нехватке кандидатов (< K) — добор с ослаблением дат при сохранении географии.
    """
    import app.services.matcher as matcher_pkg

    has_query_vec = query_vec is not None
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
    events_map: dict[int, tuple[Event, float, bool]] = {
        ev.id: (
            ev,
            score + _calculate_domain_bonus(ev, profile),
            _is_candidate_thematically_relevant(ev, score, profile, has_query_vec),
        )
        for ev, score in strict_rows
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
            events_map[ev.id] = (
                ev,
                score + _calculate_domain_bonus(ev, profile),
                _is_candidate_thematically_relevant(ev, score, profile, has_query_vec),
            )
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
            events_map[ev.id] = (
                ev,
                (score + _calculate_domain_bonus(ev, profile)) * 0.85,
                _is_candidate_thematically_relevant(ev, score, profile, has_query_vec),
            )
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
    relevant_ids: set[int] = set()
    for ev_id, (ev, total_rrf, is_relevant) in events_map.items():
        all_t = tariffs_by_event.get(ev_id, [])
        if not all_t:
            continue
        if is_relevant:
            relevant_ids.add(ev_id)
        candidates.append(
            ScoredEventCandidate(
                event=ev,
                rrf_score=total_rrf,
                all_tariffs=all_t,
                priced_tariffs=[t for t in all_t if t.actual_price is not None],
                on_request_tariffs=[t for t in all_t if t.actual_price is None],
            )
        )

    if profile.themes_keywords and relevant_ids:
        candidates = [c for c in candidates if c.event.id in relevant_ids]

    candidates.sort(key=lambda c: c.rrf_score, reverse=True)
    return candidates
