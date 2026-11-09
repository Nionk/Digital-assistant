import asyncio
import datetime
import itertools
import logging
import re
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, TypeAlias, cast

# pyrefly: ignore[missing-import]
import httpx

# pyrefly: ignore[missing-import]
from instructor.core import InstructorRetryException

# pyrefly: ignore[missing-import]
from openai import APIError

# pyrefly: ignore[missing-import]
from pydantic import BaseModel, Field, ValidationError

# pyrefly: ignore[missing-import]
from sqlalchemy import and_, case, delete, exists, func, or_, select

# pyrefly: ignore[missing-import]
from sqlalchemy.ext.asyncio import AsyncSession

# pyrefly: ignore[missing-import]
from sqlalchemy.sql.elements import ColumnElement

from app.core.config import settings
from app.core.timeutils import today_local
from app.models.models import Client, Event, EventTariff, Selection, SelectionItem
from app.schemas.manager import (
    BundleEventItemOut,
    BundleVariantOut,
    ClientQueryExtracted,
    MatchRequestIn,
    MatchResponseOut,
    TariffOptionOut,
)
from app.services.ai_client import LLM_SEMAPHORE, get_embedding, structured_llm_client
from app.services.profiler import extract_client_profile

logger = logging.getLogger(__name__)

EventFormat: TypeAlias = Literal["roundtable", "business_breakfast", "forum", "conference", "session"]
ParticipationRole: TypeAlias = Literal["delegate", "speaker", "sponsor"]
EventDataStatus: TypeAlias = Literal["ready", "needs_enrichment", "archived"]


@dataclass
class ScoredEventCandidate:
    """Кандидат мероприятия с рассчитанным RRF-рейтингом и разделенными тарифами."""

    event: Event
    rrf_score: float
    all_tariffs: list[TariffOptionOut]
    priced_tariffs: list[TariffOptionOut]
    on_request_tariffs: list[TariffOptionOut]


@dataclass
class EvaluatedCombo:
    """Оцененная комбинация мероприятий с назначенными тарифами и флагами соблюдения ограничений."""

    candidates: tuple[ScoredEventCandidate, ...]
    chosen_tariffs: tuple[TariffOptionOut, ...]
    total_actual_price: float
    total_base_price: float
    total_savings: float
    earliest_deadline: datetime.date | None
    combo_score: float
    is_over_budget_tolerance: bool
    roles_strictly_matched: bool = True
    has_date_conflict: bool = False
    matched_speaker_count: int = 0


class EventRationaleLLMItem(BaseModel):
    event_id: int = Field(..., description="ID мероприятия из переданного списка")
    ai_rationale: str = Field(
        ...,
        description="Краткое (1-2 предложения) убедительное обоснование для клиента, почему выбрано это событие и эта роль участия.",
    )


class PitchAndRationalesLLMResponse(BaseModel):
    rationales: list[EventRationaleLLMItem] = Field(
        default_factory=list,
        description="Список обоснований для каждого переданного мероприятия по его event_id.",
    )
    generated_pitch_text: str = Field(
        ...,
        description=(
            "Живое, персонализированное сопроводительное письмо клиенту от лица менеджера без спам-штампов. "
            "Используй ТОЛЬКО переданные точные цифры общей стоимости, базовой стоимости, экономии Early Bird и дат."
        ),
    )


def _normalize_participation_role(raw_role: str | None) -> ParticipationRole:
    """Приводит строковую роль из БД к строгому типу ParticipationRole."""
    if raw_role == "speaker":
        return "speaker"
    if raw_role == "sponsor":
        return "sponsor"
    return "delegate"


def _normalize_event_format(raw_format: str | None) -> EventFormat:
    """Приводит строковый формат события из БД к строгому типу EventFormat."""
    if raw_format == "roundtable":
        return "roundtable"
    if raw_format == "business_breakfast":
        return "business_breakfast"
    if raw_format == "forum":
        return "forum"
    if raw_format == "session":
        return "session"
    return "conference"


def _normalize_data_status(raw_status: str | None) -> EventDataStatus:
    """Приводит статус полноты данных из БД к строгому типу EventDataStatus."""
    if raw_status == "needs_enrichment":
        return "needs_enrichment"
    if raw_status == "archived":
        return "archived"
    return "ready"


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


def build_tariff_option(t: EventTariff, today: datetime.date) -> TariffOptionOut:
    """
    Переводит ORM-модель EventTariff в схему TariffOptionOut с детерминированным расчетом
    актуальной цены (actual_price) и экономии раннего бронирования (savings) на сегодня.
    """
    base = float(t.base_price) if t.base_price is not None else None
    eb = float(t.early_bird_price) if t.early_bird_price is not None else None

    if base is None:
        actual = None
        savings = 0.0
    elif eb is not None and t.early_bird_deadline is not None and t.early_bird_deadline >= today:
        actual = eb
        savings = round(max(0.0, base - eb), 2)
    else:
        actual = base
        savings = 0.0

    return TariffOptionOut(
        tariff_id=t.id,
        tariff_name=t.tariff_name,
        participation_role=_normalize_participation_role(t.participation_role),
        base_price=base,
        early_bird_price=eb,
        early_bird_deadline=t.early_bird_deadline,
        actual_price=actual,
        savings=savings,
        included_benefits=t.included_benefits,
    )


def build_default_rationale(
    event: Event,
    tariff: TariffOptionOut,
    profile: ClientQueryExtracted,
) -> str:
    """Детерминированный генератор обоснования (на случай пропуска event_id моделью или таймаута)."""
    matched_themes = [
        t for t in (event.themes or [])
        if any(kw.lower() in t.lower() or t.lower() in kw.lower() for kw in profile.themes_keywords)
    ]
    themes_str = (
        ", ".join(matched_themes[:3])
        if matched_themes
        else ", ".join((event.themes or ["деловая повестка"])[:2])
    )
    role_label = {
        "speaker": "выступление со спикерским докладом в целевой сессии и укрепление экспертной позиции",
        "sponsor": "партнерская и стендовая интеграция с вовлечением целевой аудитории на площадке",
        "delegate": "целевые деловые знакомства и прямой выход на ключевых игроков отрасли",
    }.get(tariff.participation_role, "профильное участие")
    loc = "онлайн-формате" if event.is_online else f"г. {event.city}"
    return f"Приоритетная площадка по направлениям ({themes_str}) в {loc}: обеспечивает {role_label}."


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
    strict_rows = await fetch_hybrid_rrf_candidates(
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
    tolerance_rows = await fetch_hybrid_rrf_candidates(
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

    relaxed_rows = await fetch_hybrid_rrf_candidates(
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
    query_vec: list[float] | None = None
    try:
        query_vec = await get_embedding(profile.semantic_search_query)
    except (RuntimeError, APIError, httpx.HTTPError, TimeoutError, ValueError):
        logger.warning(
            "Не удалось получить эмбеддинг для запроса %r, переключаемся на FTS-only поиск",
            profile.semantic_search_query,
            exc_info=True,
        )
        query_vec = None

    events_map = await _fetch_filtered_events_map(
        session, profile, query_vec, build_fts_or_query(profile), today
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


def has_offline_date_conflict(candidates: Sequence[ScoredEventCandidate]) -> bool:
    """
    Проверяет пересечение дат между двумя ОЧНЫМИ мероприятиями в комбинации.
    Онлайн-мероприятия могут совмещаться с очными без конфликта логистики.
    """
    offline_events = [c.event for c in candidates if not c.event.is_online]
    n = len(offline_events)
    for i in range(n):
        for j in range(i + 1, n):
            e1, e2 = offline_events[i], offline_events[j]
            if e1.start_date <= e2.end_date and e2.start_date <= e1.end_date:
                return True
    return False


def _tariff_sort_key(t: TariffOptionOut) -> tuple[float, float]:
    """Ключ сортировки тарифов: минимальная цена, при равенстве — максимальная скидка Early Bird."""
    return (t.actual_price if t.actual_price is not None else 0.0, -(t.savings or 0.0))


def _pick_cheapest_by_role(
    priced_tariffs: list[TariffOptionOut],
    role: ParticipationRole,
) -> TariffOptionOut | None:
    """Возвращает самый выгодный тариф заданной роли или None, если подходящих тарифов нет."""
    matches = [t for t in priced_tariffs if t.participation_role == role]
    return min(matches, key=_tariff_sort_key) if matches else None


def pick_best_tariff_for_role(
    priced_tariffs: list[TariffOptionOut],
    target_role: ParticipationRole,
    allow_role_fallback: bool = False,
) -> tuple[TariffOptionOut | None, bool]:
    """
    Выбирает оптимальный по цене тариф для заданной роли ('speaker', 'delegate', 'sponsor').
    Возвращает кортеж (TariffOptionOut | None, is_strict_role_match: bool).
    Спикерский слот при allow_role_fallback=True может быть заменен только на партнерский ('sponsor'),
    но никогда не подменяется на обычный билет слушателя ('delegate').
    """
    strict_match = _pick_cheapest_by_role(priced_tariffs, target_role)
    if strict_match is not None:
        return strict_match, True

    if not allow_role_fallback or not priced_tariffs:
        return None, False

    if target_role == "speaker":
        return _pick_cheapest_by_role(priced_tariffs, "sponsor"), False
    if target_role == "sponsor":
        return _pick_cheapest_by_role(priced_tariffs, "speaker"), False
    return min(priced_tariffs, key=_tariff_sort_key), False


def _sum_tariff_totals(chosen_tariffs: list[TariffOptionOut]) -> tuple[float, float, float]:
    """Суммирует актуальную стоимость, базовую стоимость и экономию по выбранным тарифам."""
    total_actual = round(sum(t.actual_price or 0.0 for t in chosen_tariffs), 2)
    total_base = round(sum(t.base_price or 0.0 for t in chosen_tariffs), 2)
    total_savings = round(sum(t.savings or 0.0 for t in chosen_tariffs), 2)
    return total_actual, total_base, total_savings


def _build_evaluated_combo(
    combo: tuple[ScoredEventCandidate, ...],
    chosen_tariffs: list[TariffOptionOut],
    budget_max: float,
    strict_roles_ok: bool,
    date_conflict: bool,
) -> EvaluatedCombo:
    """Конструирует объект EvaluatedCombo с точным расчетом стоимости, экономии и дедлайнов."""
    total_actual, total_base, total_savings = _sum_tariff_totals(chosen_tariffs)
    deadlines = [
        t.early_bird_deadline
        for t in chosen_tariffs
        if (t.savings or 0.0) > 0 and t.early_bird_deadline is not None
    ]
    return EvaluatedCombo(
        candidates=combo,
        chosen_tariffs=tuple(chosen_tariffs),
        total_actual_price=total_actual,
        total_base_price=total_base,
        total_savings=total_savings,
        earliest_deadline=min(deadlines) if deadlines else None,
        combo_score=sum(c.rrf_score for c in combo),
        is_over_budget_tolerance=total_actual > budget_max,
        roles_strictly_matched=strict_roles_ok,
        has_date_conflict=date_conflict,
        matched_speaker_count=sum(1 for t in chosen_tariffs if t.participation_role == "speaker"),
    )


def _match_tariffs_for_speaker_set(
    combo: tuple[ScoredEventCandidate, ...],
    speaker_set: set[int],
    default_role: ParticipationRole,
    allow_role_fallback: bool,
) -> tuple[list[TariffOptionOut], bool] | None:
    """Подбирает тарифы для заданного распределения спикерских слотов внутри комбинации."""
    chosen_tariffs: list[TariffOptionOut] = []
    strict_roles_ok = True
    for idx, cand in enumerate(combo):
        desired_role: ParticipationRole = "speaker" if idx in speaker_set else default_role
        t, is_strict = pick_best_tariff_for_role(cand.priced_tariffs, desired_role, allow_role_fallback)
        if t is None:
            return None
        strict_roles_ok = strict_roles_ok and is_strict
        chosen_tariffs.append(t)
    return chosen_tariffs, strict_roles_ok


def evaluate_candidate_tuple(
    combo: tuple[ScoredEventCandidate, ...],
    min_speaker_events: int,
    required_roles: Sequence[str],
    budget_max: float,
    check_dates: bool = True,
    allow_role_fallback: bool = False,
) -> list[EvaluatedCombo]:
    """
    Для выбранной комбинации из K мероприятий перебирает распределение спикерских/спонсорских
    и делегатских слотов и возвращает валидные оцененные комбинации.
    Еcли комбинация размера K меньше запрошенного min_speaker_events, комбинация отклоняется.
    """
    date_conflict = has_offline_date_conflict(combo)
    if check_dates and date_conflict:
        return []

    k = len(combo)
    s_needed = 1 if list(required_roles) == ["speaker"] and min_speaker_events == 0 else max(0, min_speaker_events)
    if s_needed > k:
        return []

    other_roles: list[ParticipationRole] = [cast(ParticipationRole, r) for r in required_roles if r != "speaker"]
    if not other_roles:
        other_roles = ["delegate"]

    valid_evaluations: list[EvaluatedCombo] = []
    for speaker_indices in itertools.combinations(range(k), s_needed):
        spk_set = set(speaker_indices)
        remaining_indices = [i for i in range(k) if i not in spk_set]

        if not remaining_indices:
            matched = _match_tariffs_for_speaker_set(combo, spk_set, other_roles[0], allow_role_fallback)
            if matched is not None:
                m_tariffs, m_strict = matched
                valid_evaluations.append(
                    _build_evaluated_combo(combo, m_tariffs, budget_max, m_strict, date_conflict)
                )
            continue

        for role_assignment in itertools.product(other_roles, repeat=len(remaining_indices)):
            # Если слотов достаточно для всех запрошенных не-спикерских ролей, требуем их полного покрытия
            if len(remaining_indices) >= len(other_roles) and any(r not in role_assignment for r in other_roles):
                continue

            chosen_tariffs: list[TariffOptionOut] = []
            strict_roles_ok = True
            matched_all = True
            role_map = dict(zip(remaining_indices, role_assignment))
            for idx, cand in enumerate(combo):
                desired_role: ParticipationRole = "speaker" if idx in spk_set else role_map[idx]
                t, is_strict = pick_best_tariff_for_role(cand.priced_tariffs, desired_role, allow_role_fallback)
                if t is None:
                    matched_all = False
                    break
                strict_roles_ok = strict_roles_ok and is_strict
                chosen_tariffs.append(t)
            if matched_all:
                valid_evaluations.append(
                    _build_evaluated_combo(combo, chosen_tariffs, budget_max, strict_roles_ok, date_conflict)
                )
    return valid_evaluations


def _collect_valid_combos(
    priced_pool: list[ScoredEventCandidate],
    profile: ClientQueryExtracted,
    target_k: int,
) -> tuple[dict[int, list[EvaluatedCombo]], dict[int, list[EvaluatedCombo]]]:
    """
    Перебирает комбинации без календарных коллизий (check_dates=True) и раскладывает их
    в строгие (<= budget) и допустимые с отклонением до +10% (<= budget * 1.10).
    """
    budget = profile.total_budget_max
    max_tolerance_budget = budget * 1.10
    strict_by_k: dict[int, list[EvaluatedCombo]] = defaultdict(list)
    tolerance_by_k: dict[int, list[EvaluatedCombo]] = defaultdict(list)
    req_roles = list(profile.required_roles)

    for k in range(target_k, 0, -1):
        for combo_tuple in itertools.combinations(priced_pool, k):
            evals = evaluate_candidate_tuple(
                combo=combo_tuple,
                min_speaker_events=profile.min_speaker_events,
                required_roles=req_roles,
                budget_max=budget,
                check_dates=True,
                allow_role_fallback=False,
            )
            if not evals:
                evals = evaluate_candidate_tuple(
                    combo=combo_tuple,
                    min_speaker_events=profile.min_speaker_events,
                    required_roles=req_roles,
                    budget_max=budget,
                    check_dates=True,
                    allow_role_fallback=True,
                )
            for ev_combo in evals:
                if ev_combo.total_actual_price <= budget:
                    strict_by_k[k].append(ev_combo)
                elif ev_combo.total_actual_price <= max_tolerance_budget:
                    tolerance_by_k[k].append(ev_combo)

        distinct_strict_sets = {frozenset(x.event.id for x in c.candidates) for c in strict_by_k[k]}
        if len(distinct_strict_sets) >= 2:
            break

    return strict_by_k, tolerance_by_k


def _v1_priority_key(x: EvaluatedCombo) -> tuple[bool, int, bool, float, float, float]:
    """Ключ сортировки для выбора Варианта №1 (максимальный релевантный охват тем и ролей)."""
    return (
        x.roles_strictly_matched,
        x.matched_speaker_count,
        not x.has_date_conflict,
        round(x.combo_score, 6),
        x.total_savings,
        -x.total_actual_price,
    )


def _select_second_variant(
    variant_1: EvaluatedCombo,
    candidate_pool: list[EvaluatedCombo],
) -> EvaluatedCombo | None:
    """Подбирает диверсифицированный Вариант №2 (оптимальный по экономии бюджета или альтернативный состав)."""
    v1_ids = {c.event.id for c in variant_1.candidates}
    distinct_pool = [
        c
        for c in candidate_pool
        if {x.event.id for x in c.candidates} != v1_ids
        and not ({x.event.id for x in c.candidates} < v1_ids)
    ]
    if not distinct_pool:
        return None

    cheaper = [
        c for c in distinct_pool
        if c.total_actual_price < variant_1.total_actual_price or c.total_savings > variant_1.total_savings
    ]
    if cheaper:
        cheaper.sort(
            key=lambda x: (
                not x.has_date_conflict,
                x.matched_speaker_count,
                x.total_savings,
                round(variant_1.total_actual_price - x.total_actual_price, 2),
                round(x.combo_score, 6),
            ),
            reverse=True,
        )
        return cheaper[0]

    distinct_pool.sort(key=_v1_priority_key, reverse=True)
    return distinct_pool[0]


def _pick_on_request_tariff(cand: ScoredEventCandidate, min_speaker_events: int) -> TariffOptionOut:
    """Выбирает приоритетный тариф со статусом 'По запросу' для бонусного мероприятия."""
    if min_speaker_events > 0:
        for t in cand.on_request_tariffs:
            if t.participation_role == "speaker":
                return t
    return cand.on_request_tariffs[0]


def _select_bonus_on_request_pairs(
    candidates: list[ScoredEventCandidate],
    profile: ClientQueryExtracted,
    excluded_event_ids: set[int],
    limit: int = 2,
) -> list[tuple[ScoredEventCandidate, TariffOptionOut]]:
    """Формирует список бонусных мероприятий со статусом тарифа 'Цена по запросу' (base_price IS NULL)."""
    on_req_cands = [c for c in candidates if c.on_request_tariffs]
    ordered = [c for c in on_req_cands if c.event.id not in excluded_event_ids] + [
        c for c in on_req_cands if c.event.id in excluded_event_ids
    ]
    return [(c, _pick_on_request_tariff(c, profile.min_speaker_events)) for c in ordered[:limit]]


def _pick_best_combo_from_buckets(
    buckets_by_k: dict[int, list[EvaluatedCombo]],
    target_k: int,
) -> EvaluatedCombo | None:
    """Находит лучшую комбинацию максимального размера K в заданном словаре корзин."""
    for k in range(target_k, 0, -1):
        if buckets_by_k[k]:
            buckets_by_k[k].sort(key=_v1_priority_key, reverse=True)
            return buckets_by_k[k][0]
    return None


def _build_v2_candidate_pool(
    strict_by_k: dict[int, list[EvaluatedCombo]],
    tolerance_by_k: dict[int, list[EvaluatedCombo]],
    target_k: int,
) -> list[EvaluatedCombo]:
    """Собирает пул кандидатов для Варианта №2 (с допуском +10% только при < 2 строгих пакетов)."""
    all_strict = [combo for k in range(target_k, 0, -1) for combo in strict_by_k[k]]
    distinct_strict_sets = {frozenset(x.event.id for x in c.candidates) for c in all_strict}
    if len(distinct_strict_sets) >= 2:
        return all_strict
    return [*all_strict, *(combo for k in range(target_k, 0, -1) for combo in tolerance_by_k[k])]


def build_bundles(
    candidates: list[ScoredEventCandidate],
    profile: ClientQueryExtracted,
) -> tuple[list[EvaluatedCombo], list[tuple[ScoredEventCandidate, TariffOptionOut]]]:
    """
    Комбинаторный сборщик пакетов (Задача D-07, время работы < 15 мс).
    Строго соблюдает отсутствие очных календарных коллизий и правило бюджета (допуск +10% только при < 2 строгих вариантов).
    """
    pool_size = min(15, profile.target_events_count + 5)
    priced_pool = [c for c in candidates if c.priced_tariffs][:pool_size]
    if not priced_pool:
        return [], _select_bonus_on_request_pairs(candidates, profile, set(), limit=3)

    target_k = min(profile.target_events_count, len(priced_pool))
    strict_by_k, tolerance_by_k = _collect_valid_combos(priced_pool, profile, target_k)

    if strict_by_k[target_k]:
        strict_by_k[target_k].sort(key=_v1_priority_key, reverse=True)
        variant_1: EvaluatedCombo | None = strict_by_k[target_k][0]
    elif tolerance_by_k[target_k]:
        tolerance_by_k[target_k].sort(key=_v1_priority_key, reverse=True)
        variant_1 = tolerance_by_k[target_k][0]
    else:
        variant_1 = _pick_best_combo_from_buckets(strict_by_k, target_k) or _pick_best_combo_from_buckets(
            tolerance_by_k, target_k
        )
    if variant_1 is None:
        return [], _select_bonus_on_request_pairs(candidates, profile, set(), limit=2)

    selected_variants: list[EvaluatedCombo] = [variant_1]
    v2_pool = _build_v2_candidate_pool(strict_by_k, tolerance_by_k, target_k)

    v1_k = len(variant_1.candidates)
    same_size_pool = [c for c in v2_pool if len(c.candidates) == v1_k]
    variant_2 = _select_second_variant(variant_1, same_size_pool) or _select_second_variant(variant_1, v2_pool)
    if variant_2 is not None:
        selected_variants.append(variant_2)

    selected_event_ids = {c.event.id for var in selected_variants for c in var.candidates}
    return selected_variants, _select_bonus_on_request_pairs(candidates, profile, selected_event_ids, limit=2)


def build_fallback_pitch(
    client_name: str,
    profile: ClientQueryExtracted,
    v1: EvaluatedCombo,
) -> str:
    """
    Формирует чистый, выверенный шаблон КП на случай недоступности внешнего LLM-шлюза.
    Корректно адаптируется к составу ролей и отсутствию скидок Early Bird (total_savings == 0.0).
    """
    titles = ", ".join(f"«{c.event.canonical_title}»" for c in v1.candidates)
    themes_str = ", ".join(profile.themes_keywords[:3]) if profile.themes_keywords else "ключевым отраслевым направлениям"
    price_str = f"{int(v1.total_actual_price):,}".replace(",", " ")
    budget_str = f"{int(profile.total_budget_max):,}".replace(",", " ")
    budget_clause = (
        f" при согласованном ориентире бюджета {budget_str} ₽"
        if not getattr(profile, "budget_is_assumed", False)
        else ""
    )

    pitch = (
        f"Добрый день! По итогам установочной встречи подготовили для компании {client_name} "
        f"рекомендованный календарь профильных мероприятий по направлениям: {themes_str}.\n\n"
        f"В приоритетный пакет вошли {len(v1.candidates)} площадки без пересечений по датам: {titles}.\n\n"
        f"Расчет внешних расходов (взносы организаторов по выбранным тарифам) составляет {price_str} ₽ (с НДС)"
        f"{budget_clause}."
    )

    if v1.total_savings > 0 and v1.earliest_deadline is not None:
        base_str = f"{int(v1.total_base_price):,}".replace(",", " ")
        savings_str = f"{int(v1.total_savings):,}".replace(",", " ")
        dl_str = v1.earliest_deadline.strftime("%d.%m.%Y")
        pitch += (
            f" При согласовании плана и бронировании до {dl_str} действуют льготные условия Early Bird "
            f"и партнёрские преференции — прямая выгода составит {savings_str} ₽ "
            f"(базовая стоимость без скидки — {base_str} ₽)."
        )

    if v1.matched_speaker_count > 0:
        pitch += (
            "\n\nСо стороны агентства мы берем на себя согласование условий с организаторами, "
            "подготовку экспертного выступления спикера и организацию целевых деловых знакомств на площадках."
        )
    else:
        pitch += (
            "\n\nСо стороны агентства мы берем на себя согласование условий с организаторами, "
            "аккредитацию участников и организацию целевых деловых знакомств на площадках."
        )
    return pitch


def _collect_unique_events_for_pitch(
    selected_variants: list[EvaluatedCombo],
    bonus_pairs: list[tuple[ScoredEventCandidate, TariffOptionOut]],
) -> dict[int, tuple[Event, TariffOptionOut]]:
    """Собирает словарь уникальных событий и назначенных им тарифов для генерации обоснований."""
    unique_info: dict[int, tuple[Event, TariffOptionOut]] = {}
    for var in selected_variants:
        for cand, tariff in zip(var.candidates, var.chosen_tariffs):
            if cand.event.id not in unique_info:
                unique_info[cand.event.id] = (cand.event, tariff)
    for cand, tariff in bonus_pairs:
        if cand.event.id not in unique_info:
            unique_info[cand.event.id] = (cand.event, tariff)
    return unique_info


def _format_event_line_for_pitch(ev_id: int, ev: Event, tar: TariffOptionOut) -> str:
    """Форматирует описание одного мероприятия и тарифа для промпта генерации КП."""
    loc = "Онлайн" if ev.is_online else ev.city
    if tar.actual_price is None:
        price_info = "По запросу"
    elif tar.actual_price == 0.0:
        price_info = "0 руб. (бесплатно)"
    else:
        price_info = f"{int(tar.actual_price)} руб."
    return (
        f"- event_id={ev_id}: «{ev.canonical_title}» ({ev.event_format}, {loc}, {ev.start_date}). "
        f"Темы: {', '.join(ev.themes or [])}. Выбранный тариф: «{tar.tariff_name}» "
        f"(роль: {tar.participation_role}, цена: {price_info})."
    )


def _build_pitch_prompts(
    client_name: str,
    raw_notes: str,
    profile: ClientQueryExtracted,
    v1: EvaluatedCombo,
    unique_events_info: dict[int, tuple[Event, TariffOptionOut]],
) -> tuple[str, str]:
    """Формирует системный и пользовательский промпты для генерации КП и обоснований."""
    events_lines = [_format_event_line_for_pitch(ev_id, ev, tar) for ev_id, (ev, tar) in unique_events_info.items()]
    eb_clause = (
        f"Экономия Early Bird: {int(v1.total_savings)} руб. при бронировании до {v1.earliest_deadline.isoformat()}."
        if (v1.total_savings > 0 and v1.earliest_deadline is not None)
        else "Специальных скидок Early Bird в данном пакете нет (экономия 0 руб., не упоминай скидки в письме)."
    )
    agency_role_clause = (
        "подготовку спикера и организацию целевых встреч"
        if v1.matched_speaker_count > 0
        else "согласование участия с организаторами и организацию целевых встреч"
    )
    v1_summary = (
        f"Состав Варианта №1 ({len(v1.candidates)} событий): "
        + ", ".join(f"«{c.event.canonical_title}» (тариф {t.tariff_name})" for c, t in zip(v1.candidates, v1.chosen_tariffs))
        + f". Итоговая стоимость пакета: {int(v1.total_actual_price)} руб. "
        + f"Базовая стоимость: {int(v1.total_base_price)} руб. "
        + eb_clause
    )
    system_prompt = (
        "Ты — ведущий менеджер сопровождения делового B2B-агентства. "
        "Сформируй персональные аргументы выбора площадки (ai_rationale) для каждого мероприятия из списка "
        "(укажи ценность целевой аудитории и какую задачу решает формат: целевые деловые знакомства, экспертное выступление в сессии или вовлечение аудитории на стенде) "
        "и напиши живое, убедительное сопроводительное письмо клиенту (generated_pitch_text) без канцеляризмов и спам-штампов. "
        f"В письме подчеркни, что календарь сверен без пересечений по срокам, укажи бюджет внешних взносов организаторам "
        f"и готовность агентства взять на себя {agency_role_clause}. "
        "КРИТИЧЕСКОЕ ПРАВИЛО: В письме используй ТОЛЬКО переданные ниже цифры стоимости Варианта №1 и дат. "
        "Ничего не пересчитывай самостоятельно и не выдумывай несуществующие скидки."
    )
    budget_line = (
        f"Лимит бюджета клиента: {int(profile.total_budget_max)} руб.\n\n"
        if not getattr(profile, "budget_is_assumed", False)
        else "Клиент не зафиксировал жесткий бюджет (не упоминай в письме формулировки 'согласованный бюджет').\n\n"
    )
    user_prompt = (
        f"Клиент: {client_name}\nИсходная заметка созвона: {raw_notes}\n"
        f"{budget_line}"
        f"Точные параметры Варианта №1 для письма:\n{v1_summary}\n\n"
        f"Список всех мероприятий для генерации ai_rationale:\n" + "\n".join(events_lines)
    )
    return system_prompt, user_prompt


async def _request_pitch_from_llm(
    system_prompt: str,
    user_prompt: str,
) -> PitchAndRationalesLLMResponse | None:
    """Выполняет защищенный LLM_SEMAPHORE вызов к LLM для генерации КП и обоснований."""
    try:
        async with LLM_SEMAPHORE:
            res: PitchAndRationalesLLMResponse = await asyncio.wait_for(
                structured_llm_client.chat.completions.create(
                    model=settings.LLM_MODEL,
                    response_model=PitchAndRationalesLLMResponse,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    max_retries=1,
                ),
                timeout=25.0,
            )
            return res
    except (TimeoutError, APIError, httpx.HTTPError, ValidationError, InstructorRetryException) as exc:
        logger.warning(
            "Сбой генерации текста КП через LLM (%s: %s). Применяется детерминированный шаблон.",
            type(exc).__name__,
            exc,
            exc_info=True,
        )
        return None


def _merge_llm_rationales(
    rationales_map: dict[int, str],
    llm_res: PitchAndRationalesLLMResponse | None,
    fallback_pitch: str,
) -> tuple[dict[int, str], str]:
    """Объединяет детерминированные обоснования с ответом LLM при его наличии."""
    if llm_res is None:
        return rationales_map, fallback_pitch
    for item in llm_res.rationales:
        if item.event_id in rationales_map and item.ai_rationale.strip():
            rationales_map[item.event_id] = item.ai_rationale.strip()
    return rationales_map, (llm_res.generated_pitch_text.strip() or fallback_pitch)


async def generate_pitch_and_rationales(
    client_name: str,
    raw_notes: str,
    profile: ClientQueryExtracted,
    selected_variants: list[EvaluatedCombo],
    bonus_pairs: list[tuple[ScoredEventCandidate, TariffOptionOut]],
) -> tuple[dict[int, str], str]:
    """
    За 1 сетевой вызов к structured_llm_client (под защитой LLM_SEMAPHORE) генерирует обоснования
    (ai_rationale) для всех уникальных событий и сопроводительное письмо по цифрам Варианта №1.
    """
    unique_events_info = _collect_unique_events_for_pitch(selected_variants, bonus_pairs)
    rationales_map: dict[int, str] = {
        ev_id: build_default_rationale(ev, tar, profile)
        for ev_id, (ev, tar) in unique_events_info.items()
    }

    if not selected_variants:
        city_clause = f" (город: {', '.join(profile.cities)})" if profile.cities else ""
        return (
            rationales_map,
            f"По вашему запросу{city_clause} не найдено подходящих пакетных предложений в базе знаний агентства. Рекомендуется скорректировать параметры отбора или добавить новые площадки.",
        )

    v1 = selected_variants[0]
    fallback_pitch = build_fallback_pitch(client_name, profile, v1)
    if not settings.LLM_API_KEY:
        return rationales_map, fallback_pitch

    system_prompt, user_prompt = _build_pitch_prompts(
        client_name, raw_notes, profile, v1, unique_events_info
    )
    llm_res = await _request_pitch_from_llm(system_prompt, user_prompt)
    return _merge_llm_rationales(rationales_map, llm_res, fallback_pitch)


def _to_bundle_event_item(
    cand: ScoredEventCandidate,
    recommended_tariff: TariffOptionOut,
    rationale: str,
) -> BundleEventItemOut:
    """Собирает выходную карточку BundleEventItemOut со строгой нормализацией типов."""
    ev = cand.event
    primary_url = str(ev.source_urls[0]) if (ev.source_urls and len(ev.source_urls) > 0) else None
    return BundleEventItemOut(
        event_id=ev.id,
        canonical_title=ev.canonical_title,
        event_format=_normalize_event_format(ev.event_format),
        city=ev.city,
        is_online=bool(ev.is_online),
        venue=ev.venue,
        start_date=ev.start_date,
        end_date=ev.end_date,
        themes=list(ev.themes or []),
        recommended_tariff=recommended_tariff,
        available_tariffs=cand.all_tariffs,
        ai_rationale=rationale,
        website_url=primary_url,
        data_status=_normalize_data_status(ev.data_status),
        missing_data_warnings=list(ev.missing_data_warnings or []),
    )


def _format_bundle_variants_out(
    evaluated_variants: list[EvaluatedCombo],
    rationales_map: dict[int, str],
    unique_events_info: dict[int, tuple[Event, TariffOptionOut]] | None = None,
    profile: ClientQueryExtracted | None = None,
) -> list[BundleVariantOut]:
    """Преобразует оцененные комбинации EvaluatedCombo в выходные схемы BundleVariantOut."""
    bundle_variants_out: list[BundleVariantOut] = []
    for idx, ev_var in enumerate(evaluated_variants, start=1):
        items_out = []
        for cand, tar in zip(ev_var.candidates, ev_var.chosen_tariffs):
            if unique_events_info and profile and cand.event.id in unique_events_info:
                ref_tariff = unique_events_info[cand.event.id][1]
                if tar.participation_role == ref_tariff.participation_role:
                    rationale = rationales_map.get(cand.event.id, "")
                else:
                    rationale = build_default_rationale(cand.event, tar, profile)
            else:
                rationale = rationales_map.get(cand.event.id, "")
            items_out.append(
                _to_bundle_event_item(
                    cand=cand,
                    recommended_tariff=tar,
                    rationale=rationale,
                )
            )
        if idx == 1:
            title = (
                "Вариант 1: Максимальное совпадение по темам (требует согласования бюджета)"
                if ev_var.is_over_budget_tolerance
                else f"Вариант 1: Максимальный охват тем ({len(items_out)} события)"
            )
        else:
            title = (
                f"Вариант 2: Альтернативный состав ({len(items_out)} события, требует согласования бюджета)"
                if ev_var.is_over_budget_tolerance
                else f"Вариант 2: Оптимальный по экономии бюджета ({len(items_out)} события)"
            )

        bundle_variants_out.append(
            BundleVariantOut(
                bundle_group=idx,
                bundle_title=title,
                items=items_out,
                total_actual_price=ev_var.total_actual_price,
                total_base_price=ev_var.total_base_price,
                total_savings=ev_var.total_savings,
                earliest_deadline=ev_var.earliest_deadline,
                is_over_budget_tolerance=ev_var.is_over_budget_tolerance,
            )
        )
    return bundle_variants_out


async def _persist_draft_selection(
    session: AsyncSession,
    client_id: int,
    pitch_text: str,
    budget_limit: float,
    bundle_variants_out: list[BundleVariantOut],
) -> int:
    """Удаляет устаревшие черновики клиента и атомарно сохраняет новый черновик подборки."""
    await session.execute(
        delete(Selection).where(
            Selection.client_id == client_id,
            Selection.status == "draft",
        )
    )
    new_selection = Selection(
        client_id=client_id,
        status="draft",
        generated_pitch_text=pitch_text,
        total_budget_limit=budget_limit,
    )
    session.add(new_selection)
    await session.flush()
    selection_id = new_selection.id

    for variant in bundle_variants_out:
        for item in variant.items:
            session.add(
                SelectionItem(
                    selection_id=selection_id,
                    event_id=item.event_id,
                    recommended_tariff_id=item.recommended_tariff.tariff_id,
                    bundle_group=variant.bundle_group,
                    ai_rationale=item.ai_rationale,
                    client_reaction="pending",
                )
            )
    await session.commit()
    return selection_id


async def _load_and_update_client_profile(
    session: AsyncSession,
    client_id: int,
    payload: MatchRequestIn,
) -> tuple[Client, ClientQueryExtracted]:
    """Загружает клиента из БД и обновляет его сохраненный NER-профиль."""
    client_res = await session.execute(select(Client).where(Client.id == client_id))
    client_obj = client_res.scalar_one_or_none()
    if client_obj is None:
        raise LookupError(f"Клиент с ID={client_id} не найден")

    if payload.override_profile is not None:
        extracted_profile = payload.override_profile
        extracted_profile.profile_source = "manual"
    else:
        extracted_profile = await extract_client_profile(payload.raw_manager_notes)

    client_obj.raw_manager_notes = payload.raw_manager_notes
    client_obj.extracted_profile = extracted_profile.model_dump(mode="json")
    return client_obj, extracted_profile


async def run_client_matching_pipeline(
    session: AsyncSession,
    client_id: int,
    payload: MatchRequestIn,
) -> MatchResponseOut:
    """
    Полный цикл Задачи D-07 + сохранение черновика подборки в БД.
    Выбрасывает LookupError, если клиент с указанным client_id отсутствует в БД.
    """
    client_obj, extracted_profile = await _load_and_update_client_profile(session, client_id, payload)
    candidates = await get_scored_candidates(session, extracted_profile, today_local())
    evaluated_variants, bonus_pairs = await asyncio.to_thread(
        build_bundles, candidates, extracted_profile
    )

    rationales_map, pitch_text = await generate_pitch_and_rationales(
        client_name=client_obj.company_name,
        raw_notes=payload.raw_manager_notes,
        profile=extracted_profile,
        selected_variants=evaluated_variants,
        bonus_pairs=bonus_pairs,
    )
    unique_events_info = _collect_unique_events_for_pitch(evaluated_variants, bonus_pairs)
    bundle_variants_out = _format_bundle_variants_out(
        evaluated_variants, rationales_map, unique_events_info, extracted_profile
    )
    bonus_items_out = [
        _to_bundle_event_item(cand, tar, rationales_map.get(cand.event.id, ""))
        for cand, tar in bonus_pairs
    ]
    selection_id = await _persist_draft_selection(
        session, client_obj.id, pitch_text, extracted_profile.total_budget_max, bundle_variants_out
    )

    return MatchResponseOut(
        selection_id=selection_id,
        client_id=client_id,
        extracted_profile=extracted_profile,
        bundle_variants=bundle_variants_out,
        bonus_on_request_items=bonus_items_out,
        generated_pitch_text=pitch_text,
    )
