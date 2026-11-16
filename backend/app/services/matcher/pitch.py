import asyncio
import logging
from typing import TypeVar

import httpx
from instructor.core import InstructorRetryException
from openai import APIError
from pydantic import BaseModel, Field, ValidationError

from app.models.models import Event
from app.schemas.manager import ClientQueryExtracted, TariffOptionOut
from app.services.matcher.types import EvaluatedCombo, ScoredEventCandidate

logger = logging.getLogger(__name__)

_LLMResponseT = TypeVar("_LLMResponseT", bound=BaseModel)


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


class PitchOnlyLLMResponse(BaseModel):
    generated_pitch_text: str = Field(
        ...,
        description=(
            "Живое, персонализированное сопроводительное письмо клиенту от лица менеджера без канцеляризмов и спам-штампов. "
            "Используй ТОЛЬКО переданные точные цифры общей стоимости, базовой стоимости, экономии Early Bird и дат."
        ),
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


def _format_rub_int(amount: float) -> str:
    """Форматирует целую сумму в рублях с пробелами-разделителями разрядов."""
    return f"{int(amount):,}".replace(",", " ")


def build_fallback_pitch(
    client_name: str,
    profile: ClientQueryExtracted,
    v1: EvaluatedCombo,
    *,
    has_on_request: bool = False,
) -> str:
    """
    Формирует живой, естественный шаблон КП на случай недоступности внешнего LLM-шлюза.
    Корректно адаптируется к составу ролей, позициям «По запросу», конфликтам дат и отсутствию Early Bird.
    """
    titles = ", ".join(f"«{c.event.canonical_title}»" for c in v1.candidates)
    clean_themes = [t.strip() for t in profile.themes_keywords[:3] if t.strip()]
    themes_clause = (
        f"по направлениям: {', '.join(clean_themes)}"
        if clean_themes
        else "по ключевым отраслевым направлениям"
    )
    price_str = _format_rub_int(v1.total_actual_price)
    budget_str = _format_rub_int(profile.total_budget_max)
    budget_clause = (
        f" при ориентире бюджета {budget_str} ₽"
        if not getattr(profile, "budget_is_assumed", False)
        else ""
    )

    n_ev = len(v1.candidates)
    conflict_note = ""
    if v1.has_date_conflict:
        date_phrase = ""
        conflict_note = (
            " Обратите внимание: даты части очных площадок пересекаются, "
            "поэтому при подтверждении поможем гибко распределить участие команды."
        )
    else:
        date_phrase = " без пересечений по датам"

    if n_ev == 1:
        bundle_lead = f"В подборку вошла 1 профильная площадка: {titles}."
    elif 2 <= n_ev <= 4:
        bundle_lead = f"В подборку вошли {n_ev} площадки{date_phrase}: {titles}.{conflict_note}"
    else:
        bundle_lead = f"В подборку вошли {n_ev} площадок{date_phrase}: {titles}.{conflict_note}"

    if has_on_request and v1.total_actual_price <= 0:
        price_sentence = "Стоимость участия по выбранным позициям уточняется по запросу у организаторов."
    else:
        on_req_suffix = " (плюс позиции со стоимостью по запросу)" if has_on_request else ""
        price_sentence = (
            f"Стоимость участия по выбранным тарифам составит {price_str} ₽ (с НДС)"
            f"{on_req_suffix}{budget_clause}."
        )

    pitch = (
        f"Добрый день! По итогам нашего разговора подготовили для компании {client_name} "
        f"подборку профильных мероприятий {themes_clause}.\n\n"
        f"{bundle_lead}\n\n"
        f"{price_sentence}"
    )

    if v1.total_savings > 0 and v1.earliest_deadline is not None:
        base_str = _format_rub_int(v1.total_base_price)
        savings_str = _format_rub_int(v1.total_savings)
        dl_str = v1.earliest_deadline.strftime("%d.%m.%Y")
        pitch += (
            f" Если зафиксируем участие до {dl_str}, сработают условия Early Bird "
            f"и партнёрские преференции — прямая экономия составит {savings_str} ₽ "
            f"(базовая стоимость без скидки — {base_str} ₽)."
        )

    if v1.matched_speaker_count > 0:
        pitch += (
            "\n\nМы возьмём на себя переговоры с организаторами, подготовку выступления спикера "
            "и организацию целевых деловых знакомств на площадках."
        )
    else:
        pitch += (
            "\n\nМы возьмём на себя переговоры с организаторами, аккредитацию участников "
            "и организацию целевых деловых знакомств на площадках."
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


def _build_common_pitch_clauses(
    profile: ClientQueryExtracted,
    combo: EvaluatedCombo,
    *,
    has_on_request: bool = False,
) -> tuple[str, str, str, str, str]:
    """Собирает переиспользуемые фрагменты промпта (Early Bird, роль агентства, сводка пакета, бюджет)."""
    eb_clause = (
        f"Экономия Early Bird: {int(combo.total_savings)} руб. при бронировании до {combo.earliest_deadline.isoformat()}."
        if (combo.total_savings > 0 and combo.earliest_deadline is not None)
        else "Специальных скидок Early Bird в данном пакете нет (экономия 0 руб., не упоминай скидки в письме)."
    )
    agency_role_clause = (
        "подготовку спикера и организацию целевых встреч"
        if combo.matched_speaker_count > 0
        else "согласование участия с организаторами и организацию целевых встреч"
    )
    on_req_clause = (
        " В составе есть позиции со статусом «По запросу» — их стоимость уточняется отдельно у организаторов."
        if has_on_request
        else ""
    )
    combo_summary = (
        f"Состав пакета ({len(combo.candidates)} событий): "
        + ", ".join(
            f"«{c.event.canonical_title}» (тариф {t.tariff_name})"
            for c, t in zip(combo.candidates, combo.chosen_tariffs)
        )
        + f". Итоговая стоимость пакета: {int(combo.total_actual_price)} руб. "
        + f"Базовая стоимость: {int(combo.total_base_price)} руб. "
        + eb_clause
        + on_req_clause
    )
    budget_line = (
        f"Лимит бюджета клиента: {int(profile.total_budget_max)} руб.\n\n"
        if not getattr(profile, "budget_is_assumed", False)
        else "Клиент не зафиксировал жесткий бюджет (не упоминай в письме формулировки 'согласованный бюджет').\n\n"
    )
    date_clause = (
        "Внимание: среди выбранных очных площадок есть пересечение по датам (менеджер включил их осознанно) — "
        "НЕ пиши, что календарь без пересечений; аккуратно отметь необходимость распределить команду или согласовать график."
        if combo.has_date_conflict
        else "Календарь сверен без пересечений по датам."
    )
    return agency_role_clause, combo_summary, budget_line, date_clause, eb_clause


def _build_pitch_prompts(
    client_name: str,
    raw_notes: str,
    profile: ClientQueryExtracted,
    v1: EvaluatedCombo,
    unique_events_info: dict[int, tuple[Event, TariffOptionOut]],
) -> tuple[str, str]:
    """Формирует системный и пользовательский промпты для генерации КП и обоснований."""
    events_lines = [_format_event_line_for_pitch(ev_id, ev, tar) for ev_id, (ev, tar) in unique_events_info.items()]
    agency_role_clause, v1_summary, budget_line, date_clause, _ = _build_common_pitch_clauses(
        profile, v1, has_on_request=False
    )
    system_prompt = (
        "Ты — ведущий менеджер сопровождения делового B2B-агентства. "
        "Сформируй персональные аргументы выбора площадки (ai_rationale) для каждого мероприятия из списка "
        "(укажи ценность целевой аудитории и какую задачу решает формат: целевые деловые знакомства, экспертное выступление в сессии или вовлечение аудитории на стенде) "
        "и напиши живое, убедительное сопроводительное письмо клиенту (generated_pitch_text) без канцеляризмов и спам-штампов. "
        f"В письме учти календарь ({date_clause}), укажи стоимость участия по выбранным тарифам "
        f"и готовность агентства взять на себя {agency_role_clause}. "
        "КРИТИЧЕСКОЕ ПРАВИЛО: В письме используй ТОЛЬКО переданные ниже цифры стоимости Варианта №1 и дат. "
        "Ничего не пересчитывай самостоятельно и не выдумывай несуществующие скидки."
    )
    user_prompt = (
        f"Клиент: {client_name}\nИсходная заметка созвона: {raw_notes}\n"
        f"{budget_line}"
        f"Точные параметры Варианта №1 для письма:\n{v1_summary}\n\n"
        "Список всех мероприятий для генерации ai_rationale:\n" + "\n".join(events_lines)
    )
    return system_prompt, user_prompt


def _build_live_pitch_prompts(
    client_name: str,
    raw_notes: str,
    profile: ClientQueryExtracted,
    combo: EvaluatedCombo,
    *,
    has_on_request: bool = False,
) -> tuple[str, str]:
    """Формирует системный и пользовательский промпты для живой перегенерации только текста письма КП."""
    events_lines = [
        _format_event_line_for_pitch(cand.event.id, cand.event, tar)
        for cand, tar in zip(combo.candidates, combo.chosen_tariffs)
    ]
    agency_role_clause, combo_summary, budget_line, date_clause, _ = _build_common_pitch_clauses(
        profile, combo, has_on_request=has_on_request
    )
    system_prompt = (
        "Ты — ведущий менеджер сопровождения делового B2B-агентства. "
        "Напиши тёплое, живое, лаконичное деловое сопроводительное письмо клиенту (generated_pitch_text) "
        "без канцеляризмов (избегай фраз вроде 'Расчет внешних расходов') и без спам-штампов. "
        f"Учти статус календаря: {date_clause} "
        f"Покажи ценность выбранных площадок, укажи стоимость участия и готовность агентства взять на себя {agency_role_clause}. "
        "Если в составе есть позиции «По запросу», явно отметь, что их стоимость уточняется отдельно у организаторов. "
        "КРИТИЧЕСКОЕ ПРАВИЛО: Используй ТОЛЬКО переданные ниже точные цифры стоимости, экономии и дат. "
        "Ничего не пересчитывай самостоятельно и не выдумывай несуществующие скидки."
    )
    user_prompt = (
        f"Клиент: {client_name}\nИсходная заметка созвона: {raw_notes or 'Не указана'}\n"
        f"{budget_line}"
        f"Точные параметры утвержденного менеджером состава:\n{combo_summary}\n\n"
        "Выбранные мероприятия и тарифы:\n" + "\n".join(events_lines)
    )
    return system_prompt, user_prompt


async def _request_structured_pitch(
    system_prompt: str,
    user_prompt: str,
    response_model: type[_LLMResponseT],
    *,
    timeout_sec: float = 25.0,
) -> _LLMResponseT | None:
    """Выполняет защищенный LLM_SEMAPHORE вызов к LLM для структурированной генерации КП."""
    import app.services.matcher as matcher_pkg

    try:
        async with matcher_pkg.LLM_SEMAPHORE:
            res: _LLMResponseT = await asyncio.wait_for(
                matcher_pkg.structured_llm_client.chat.completions.create(
                    model=matcher_pkg.settings.LLM_MODEL,
                    response_model=response_model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    max_retries=1,
                ),
                timeout=timeout_sec,
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


async def _request_pitch_from_llm(
    system_prompt: str,
    user_prompt: str,
) -> PitchAndRationalesLLMResponse | None:
    """Выполняет защищенный LLM_SEMAPHORE вызов к LLM для генерации КП и обоснований."""
    return await _request_structured_pitch(
        system_prompt,
        user_prompt,
        PitchAndRationalesLLMResponse,
        timeout_sec=25.0,
    )


async def generate_live_pitch_text(
    client_name: str,
    raw_notes: str,
    profile: ClientQueryExtracted,
    combo: EvaluatedCombo,
    *,
    has_on_request: bool = False,
) -> tuple[str, bool]:
    """
    Генерирует живое сопроводительное письмо КП по актуальному составу (без пересчёта ai_rationale).
    При отсутствии ключа или сбое/таймауте LLM безопасно откатывается на build_fallback_pitch.
    Возвращает кортеж (pitch_text, used_llm).
    """
    import app.services.matcher as matcher_pkg

    fallback_pitch = build_fallback_pitch(
        client_name,
        profile,
        combo,
        has_on_request=has_on_request,
    )
    if not matcher_pkg.settings.LLM_API_KEY:
        return fallback_pitch, False

    system_prompt, user_prompt = _build_live_pitch_prompts(
        client_name,
        raw_notes,
        profile,
        combo,
        has_on_request=has_on_request,
    )
    llm_res = await _request_structured_pitch(
        system_prompt,
        user_prompt,
        PitchOnlyLLMResponse,
        timeout_sec=20.0,
    )
    if llm_res is None or not llm_res.generated_pitch_text.strip():
        return fallback_pitch, False
    return llm_res.generated_pitch_text.strip(), True


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
    import app.services.matcher as matcher_pkg

    unique_events_info = _collect_unique_events_for_pitch(selected_variants, bonus_pairs)
    rationales_map: dict[int, str] = {
        ev_id: build_default_rationale(ev, tar, profile)
        for ev_id, (ev, tar) in unique_events_info.items()
    }

    if not selected_variants:
        city_clause = f" (город: {', '.join(profile.cities)})" if profile.cities else ""
        if bonus_pairs:
            bonus_titles = ", ".join(f"«{c.event.canonical_title}»" for c, _ in bonus_pairs)
            return (
                rationales_map,
                f"По вашему запросу{city_clause} не найдено площадок с фиксированным прайсом, однако подобраны релевантные профильные мероприятия с тарифами «По запросу»: {bonus_titles}. Включите подходящие площадки из блока «Дополнительные возможности» для согласования с клиентом.",
            )
        return (
            rationales_map,
            f"По вашему запросу{city_clause} не найдено подходящих пакетных предложений в базе знаний агентства. Рекомендуется скорректировать параметры отбора или добавить новые площадки.",
        )

    v1 = selected_variants[0]
    fallback_pitch = build_fallback_pitch(client_name, profile, v1)
    if not matcher_pkg.settings.LLM_API_KEY:
        return rationales_map, fallback_pitch

    system_prompt, user_prompt = _build_pitch_prompts(
        client_name, raw_notes, profile, v1, unique_events_info
    )
    llm_res = await _request_pitch_from_llm(system_prompt, user_prompt)
    return _merge_llm_rationales(rationales_map, llm_res, fallback_pitch)
