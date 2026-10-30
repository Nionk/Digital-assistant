import asyncio
import datetime
import logging
import re
from app.services.ai_client import structured_llm_client
from app.schemas.manager import ClientQueryExtracted
from app.core.constants import normalize_city
from app.core.config import settings

logger = logging.getLogger(__name__)

_CITY_PATTERNS: list[tuple[str, str]] = [
    (r"\bмоскв[а-яё]*\b|\bмск\b", "Москва"),
    (r"\bсанкт[\s\-]*петербург[а-яё]*\b|\bпетербург[а-яё]*\b|\bспб\b|\bпитер[а-яё]*\b", "Санкт-Петербург"),
    (r"\bекатеринбург[а-яё]*\b|\bекб\b", "Екатеринбург"),
    (r"\bказан[ьияейю][а-яё]*\b", "Казань"),
    (r"\bсочи\b", "Сочи"),
    (r"\bновосибирск[а-яё]*\b|\bнск\b", "Новосибирск"),
    (r"\bвладивосток[а-яё]*\b", "Владивосток"),
    (r"\bнижн[а-яё]+\s+новгород[а-яё]*\b|\bнн\b", "Нижний Новгород"),
    (r"\bкраснодар[а-яё]*\b", "Краснодар"),
]

_THEME_PATTERNS: list[tuple[str, str]] = [
    (r"\bкрт\b|комплексн[а-яё]+\s+развит[а-яё]+\s+территор", "КРТ"),
    (r"урбанист[а-яё]*|мастер[\s\-]*план[а-яё]*|градостроит[а-яё]*", "урбанистика"),
    (r"девелоп[а-яё]*|застройщ[а-яё]*", "девелопмент"),
    (r"строит[а-яё]*|стройк[а-яё]*", "строительство"),
    (r"стройматериал[а-яё]*|материал[а-яё]*|фасад[а-яё]*|кровл[а-яё]*", "строительные материалы"),
    (r"\bbim\b|бим|тим|цифров[а-яё]+\s+стройк", "BIM"),
    (r"архитектур[а-яё]*|проектиров[а-яё]*", "архитектура"),
    (r"инженерн[а-яё]*|вентиляц[а-яё]*|овк", "инженерные решения"),
    (r"жила?я\s+недвижим[а-яё]*|недвижим[а-яё]*|ижс", "жилая недвижимость"),
    (r"\besg\b|устойчив[а-яё]+\s+развит", "устойчивое развитие городов"),
    (r"инвестиц[а-яё]*|облигац[а-яё]*|финанс[а-яё]*", "инвестиции"),
    (r"искусственн[а-яё]+\s+интеллект|\bai\b|\bии\b|нейросет", "искусственный интеллект"),
    (r"операционн[а-яё]*|управлен[а-яё]*|персонал|hr\b", "управление"),
]


def extract_profile_heuristic(
    raw_notes: str,
    today: datetime.date | None = None,
) -> ClientQueryExtracted:
    """
    Детерминированный извлекатель параметров запроса из текста конспекта менеджера (0 мс).
    Используется как мгновенный страхующий фолбэк при таймауте или сетевом сбое внешнего LLM-шлюза,
    чтобы реальный запрос клиента никогда не подменялся чужими демо-данными.
    """
    today = today or datetime.date.today()
    text = raw_notes or ""
    low = text.lower()

    # 1. Города
    cities: list[str] = []
    for pattern, canonical in _CITY_PATTERNS:
        if re.search(pattern, low):
            if canonical not in cities:
                cities.append(canonical)

    # 2. Онлайн-формат
    strict_offline = bool(
        re.search(
            r"только\s+(в\s+)?(москв|мск|спб|питер|санкт|екатеринбург|казан|сочи|очно|офф?лайн)|без\s+онлайн|строго\s+очно|строго\s+офф?лайн",
            low,
        )
    )
    explicit_online = bool(re.search(r"онлайн|вебинар|трансляц", low))
    include_online = False if (strict_offline and not explicit_online) else True

    # 3. Бюджет (total_budget_max)
    budget = 400000.0
    if "полтора миллиона" in low or "полтора млн" in low:
        budget = 1500000.0
    else:
        m_mln = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:млн|миллион[а-яё]*)", low)
        m_tys = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:тыс[а-яё.]*|т\.?\s*р\.?|к\b)", low)
        if m_mln:
            budget = float(m_mln.group(1).replace(",", ".")) * 1_000_000.0
        elif m_tys:
            budget = float(m_tys.group(1).replace(",", ".")) * 1_000.0
        else:
            # Ищем явные суммы вида 400 000 или 1000000 (не путая с годами 2026/2027)
            raw_nums = re.findall(r"\b\d{1,3}(?:[\s\u00a0]\d{3})+\b|\b\d{5,8}\b", low)
            for rn in raw_nums:
                val = float(re.sub(r"[\s\u00a0]", "", rn))
                if val >= 10000:
                    budget = val
                    break

    # 4. Период дат (date_from, date_to)
    date_from = today
    date_to = today + datetime.timedelta(days=120)

    if re.search(r"через\s+недел[юи]|не\s+ранее\s+чем\s+через\s+недел", low):
        date_from = today + datetime.timedelta(days=7)
    elif "ноябр" in low and "2026" in low:
        date_from = max(today, datetime.date(2026, 11, 1))

    if re.search(r"начал[оеу]\s*2027|2027", low):
        date_to = datetime.date(2027, 3, 31)
    elif "декабр" in low:
        date_to = datetime.date(today.year, 12, 31)

    # 5. Количество мероприятий и спикерство
    target_count = 3
    m_better = re.search(r"лучше\s*(\d+)\s*(?:мероприят|площад|событ|форум)?", low)
    m_count = re.search(r"\b([1-5])\s*(?:небольш[а-яё]+\s+|профильн[а-яё]+\s+|ключев[а-яё]+\s+)?(?:мероприят|площад|событ|форум|встреч)", low)
    if m_better:
        target_count = max(1, min(5, int(m_better.group(1))))
    elif m_count:
        target_count = max(1, min(5, int(m_count.group(1))))
    elif "два мероприятия" in low or "две площадки" in low or "на обоих" in low:
        target_count = 2
    elif "одно мероприятие" in low or "одну площадку" in low:
        target_count = 1

    # 6. Роли участия и min_speaker_events
    roles: list[str] = []
    wants_speaker = bool(re.search(r"спик[а-яё]*|спискер[а-яё]*|выступ[а-яё]*|доклад[а-яё]*", low))
    wants_sponsor = bool(re.search(r"стенд[а-яё]*|спонсор[а-яё]*|партнерск[а-яё]*|партнёрск[а-яё]*|делов[а-яё]+\s+игр", low))
    wants_delegate = bool(re.search(r"делегат[а-яё]*|знакомств[а-яё]*|нетворкинг[а-яё]*|посетит[а-яё]*|встреч[а-яё]*", low))

    if wants_speaker:
        roles.append("speaker")
    if wants_sponsor:
        roles.append("sponsor")
    if wants_delegate or not roles:
        roles.append("delegate")

    min_speaker = 0
    if wants_speaker:
        if re.search(r"на\s+обоих|на\s+обеих|на\s+всех|везде\s+спик", low):
            min_speaker = target_count
        else:
            min_speaker = 1
        if min_speaker < target_count and "delegate" not in roles:
            roles.append("delegate")

    # 7. Предпочитаемые форматы
    formats: list[str] = []
    if re.search(r"кругл[а-яё]+\s+стол|камерн[а-яё]+|закрыт[а-яё]+", low):
        formats.append("roundtable")
    if re.search(r"завтрак[а-яё]*|камерн[а-яё]+|закрыт[а-яё]+", low):
        formats.append("business_breakfast")
    if re.search(r"форум[а-яё]*|выставк[а-яё]*|саммит[а-яё]*", low):
        formats.append("forum")
    if re.search(r"конференц[а-яё]*|конкурс[а-яё]*|преми[яию]", low):
        formats.append("conference")

    # 8. Темы и семантический запрос
    themes: list[str] = []
    for pattern, tag in _THEME_PATTERNS:
        if re.search(pattern, low) and tag not in themes:
            themes.append(tag)
    if not themes:
        themes = ["строительство", "девелопмент"]

    sem_parts = [*themes]
    if cities:
        sem_parts.extend(cities)
    if wants_speaker:
        sem_parts.append("выступление спикером в деловой программе")
    if wants_sponsor:
        sem_parts.append("экспозиция стенд партнерское участие")
    semantic_query = f"{' '.join(sem_parts)} {text.strip()}"[:350].strip()

    return ClientQueryExtracted(
        cities=cities,
        include_online=include_online,
        date_from=date_from,
        date_to=date_to,
        total_budget_max=budget,
        target_events_count=target_count,
        preferred_formats=formats,  # type: ignore[arg-type]
        required_roles=roles,  # type: ignore[arg-type]
        min_speaker_events=min_speaker,
        themes_keywords=themes,
        semantic_search_query=semantic_query,
    )


async def extract_client_profile(raw_notes: str) -> ClientQueryExtracted:
    today = datetime.date.today()
    current_date_str = today.isoformat()
    day_of_week = today.strftime("%A")

    system_prompt = f"""Ты — экспертный ИИ-ассистент коммуникационного B2B-агентства (подбор площадок и сопровождение участия для строительной отрасли: производителей, застройщиков, строительных компаний, архитектурных и проектных бюро).
Твоя задача — извлечь строго структурированные параметры запроса клиента из конспекта установочной встречи или созвона менеджера.

ВАЖНЫЙ КОНТЕКСТ: Сегодняшняя дата: {current_date_str} ({day_of_week}).
Все относительные даты (например, "в следующем месяце", "не ранее чем через неделю", "на ноябрь-декабрь", "начало 2027") ты должен перевести в абсолютные даты формата YYYY-MM-DD на основе сегодняшней даты ({current_date_str}).

Правила извлечения:
1. `cities`: Список географических городов в именительном падеже (например, ["Москва"]). Если сказано "ТОЛЬКО Москва" — верни строго ["Москва"] и `include_online: false`. Если указано "только онлайн" или город не важен, верни пустой список []. Слово "онлайн" городом не является!
2. `include_online`: True по умолчанию, либо если клиент не против онлайн-формата или сам его просит. False если клиент явно требует исключительно конкретный город ("ТОЛЬКО Москва") или очное присутствие ("только очно", "строго офлайн", "без онлайна").
3. `date_from` и `date_to`: Период поиска (YYYY-MM-DD). Если сказано "не ранее чем через неделю от момента сейчас", то `date_from` = {(today + datetime.timedelta(days=7)).isoformat()}.
4. `total_budget_max`: Общий бюджет на ВСЮ серию (только число). Если "1млн" -> 1000000. Если "полтора миллиона" -> 1500000. Если "400 тыс" -> 400000.
5. `target_events_count`: Сколько всего мероприятий нужно (по умолчанию 3, если не сказано иное; если сказано "лучше 2 мероприятия" -> 2).
6. `preferred_formats`: Массив из списка ["roundtable", "business_breakfast", "forum", "conference", "session"].
   - Если клиент упоминает "камерные встречи", "закрытые встречи", "узкий круг" -> включай "roundtable", "business_breakfast".
   - Если клиент упоминает "выставки", "крупные форумы", "отраслевые конкурсы", "премии" -> включай "forum", "conference".
   - Если формат не указан — верни пустой массив [].
7. `required_roles`: Массив из ["delegate", "speaker", "sponsor"].
   - Если нужны "целевые знакомства", "выход на ключевых игроков", "нетворкинг" -> "delegate".
   - Если нужно "экспертное выступление", "выступить спикером", "доклад в целевой сессии" -> "speaker".
   - Если нужны "стенд", "интерактивная программа на стенде", "деловая игра", "партнерский пакет" -> "sponsor".
8. `min_speaker_events`: Если сказано "хотя бы на одном выступить спикером" -> 1. Если сказано "на обоих спикером" (при 2 мероприятиях) -> 2. Если без доклада -> 0.
9. `themes_keywords`: Отраслевые термины, продукт компании, целевая аудитория и теги (строительство, КРТ, ИЖС, урбанистика, девелопмент, BIM, архитектура, производители стройматериалов, проектирование, конкурсы и т.д.).
10. `semantic_search_query`: Развернутое описание бизнес-задачи, продукта, целевой аудитории и искомых площадок на русском языке для векторного поиска.
"""

    heuristic_fallback = extract_profile_heuristic(raw_notes, today)

    try:
        extracted_data = await asyncio.wait_for(
            structured_llm_client.chat.completions.create(
                model=settings.LLM_MODEL,
                response_model=ClientQueryExtracted,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Заметка менеджера:\n{raw_notes}"},
                ],
                max_retries=1,
                extra_body={"reasoning": {"effort": "low"}},
            ),
            timeout=30.0,
        )
    except Exception as exc:
        logger.warning(
            "LLM profile extraction fallback triggered (%s: %s). Using deterministic heuristic parser.",
            type(exc).__name__,
            exc,
        )
        return heuristic_fallback

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

    # Страховка относительной даты: если клиент написал "не ранее чем через неделю", а LLM вернула начало года
    low_notes = (raw_notes or "").lower()
    if re.search(r"через\s+недел[юи]|не\s+ранее\s+чем\s+через\s+недел", low_notes):
        min_date_from = today + datetime.timedelta(days=7)
        if extracted_data.date_from is None or extracted_data.date_from < min_date_from:
            extracted_data.date_from = min_date_from
    elif extracted_data.date_from is not None and extracted_data.date_from < today:
        extracted_data.date_from = today

    # Страховка "ТОЛЬКО <Город>": отключаем онлайн, если онлайн не запрошен явно
    if re.search(
        r"только\s+(в\s+)?(москв|мск|спб|питер|санкт|екатеринбург|казан|сочи)",
        low_notes,
    ) and "онлайн" not in low_notes:
        extracted_data.include_online = False

    return extracted_data
