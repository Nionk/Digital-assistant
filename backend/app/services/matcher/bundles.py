import datetime
import itertools
from collections import defaultdict
from collections.abc import Sequence
from typing import cast

from app.models.models import EventTariff
from app.schemas.manager import ClientQueryExtracted, TariffOptionOut
from app.services.matcher.types import (
    EvaluatedCombo,
    ParticipationRole,
    ScoredEventCandidate,
    _normalize_participation_role,
)


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
