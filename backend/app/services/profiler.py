import asyncio
import datetime
from app.services.ai_client import structured_llm_client
from app.schemas.manager import ClientQueryExtracted
from app.core.constants import normalize_city
from app.core.config import settings

async def extract_client_profile(raw_notes: str) -> ClientQueryExtracted:

    today = datetime.date.today()
    current_date_str = today.isoformat()
    day_of_week = today.strftime("%A")

    system_prompt = f"""Ты — экспертный ИИ-ассистент отдела сопровождения ивент-агентства «СКАРТ».
Твоя задача — извлечь строго структурированные параметры запроса клиента из свободного конспекта созвона менеджера.

ВАЖНЫЙ КОНТЕКСТ: Сегодняшняя дата: {current_date_str} ({day_of_week}). 
Все относительные даты (например, "в следующем месяце", "в конце осени", "на ноябрь-декабрь") ты должен перевести в абсолютные даты формата YYYY-MM-DD на основе сегодняшней даты.

Правила извлечения:
1. `cities`: Список географических городов в именительном падеже (например, ["Москва", "Санкт-Петербург"]). Если указано "только онлайн" или город не важен, верни пустой список []. Слово "онлайн" городом не является!
2. `include_online`: True по умолчанию, либо если клиент не против онлайн-формата или сам его просит (вебинары, трансляции). False ТОЛЬКО если клиент явно требует исключительно очное присутствие ("только очно", "строго офлайн", "без онлайна").
3. `date_from` и `date_to`: Период поиска (YYYY-MM-DD).
4. `total_budget_max`: Общий бюджет на ВСЮ серию (только число). Если "полтора миллиона" -> 1500000. Если "400 тыс" -> 400000.
5. `target_events_count`: Сколько всего мероприятий нужно (по умолчанию 3, если не сказано иное).
6. `preferred_formats`: Массив из списка ["roundtable", "business_breakfast", "forum", "conference", "session"]. Если не указано — пустой массив.
7. `required_roles`: Массив из ["delegate", "speaker", "sponsor"]. 
8. `min_speaker_events`: Если сказано "хотя бы на одном выступить спикером" -> 1. Если "на всех делегатами" -> 0.
9. `themes_keywords`: Отраслевые термины и теги (КРТ, ИЖС, урбанистика, девелопмент, BIM и т.д.).
10. `semantic_search_query`: Развернутое описание запроса на русском языке для векторного поиска.
"""

    extracted_data = await asyncio.wait_for(
        structured_llm_client.chat.completions.create(
            model=settings.LLM_MODEL,
            response_model=ClientQueryExtracted,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Заметка менеджера:\n{raw_notes}"}
            ],
            max_retries=2,
        ),
        timeout=20.0,
    )

    if extracted_data.cities:
        normalized_cities = []
        for city in extracted_data.cities:
            norm = normalize_city(city)
            if not norm:
                continue
            if norm == "Онлайн":
                extracted_data.include_online = True
                continue
            if norm not in normalized_cities:
                normalized_cities.append(norm)
        extracted_data.cities = normalized_cities

    return extracted_data