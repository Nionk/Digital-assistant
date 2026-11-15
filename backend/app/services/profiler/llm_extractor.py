import asyncio
import datetime
import logging
import re

import httpx
from instructor.core import InstructorError
from openai import APIError
from pydantic import ValidationError

from app.core.constants import is_online_format, normalize_city
from app.schemas.manager import ClientQueryExtracted

logger = logging.getLogger(__name__)


def _build_profiler_system_prompt(today: datetime.date) -> str:
    """Формирует системный промпт NER-профилировщика с динамической привязкой к текущей дате."""
    current_date_str = today.isoformat()
    day_of_week = today.strftime("%A")
    next_week_str = (today + datetime.timedelta(days=7)).isoformat()
    return f"""Ты — экспертный ИИ-ассистент коммуникационного B2B-агентства по подбору деловых мероприятий для корпоративных клиентов любых отраслей (IT, FinTech, Healthcare, Retail, FMCG, Строительство, Промышленность, Логистика и др.).
Твоя задача — извлечь строго структурированные параметры запроса клиента из конспекта встречи или созвона менеджера.

ВАЖНЫЙ КОНТЕКСТ: Сегодняшняя дата: {current_date_str} ({day_of_week}).
Все относительные даты (например, "в следующем месяце", "не ранее чем через неделю", "на ноябрь-декабрь", "начало следующего года", "в первом квартале") ты должен перевести в абсолютные даты формата YYYY-MM-DD на основе сегодняшней даты ({current_date_str}).

Правила извлечения:
1. `cities`: Список географических городов в именительном падеже (например, ["Москва", "Санкт-Петербург"]).
   - Если клиент упоминал город, но затем явно отказался от него ("думали про Сочи, но зарубили / едем в Казань") — исключи отвергнутые города!
   - Если указано "только онлайн" или город не важен, верни пустой список []. Слово "онлайн" городом не является!
2. `include_online`: True по умолчанию! Ставь False ИСКЛЮЧИТЕЛЬНО если клиент прямо и однозначно требует строго очное участие ("только очно", "строго офлайн", "без онлайна", "без вебинаров", "только личные встречи"). Простое указание города ("2 встречи в Москве", "в Казани", "прилетим в Питер") НЕ запрещает онлайн — оставляй True!
3. `date_from` и `date_to`: Период поиска (YYYY-MM-DD). Если сказано "не ранее чем через неделю от момента сейчас", то `date_from` = {next_week_str}.
4. `total_budget_max`: Общий верхний потолок бюджета на ВСЮ серию мероприятий (число > 0). Распознавай любые разговорные числительные ("1млн" -> 1000000.0, "полтора миллиона" -> 1500000.0, "350к" -> 350000.0, "четыре миллиона" -> 4000000.0, "три с половиной миллиона" -> 3500000.0, "от 300 до 500 тыс" -> 500000.0). Если бюджет не назван клиентом вообще, укажи 1000000.0 и обязательно установи флаг budget_is_assumed=True. Если бюджет назван явно — budget_is_assumed=False.
5. `target_events_count`: Сколько всего мероприятий нужно в пакете (целое число от 1 до 10). Если названо конкретное число ("на 2 мероприятиях", "пару встреч") — укажи это число (2). Если число не названо вообще — ставь 3 по умолчанию.
6. `preferred_formats`: Массив из списка ["roundtable", "business_breakfast", "forum", "conference", "session"]. Если клиент отверг формат ("только не круглые столы"), обязательно исключи его.
7. `required_roles`: Массив из ["delegate", "speaker", "sponsor"]. Если клиент отказался от роли ("отказались от спонсорства"), не включай её.
8. `min_speaker_events`: Минимальное число мероприятий со слотом спикера (от 0 до 5). СТРОГОЕ ПРАВИЛО: Ставь число > 0 и добавляй "speaker" в required_roles ТОЛЬКО если клиент прямо запросил доклад, выступление со сцены или спикерский слот ("выступить", "доклад", "спикером"). Если клиент не просил выступать — ставь 0 и НЕ добавляй "speaker"! Не додумывай спикерство для стартапов, питч-сессий или директоров без их явного запроса.
9. `themes_keywords`: Отраслевые термины, технологический стек, продукты компании, целевая аудитория и ключевые теги для ЛЮБОЙ предметной области.
10. `semantic_search_query`: Развернутое содержательное описание бизнес-задачи, продукта и искомых площадок на русском языке для векторного поиска.
"""


def _normalize_profile_cities(extracted_data: ClientQueryExtracted) -> None:
    """Канонизирует список городов и отделяет маркеры онлайна от географических локаций."""
    normalized_cities: list[str] = []
    for city in extracted_data.cities:
        if is_online_format(city):
            extracted_data.include_online = True
            continue
        norm = normalize_city(city)
        if norm and norm not in normalized_cities:
            normalized_cities.append(norm)
    extracted_data.cities = normalized_cities


def _clamp_profile_date_from(
    extracted_data: ClientQueryExtracted,
    low_notes: str,
    today: datetime.date,
) -> None:
    """Корректирует нижнюю границу даты поиска относительно сегодняшнего дня или отступа в неделю."""
    if re.search(r"через\s+недел[юи]|не\s+ранее\s+чем\s+через\s+недел", low_notes):
        min_date = today + datetime.timedelta(days=7)
        extracted_data.date_from = max(extracted_data.date_from or min_date, min_date)
    elif extracted_data.date_from is not None and extracted_data.date_from < today:
        extracted_data.date_from = today


def _postprocess_extracted_profile(
    extracted_data: ClientQueryExtracted,
    raw_notes: str,
    today: datetime.date,
) -> ClientQueryExtracted:
    """Выполняет канонизацию городов и проверку границ дат и формата участия."""
    extracted_data.profile_source = "llm"
    if extracted_data.cities:
        _normalize_profile_cities(extracted_data)

    low_notes = (raw_notes or "").lower()
    _clamp_profile_date_from(extracted_data, low_notes, today)

    if (
        extracted_data.date_to is not None
        and extracted_data.date_from is not None
        and extracted_data.date_to < extracted_data.date_from
    ):
        logger.warning(
            "date_to (%s) < date_from (%s), сбрасываем date_to",
            extracted_data.date_to,
            extracted_data.date_from,
        )
        extracted_data.date_to = None

    if extracted_data.cities and "онлайн" not in low_notes:
        city_regex_parts = [re.escape(c.lower()) for c in extracted_data.cities]
        if re.search(rf"только\s+(?:в\s+)?(?:{'|'.join(city_regex_parts)})\b", low_notes):
            extracted_data.include_online = False

    return extracted_data


async def extract_client_profile(raw_notes: str) -> ClientQueryExtracted:
    """
    Извлечение структурированного профиля потребностей клиента из свободной заметки менеджера.
    Использует облачную LLM (Instructor MD_JSON) с контролем параллелизма (LLM_SEMAPHORE)
    и регламентным таймаутом 20.0 сек (DoD задачи D-06 в plan.md).
    При сбое сети или отсутствии API-ключа переключается на детерминированный универсальный парсер.
    """
    import app.services.profiler as profiler_pkg

    today = profiler_pkg.today_local()
    if not profiler_pkg.settings.LLM_API_KEY:
        logger.info("LLM_API_KEY не задан. Применяется универсальный детерминированный парсер.")
        return profiler_pkg.extract_profile_heuristic(raw_notes, today)

    system_prompt = _build_profiler_system_prompt(today)
    try:
        async with profiler_pkg.LLM_SEMAPHORE:
            extracted_data: ClientQueryExtracted = await asyncio.wait_for(
                profiler_pkg.structured_llm_client.chat.completions.create(
                    model=profiler_pkg.settings.LLM_MODEL,
                    response_model=ClientQueryExtracted,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": f"Заметка менеджера:\n{raw_notes}"},
                    ],
                    max_retries=1,
                ),
                timeout=20.0,
            )
    except (TimeoutError, APIError, httpx.HTTPError, InstructorError, ValidationError, ValueError) as exc:
        logger.warning(
            "Сбой вызова LLM-шлюза профилирования (%s: %s). Применяется универсальный парсер.",
            type(exc).__name__,
            exc,
            exc_info=True,
        )
        return profiler_pkg.extract_profile_heuristic(raw_notes, today)

    return _postprocess_extracted_profile(extracted_data, raw_notes, today)
