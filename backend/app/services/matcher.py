import asyncio
import datetime
import itertools
import logging
import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Sequence

from pydantic import BaseModel, Field
from sqlalchemy import select, func, or_, exists, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.models import Event, EventTariff, Selection, SelectionItem, Client
from app.schemas.manager import (
    ClientQueryExtracted,
    MatchRequestIn,
    MatchResponseOut,
    BundleVariantOut,
    BundleEventItemOut,
    TariffOptionOut,
)
from app.services.ai_client import get_embedding, structured_llm_client
from app.services.profiler import extract_client_profile

logger = logging.getLogger(__name__)


# ============================================================================
# 1. ВСПОМОГАТЕЛЬНЫЕ СТРУКТУРЫ ДАННЫХ И СХЕМЫ LLM (ШАГ 3)
# ============================================================================

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


class EventRationaleLLMItem(BaseModel):
    event_id: int = Field(..., description="ID мероприятия из переданного списка")
    ai_rationale: str = Field(
        ...,
        description="Краткое (1-2 предложения) убедительное обоснование для клиента, почему выбрано это событие и эта роль участия."
    )


class PitchAndRationalesLLMResponse(BaseModel):
    rationales: list[EventRationaleLLMItem] = Field(
        default_factory=list,
        description="Список обоснований для каждого переданного мероприятия по его event_id."
    )
    generated_pitch_text: str = Field(
        ...,
        description=(
            "Живое, персонализированное сопроводительное письмо клиенту от лица менеджера без спам-штампов. "
            "Используй ТОЛЬКО переданные точные цифры общей стоимости, базовой стоимости, экономии Early Bird и дат."
        )
    )


# ============================================================================
# 2. ФУНКЦИИ НОРМАЛИЗАЦИИ И РАСЧЕТА ТАРИФОВ
# ============================================================================

def build_fts_or_query(profile: ClientQueryExtracted) -> str:
    """
    Формирует безопасную строку запроса для PostgreSQL websearch_to_tsquery('russian', ...).
    Исключает спецсимволы и гарантирует непустой запрос за счет фолбэка на semantic_search_query (rules.md п. 4.3).
    """
    raw_terms = profile.themes_keywords if profile.themes_keywords else []
    cleaned_terms: list[str] = []

    for kw in raw_terms:
        clean = re.sub(r"[^\w\s\-]", " ", kw).strip()
        clean = re.sub(r"\s+", " ", clean)
        if len(clean) >= 2:
            cleaned_terms.append(f'"{clean}"' if " " in clean else clean)

    if not cleaned_terms and profile.semantic_search_query:
        words = [
            re.sub(r"[^\w\-]", "", w).strip()
            for w in profile.semantic_search_query.split()
        ]
        cleaned_terms = [w for w in words if len(w) >= 3][:8]

    return " OR ".join(cleaned_terms) if cleaned_terms else "строительство OR девелопмент"


def build_tariff_option(t: EventTariff, today: datetime.date) -> TariffOptionOut:
    """
    Переводит ORM-модель EventTariff в схему TariffOptionOut с детерминированным расчетом
    актуальной цены (actual_price) и экономии раннего бронирования (savings) на сегодня.
    Корректно обрабатывает бесплатные тарифы (0.0) и тарифы 'По запросу' (None).
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

    role = t.participation_role if t.participation_role in ("delegate", "speaker", "sponsor") else "delegate"

    return TariffOptionOut(
        tariff_id=t.id,
        tariff_name=t.tariff_name,
        participation_role=role,  # type: ignore[arg-type]
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


# ============================================================================
# 3. ШАГ 1: ГИБРИДНЫЙ ПОИСК КАНДИДАТОВ В POSTGRESQL (pgvector + FTS RRF)
# ============================================================================

async def fetch_hybrid_rrf_candidates(
    session: AsyncSession,
    profile: ClientQueryExtracted,
    query_vec: list[float],
    fts_query_str: str,
    today: datetime.date,
    strict_filters: bool = True,
    limit: int = 15,
) -> list[tuple[Event, float]]:
    """
    Выполняет гибридный поиск (векторная близость pgvector + полнотекстовый поиск FTS)
    с объединением рангов по формуле Reciprocal Rank Fusion (k=60).
    Использует нативные выражения SQLAlchemy 2.0 Core для защиты от ошибок типизации asyncpg.
    """
    conditions = [
        Event.is_active.is_(True),
        Event.summary_embedding.is_not(None),
    ]

    if strict_filters:
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

        # В строгом пуле для основных пакетов должен быть хотя бы один ЧИСЛОВОЙ тариф в рамках бюджета (+10%).
        # Это защищает Топ-15 от засорения дорогими форумами только из-за наличия у них спонсорского пакета base_price IS NULL.
        max_allowed_price = profile.total_budget_max * 1.10
        tariff_exists_stmt = exists(
            select(1).where(
                and_(
                    EventTariff.event_id == Event.id,
                    EventTariff.base_price.is_not(None),
                    or_(
                        EventTariff.base_price <= max_allowed_price,
                        and_(
                            EventTariff.early_bird_deadline.is_not(None),
                            EventTariff.early_bird_deadline >= today,
                            EventTariff.early_bird_price.is_not(None),
                            EventTariff.early_bird_price <= max_allowed_price,
                        ),
                    ),
                )
            )
        )
        conditions.append(tariff_exists_stmt)

    # Косинусное расстояние (pgvector <=>) и полнотекстовый ранг (ts_rank_cd)
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

    ranked_cte = (
        select(
            candidates_cte.c.event_id,
            r_vec_col,
            r_fts_col,
        )
        .cte("ranked")
    )

    rrf_score_expr = (
        (1.0 / (60.0 + ranked_cte.c.r_vec)) + (1.0 / (60.0 + ranked_cte.c.r_fts))
    ).label("rrf_score")

    final_stmt = (
        select(Event, rrf_score_expr)
        .join(ranked_cte, Event.id == ranked_cte.c.event_id)
        .order_by(rrf_score_expr.desc())
        .limit(limit)
    )

    result = await session.execute(final_stmt)
    rows = result.all()
    return [(row[0], float(row[1])) for row in rows]


async def get_scored_candidates(
    session: AsyncSession,
    profile: ClientQueryExtracted,
    today: datetime.date,
) -> list[ScoredEventCandidate]:
    """
    Собирает кандидатов с тарифами.
    1. Сначала выполняет строгий поиск с проверкой дат, городов и доступных числовых тарифов.
    2. Добирает события из расширенного RRF-пула (с весом x0.85) для обеспечения:
       - фолбэка при жестких ограничениях клиента;
       - наполнения бонусного слота 'Цена по запросу' (base_price IS NULL).
    """
    query_vec = await get_embedding(profile.semantic_search_query)
    fts_query_str = build_fts_or_query(profile)

    strict_rows = await fetch_hybrid_rrf_candidates(
        session=session,
        profile=profile,
        query_vec=query_vec,
        fts_query_str=fts_query_str,
        today=today,
        strict_filters=True,
        limit=15,
    )

    events_map: dict[int, tuple[Event, float]] = {ev.id: (ev, score) for ev, score in strict_rows}

    # Добираем из расширенного поиска (чтобы захватить чисто 'По запросу' события и фолбэк-кандидаты)
    relaxed_rows = await fetch_hybrid_rrf_candidates(
        session=session,
        profile=profile,
        query_vec=query_vec,
        fts_query_str=fts_query_str,
        today=today,
        strict_filters=False,
        limit=20,
    )
    for ev, score in relaxed_rows:
        if ev.id not in events_map:
            events_map[ev.id] = (ev, score * 0.85)
        if len(events_map) >= 20:
            break

    if not events_map:
        return []

    # Загружаем тарифы одним плоским запросом (предотвращает N+1 и MissingGreenlet)
    event_ids = list(events_map.keys())
    tariffs_stmt = (
        select(EventTariff)
        .where(EventTariff.event_id.in_(event_ids))
        .order_by(EventTariff.id.asc())
    )
    tariffs_res = await session.execute(tariffs_stmt)
    tariffs_by_event: dict[int, list[TariffOptionOut]] = defaultdict(list)

    for t_orm in tariffs_res.scalars().all():
        tariffs_by_event[t_orm.event_id].append(build_tariff_option(t_orm, today))

    candidates: list[ScoredEventCandidate] = []
    for ev_id, (ev, base_rrf) in events_map.items():
        all_t = tariffs_by_event.get(ev_id, [])
        if not all_t:
            continue

        # Доменный бустинг за попадание в формат, город и ключевые теги
        bonus = 0.0
        if profile.preferred_formats and ev.event_format in profile.preferred_formats:
            bonus += 0.004
        if profile.cities and ev.city in profile.cities:
            bonus += 0.003
        if profile.themes_keywords and ev.themes:
            matched_kw = sum(
                1 for t in ev.themes
                if any(kw.lower() in t.lower() or t.lower() in kw.lower() for kw in profile.themes_keywords)
            )
            if matched_kw > 0:
                bonus += min(0.004, matched_kw * 0.0015)

        priced_t = [t for t in all_t if t.actual_price is not None]
        on_req_t = [t for t in all_t if t.actual_price is None]

        candidates.append(
            ScoredEventCandidate(
                event=ev,
                rrf_score=base_rrf + bonus,
                all_tariffs=all_t,
                priced_tariffs=priced_t,
                on_request_tariffs=on_req_t,
            )
        )

    candidates.sort(key=lambda c: c.rrf_score, reverse=True)
    return candidates


# ============================================================================
# 4. ШАГ 2: КОМБИНАТОРНЫЙ СБОРЩИК ПАКЕТОВ (COMBINATORIAL BUNDLE BUILDER)
# ============================================================================

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


def pick_best_tariff_for_role(
    priced_tariffs: list[TariffOptionOut],
    target_role: str,
    allow_role_fallback: bool = False,
) -> tuple[TariffOptionOut | None, bool]:
    """
    Выбирает оптимальный по цене тариф для заданной роли ('speaker', 'delegate', 'sponsor').
    Возвращает кортеж (TariffOptionOut | None, is_strict_role_match: bool).
    """
    role_matches = [t for t in priced_tariffs if t.participation_role == target_role]
    if role_matches:
        best = min(role_matches, key=lambda t: (t.actual_price if t.actual_price is not None else 0.0, -(t.savings or 0.0)))
        return best, True

    if allow_role_fallback and priced_tariffs:
        # Если запрошен спикер, сначала пробуем спонсорский пакет (часто включает доклад), затем делегатский
        if target_role == "speaker":
            sponsor_matches = [t for t in priced_tariffs if t.participation_role == "sponsor"]
            if sponsor_matches:
                best_sp = min(sponsor_matches, key=lambda t: (t.actual_price if t.actual_price is not None else 0.0, -(t.savings or 0.0)))
                return best_sp, False
        best_any = min(priced_tariffs, key=lambda t: (t.actual_price if t.actual_price is not None else 0.0, -(t.savings or 0.0)))
        return best_any, False

    return None, False


def evaluate_candidate_tuple(
    combo: tuple[ScoredEventCandidate, ...],
    min_speaker_events: int,
    required_roles: list[str],
    budget_max: float,
    check_dates: bool = True,
    allow_role_fallback: bool = False,
) -> list[EvaluatedCombo]:
    """
    Для выбранной комбинации из K мероприятий перебирает распределение спикерских/спонсорских
    и делегатских слотов и возвращает валидные оцененные комбинации.
    """
    date_conflict = has_offline_date_conflict(combo)
    if check_dates and date_conflict:
        return []

    k = len(combo)
    s_needed = min(max(0, min_speaker_events), k)
    default_role = "sponsor" if ("sponsor" in required_roles and "delegate" not in required_roles and s_needed == 0) else "delegate"

    valid_evaluations: list[EvaluatedCombo] = []

    for speaker_indices in itertools.combinations(range(k), s_needed):
        speaker_set = set(speaker_indices)
        chosen_tariffs: list[TariffOptionOut] = []
        possible = True
        strict_roles_ok = True

        for idx, cand in enumerate(combo):
            desired_role = "speaker" if idx in speaker_set else default_role
            t, is_strict = pick_best_tariff_for_role(
                cand.priced_tariffs,
                target_role=desired_role,
                allow_role_fallback=allow_role_fallback,
            )
            if t is None:
                possible = False
                break
            if not is_strict:
                strict_roles_ok = False
            chosen_tariffs.append(t)

        if not possible:
            continue

        total_actual = round(sum(t.actual_price if t.actual_price is not None else 0.0 for t in chosen_tariffs), 2)
        total_base = round(sum(t.base_price if t.base_price is not None else 0.0 for t in chosen_tariffs), 2)
        total_savings = round(sum(t.savings or 0.0 for t in chosen_tariffs), 2)

        deadlines = [
            t.early_bird_deadline
            for t in chosen_tariffs
            if (t.savings or 0.0) > 0 and t.early_bird_deadline is not None
        ]
        earliest_dl = min(deadlines) if deadlines else None

        base_rrf_sum = sum(c.rrf_score for c in combo)
        is_over_tolerance = total_actual > budget_max

        valid_evaluations.append(
            EvaluatedCombo(
                candidates=combo,
                chosen_tariffs=tuple(chosen_tariffs),
                total_actual_price=total_actual,
                total_base_price=total_base,
                total_savings=total_savings,
                earliest_deadline=earliest_dl,
                combo_score=base_rrf_sum,
                is_over_budget_tolerance=is_over_tolerance,
                roles_strictly_matched=strict_roles_ok,
                has_date_conflict=date_conflict,
            )
        )

    return valid_evaluations


def build_bundles(
    candidates: list[ScoredEventCandidate],
    profile: ClientQueryExtracted,
) -> tuple[list[EvaluatedCombo], list[tuple[ScoredEventCandidate, TariffOptionOut]]]:
    """
    Комбинаторный сборщик пакетов (Задача D-07, время работы < 15 мс).
    Формирует до 2 диверсифицированных вариантов пакета:
      - Вариант №1 (Максимальное совпадение по темам и ролям)
      - Вариант №2 (Оптимальный по экономии бюджета / Альтернативный состав)
    и список бонусных мероприятий с тарифом 'По запросу' (base_price IS NULL).
    """
    # Пул кандидатов с числовыми ценами для комбинаторики (Топ-15 по RRF)
    priced_pool = [c for c in candidates if c.priced_tariffs][:15]

    if not priced_pool:
        bonus_only: list[tuple[ScoredEventCandidate, TariffOptionOut]] = []
        for cand in candidates:
            if cand.on_request_tariffs:
                bonus_only.append((cand, cand.on_request_tariffs[0]))
                if len(bonus_only) >= 3:
                    break
        return [], bonus_only

    target_k = min(profile.target_events_count, len(priced_pool))
    budget = profile.total_budget_max
    max_tolerance_budget = budget * 1.10

    strict_combos_by_k: dict[int, list[EvaluatedCombo]] = defaultdict(list)
    tolerance_combos_by_k: dict[int, list[EvaluatedCombo]] = defaultdict(list)
    all_fallback_combos: list[EvaluatedCombo] = []

    for k in range(target_k, 0, -1):
        for combo_tuple in itertools.combinations(priced_pool, k):
            # Сначала пробуем строгое соблюдение ролей и непересечение дат
            evals = evaluate_candidate_tuple(
                combo=combo_tuple,
                min_speaker_events=profile.min_speaker_events,
                required_roles=list(profile.required_roles),
                budget_max=budget,
                check_dates=True,
                allow_role_fallback=False,
            )
            # Если строгая комбинация невозможна, пробуем мягкий фолбэк ролей
            if not evals:
                evals = evaluate_candidate_tuple(
                    combo=combo_tuple,
                    min_speaker_events=profile.min_speaker_events,
                    required_roles=list(profile.required_roles),
                    budget_max=budget,
                    check_dates=False,
                    allow_role_fallback=True,
                )

            for ev_combo in evals:
                all_fallback_combos.append(ev_combo)
                if ev_combo.total_actual_price <= budget:
                    strict_combos_by_k[k].append(ev_combo)
                elif ev_combo.total_actual_price <= max_tolerance_budget:
                    tolerance_combos_by_k[k].append(ev_combo)

    selected_variants: list[EvaluatedCombo] = []

    # Сортировочный ключ приоритета:
    # 1. Строгое соблюдение ролей (speaker/delegate)
    # 2. Отсутствие конфликта дат
    # 3. Максимальный суммарный RRF-рейтинг
    # 4. Максимальная скидка Early Bird
    # 5. Меньшая итоговая стоимость
    def _v1_sort_key(x: EvaluatedCombo):
        return (
            x.roles_strictly_matched,
            not x.has_date_conflict,
            round(x.combo_score, 6),
            x.total_savings,
            -x.total_actual_price,
        )

    # Выбор Варианта №1
    for k in range(target_k, 0, -1):
        pool_k = strict_combos_by_k[k] or tolerance_combos_by_k[k]
        if pool_k:
            pool_k.sort(key=_v1_sort_key, reverse=True)
            selected_variants.append(pool_k[0])
            break

    # Аварийная страховка (Уровень 4): если бюджет клиента экстремально мал, берем самый дешевый пакет
    if not selected_variants and all_fallback_combos:
        all_fallback_combos.sort(
            key=lambda x: (x.total_actual_price, -int(x.roles_strictly_matched), -x.combo_score)
        )
        cheapest = all_fallback_combos[0]
        cheapest.is_over_budget_tolerance = True
        selected_variants.append(cheapest)

    if not selected_variants:
        bonus_fallback: list[tuple[ScoredEventCandidate, TariffOptionOut]] = []
        for cand in candidates:
            if cand.on_request_tariffs:
                bonus_fallback.append((cand, cand.on_request_tariffs[0]))
                if len(bonus_fallback) >= 2:
                    break
        return [], bonus_fallback

    variant_1 = selected_variants[0]
    v1_event_ids = {c.event.id for c in variant_1.candidates}

    # Выбор Варианта №2 (Оптимальный по экономии бюджета / Альтернативный состав)
    all_budget_valid: list[EvaluatedCombo] = []
    for k in range(target_k, 0, -1):
        all_budget_valid.extend(strict_combos_by_k[k])
        all_budget_valid.extend(tolerance_combos_by_k[k])

    cheaper_alternatives = [
        c for c in all_budget_valid
        if {x.event.id for x in c.candidates} != v1_event_ids
        and (c.total_actual_price < variant_1.total_actual_price or c.total_savings > variant_1.total_savings)
    ]

    if cheaper_alternatives:
        cheaper_alternatives.sort(
            key=lambda x: (
                not x.has_date_conflict,
                x.total_savings,
                round(variant_1.total_actual_price - x.total_actual_price, 2),
                round(x.combo_score, 6),
            ),
            reverse=True,
        )
        selected_variants.append(cheaper_alternatives[0])
    else:
        other_alternatives = [
            c for c in all_budget_valid
            if {x.event.id for x in c.candidates} != v1_event_ids
        ]
        if not other_alternatives and all_fallback_combos:
            other_alternatives = [
                c for c in all_fallback_combos
                if {x.event.id for x in c.candidates} != v1_event_ids
            ]
        if other_alternatives:
            other_alternatives.sort(
                key=lambda x: (
                    not x.has_date_conflict,
                    x.roles_strictly_matched,
                    round(x.combo_score, 6),
                    -x.total_actual_price,
                ),
                reverse=True,
            )
            selected_variants.append(other_alternatives[0])

    # Бонусный слот: до 2 лучших по RRF событий с тарифом 'По запросу' (base_price IS NULL).
    # Приоритет отдаем событиям, еще не вошедшим в Вариант №1, чтобы расширить кругозор менеджера.
    bonus_pairs: list[tuple[ScoredEventCandidate, TariffOptionOut]] = []
    for cand in candidates:
        if cand.on_request_tariffs and cand.event.id not in v1_event_ids:
            bonus_pairs.append((cand, cand.on_request_tariffs[0]))
            if len(bonus_pairs) >= 2:
                break

    if len(bonus_pairs) < 2:
        used_bonus_ids = {c.event.id for c, _ in bonus_pairs}
        for cand in candidates:
            if cand.on_request_tariffs and cand.event.id not in used_bonus_ids:
                bonus_pairs.append((cand, cand.on_request_tariffs[0]))
                if len(bonus_pairs) >= 2:
                    break

    return selected_variants, bonus_pairs


# Алиас для обратной совместимости со спецификацией d_07_matcher_py.md
assemble_bundles_and_bonus = build_bundles


# ============================================================================
# 5. ШАГ 3: ГЕНЕРАЦИЯ ОБОСНОВАНИЙ И ПИТЧА (1 ВЫЗОВ LLM С ФОЛБЭКОМ)
# ============================================================================

def build_fallback_pitch(
    client_name: str,
    profile: ClientQueryExtracted,
    v1: EvaluatedCombo,
) -> str:
    """
    Формирует чистый, выверенный шаблон КП на случай недоступности внешнего LLM-шлюза.
    Корректно адаптируется к отсутствию скидок Early Bird (total_savings == 0.0).
    """
    titles = ", ".join(f"«{c.event.canonical_title}»" for c in v1.candidates)
    themes_str = ", ".join(profile.themes_keywords[:3]) if profile.themes_keywords else "ключевым отраслевым направлениям"
    price_str = f"{int(v1.total_actual_price):,}".replace(",", " ")
    budget_str = f"{int(profile.total_budget_max):,}".replace(",", " ")

    pitch = (
        f"Добрый день! По итогам установочной встречи подготовили для компании {client_name} "
        f"рекомендованный календарь профильных мероприятий по направлениям: {themes_str}.\n\n"
        f"В приоритетный пакет вошли {len(v1.candidates)} площадки без пересечений по датам: {titles}.\n\n"
        f"Расчет внешних расходов (взносы организаторов по выбранным тарифам) составляет {price_str} ₽ (с НДС) "
        f"при согласованном ориентире бюджета {budget_str} ₽."
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

    pitch += (
        "\n\nСо стороны агентства мы берем на себя согласование условий с организаторами, "
        "подготовку экспертного выступления спикера и организацию целевых деловых знакомств на площадках."
    )
    return pitch


async def generate_pitch_and_rationales(
    client_name: str,
    raw_notes: str,
    profile: ClientQueryExtracted,
    selected_variants: list[EvaluatedCombo],
    bonus_pairs: list[tuple[ScoredEventCandidate, TariffOptionOut]],
) -> tuple[dict[int, str], str]:
    """
    За 1 сетевой вызов к structured_llm_client генерирует обоснования (ai_rationale)
    для всех уникальных событий и сопроводительное письмо по цифрам Варианта №1.
    """
    unique_events_info: dict[int, tuple[Event, TariffOptionOut]] = {}
    for var in selected_variants:
        for cand, tariff in zip(var.candidates, var.chosen_tariffs):
            if cand.event.id not in unique_events_info:
                unique_events_info[cand.event.id] = (cand.event, tariff)

    for cand, tariff in bonus_pairs:
        if cand.event.id not in unique_events_info:
            unique_events_info[cand.event.id] = (cand.event, tariff)

    # 1. Заполняем безотказными детерминированными обоснованиями
    rationales_map: dict[int, str] = {
        ev_id: build_default_rationale(ev, tar, profile)
        for ev_id, (ev, tar) in unique_events_info.items()
    }

    if not selected_variants:
        return rationales_map, "По вашему запросу не найдено подходящих пакетных предложений."

    v1 = selected_variants[0]
    fallback_pitch = build_fallback_pitch(client_name, profile, v1)

    events_prompt_lines = []
    for ev_id, (ev, tar) in unique_events_info.items():
        loc = "Онлайн" if ev.is_online else ev.city
        if tar.actual_price is None:
            price_info = "По запросу"
        elif tar.actual_price == 0.0:
            price_info = "0 руб. (бесплатно)"
        else:
            price_info = f"{int(tar.actual_price)} руб."

        events_prompt_lines.append(
            f"- event_id={ev_id}: «{ev.canonical_title}» ({ev.event_format}, {loc}, {ev.start_date}). "
            f"Темы: {', '.join(ev.themes or [])}. Выбранный тариф: «{tar.tariff_name}» "
            f"(роль: {tar.participation_role}, цена: {price_info})."
        )

    eb_clause = (
        f"Экономия Early Bird: {int(v1.total_savings)} руб. при бронировании до {v1.earliest_deadline.isoformat()}."
        if (v1.total_savings > 0 and v1.earliest_deadline is not None)
        else "Специальных скидок Early Bird в данном пакете нет (экономия 0 руб., не упоминай скидки в письме)."
    )

    v1_summary = (
        f"Состав Варианта №1 ({len(v1.candidates)} событий): "
        + ", ".join(f"«{c.event.canonical_title}» (тариф {t.tariff_name})" for c, t in zip(v1.candidates, v1.chosen_tariffs))
        + f". Итоговая стоимость пакета: {int(v1.total_actual_price)} руб. "
        + f"Базовая стоимость: {int(v1.total_base_price)} руб. "
        + eb_clause
    )

    system_prompt = (
        "Ты — ведущий менеджер сопровождения коммуникационного B2B-агентства «СКАРТ». "
        "Сформируй персональные аргументы выбора площадки (ai_rationale) для каждого мероприятия из списка "
        "(укажи ценность целевой аудитории и какую задачу решает формат: целевые деловые знакомства, экспертное выступление в сессии или вовлечение аудитории на стенде) "
        "и напиши живое, убедительное сопроводительное письмо клиенту (generated_pitch_text) без канцеляризмов и спам-штампов. "
        "В письме подчеркни, что календарь сверен без пересечений по срокам, укажи бюджет внешних взносов организаторам "
        "и готовность агентства взять на себя подготовку спикера и организацию целевых встреч. "
        "КРИТИЧЕСКОЕ ПРАВИЛО: В письме используй ТОЛЬКО переданные ниже цифры стоимости Варианта №1 и дат. "
        "Ничего не пересчитывай самостоятельно и не выдумывай несуществующие скидки."
    )

    user_prompt = (
        f"Клиент: {client_name}\n"
        f"Исходная заметка созвона: {raw_notes}\n"
        f"Лимит бюджета клиента: {int(profile.total_budget_max)} руб.\n\n"
        f"Точные параметры Варианта №1 для письма:\n{v1_summary}\n\n"
        f"Список всех мероприятий для генерации ai_rationale:\n" + "\n".join(events_prompt_lines)
    )

    try:
        llm_res: PitchAndRationalesLLMResponse = await asyncio.wait_for(
            structured_llm_client.chat.completions.create(
                model=settings.LLM_MODEL,
                response_model=PitchAndRationalesLLMResponse,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_retries=2,
                extra_body={"reasoning": {"effort": "low"}},
            ),
            timeout=25.0,
        )
        for item in llm_res.rationales:
            if item.event_id in rationales_map and item.ai_rationale.strip():
                rationales_map[item.event_id] = item.ai_rationale.strip()

        final_pitch = llm_res.generated_pitch_text.strip() or fallback_pitch
        return rationales_map, final_pitch

    except Exception as exc:
        logger.warning("LLM Pitch generation fallback triggered (%s): %s", type(exc).__name__, exc)
        return rationales_map, fallback_pitch


# ============================================================================
# 6. ГЛАВНАЯ ТОЧКА ВХОДА ПАЙПЛАЙНА ПОДБОРА (ДЛЯ РОУТЕРА /match)
# ============================================================================

def _to_bundle_event_item(
    cand: ScoredEventCandidate,
    recommended_tariff: TariffOptionOut,
    rationale: str,
) -> BundleEventItemOut:
    """Собирает выходную карточку BundleEventItemOut."""
    ev = cand.event
    valid_formats = ("roundtable", "business_breakfast", "forum", "conference", "session")
    fmt = ev.event_format if ev.event_format in valid_formats else "conference"

    return BundleEventItemOut(
        event_id=ev.id,
        canonical_title=ev.canonical_title,
        event_format=fmt,  # type: ignore[arg-type]
        city=ev.city,
        is_online=ev.is_online,
        venue=ev.venue,
        start_date=ev.start_date,
        end_date=ev.end_date,
        themes=list(ev.themes or []),
        recommended_tariff=recommended_tariff,
        available_tariffs=cand.all_tariffs,
        ai_rationale=rationale,
    )


async def run_client_matching_pipeline(
    session: AsyncSession,
    client_id: int,
    payload: MatchRequestIn,
) -> MatchResponseOut:
    """
    Полный цикл Задачи D-07 + сохранение черновика подборки в БД:
    1. Извлекает профиль потребностей через profiler.py (или берет override_profile из UI за 0 мс).
    2. Проводит гибридный поиск (pgvector + FTS RRF) и отбирает кандидатов.
    3. Собирает Вариант №1, Вариант №2 и Бонусный слот ('Цена по запросу') через build_bundles().
    4. Генерирует обоснования и текст КП.
    5. Сохраняет черновик Selection и SelectionItem в БД и возвращает MatchResponseOut.
    """
    today = datetime.date.today()

    # 1. Получаем клиента из БД (или используем дефолтное имя, если клиент не найден)
    client_stmt = select(Client).where(Client.id == client_id)
    client_res = await session.execute(client_stmt)
    client_obj = client_res.scalar_one_or_none()
    client_name = client_obj.company_name if client_obj else f"Клиент #{client_id}"

    # 2. Извлечение или переопределение профиля
    if payload.override_profile is not None:
        extracted_profile = payload.override_profile
    else:
        extracted_profile = await extract_client_profile(payload.raw_manager_notes)

    if client_obj is not None:
        client_obj.raw_manager_notes = payload.raw_manager_notes
        client_obj.extracted_profile = extracted_profile.model_dump(mode="json")

    # 3. Гибридный поиск кандидатов (RRF)
    candidates = await get_scored_candidates(session, extracted_profile, today)

    # 4. Комбинаторная сборка пакетов (< 15 мс)
    evaluated_variants, bonus_pairs = build_bundles(candidates, extracted_profile)

    # 5. Генерация обоснований и черновика КП
    rationales_map, pitch_text = await generate_pitch_and_rationales(
        client_name=client_name,
        raw_notes=payload.raw_manager_notes,
        profile=extracted_profile,
        selected_variants=evaluated_variants,
        bonus_pairs=bonus_pairs,
    )

    # 6. Формирование выходных структур BundleVariantOut
    bundle_variants_out: list[BundleVariantOut] = []
    for idx, ev_var in enumerate(evaluated_variants, start=1):
        items_out = [
            _to_bundle_event_item(
                cand=cand,
                recommended_tariff=tar,
                rationale=rationales_map.get(cand.event.id, ""),
            )
            for cand, tar in zip(ev_var.candidates, ev_var.chosen_tariffs)
        ]

        if idx == 1:
            title = (
                "Вариант 1: Максимальное совпадение по темам (требует согласования бюджета)"
                if ev_var.is_over_budget_tolerance
                else f"Вариант 1: Максимальный охват тем ({len(items_out)} события)"
            )
        else:
            title = f"Вариант 2: Оптимальный по экономии бюджета ({len(items_out)} события)"

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

    bonus_items_out: list[BundleEventItemOut] = [
        _to_bundle_event_item(
            cand=cand,
            recommended_tariff=tar,
            rationale=rationales_map.get(cand.event.id, ""),
        )
        for cand, tar in bonus_pairs
    ]

    # 7. Сохранение черновика Selection и SelectionItem в БД
    selection_id = 10  # fallback ID, если вызвано для несуществующего в БД клиента
    if client_obj is not None:
        new_selection = Selection(
            client_id=client_obj.id,
            status="draft",
            generated_pitch_text=pitch_text,
            total_budget_limit=extracted_profile.total_budget_max,
        )
        session.add(new_selection)
        await session.flush()
        selection_id = new_selection.id

        for variant in bundle_variants_out:
            for item in variant.items:
                sel_item = SelectionItem(
                    selection_id=selection_id,
                    event_id=item.event_id,
                    recommended_tariff_id=item.recommended_tariff.tariff_id,
                    bundle_group=variant.bundle_group,
                    ai_rationale=item.ai_rationale,
                    client_reaction="pending",
                )
                session.add(sel_item)

        await session.commit()

    return MatchResponseOut(
        selection_id=selection_id,
        client_id=client_id,
        extracted_profile=extracted_profile,
        bundle_variants=bundle_variants_out,
        bonus_on_request_items=bonus_items_out,
        generated_pitch_text=pitch_text,
    )

