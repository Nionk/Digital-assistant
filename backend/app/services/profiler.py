import asyncio
import calendar
import datetime
import logging
import re
from typing import Literal, TypeAlias

import httpx
from instructor.core import InstructorError
from openai import APIError
from pydantic import ValidationError

from app.core.config import settings
from app.core.constants import CITY_ALIASES, is_online_format, normalize_city
from app.schemas.manager import ClientQueryExtracted
from app.services.ai_client import LLM_SEMAPHORE, structured_llm_client

logger = logging.getLogger(__name__)

EventFormat: TypeAlias = Literal["roundtable", "business_breakfast", "forum", "conference", "session"]
ParticipationRole: TypeAlias = Literal["delegate", "speaker", "sponsor"]

# Потолок бюджета по умолчанию, если в тексте заметки бюджет не указан вовсе
DEFAULT_UNCONSTRAINED_BUDGET: float = 1_000_000.0

# Грамматические словари для разбора русских числительных
_NUMERAL_UNITS: dict[str, int] = {
    "один": 1, "одну": 1, "одна": 1,
    "два": 2, "две": 2,
    "три": 3, "четыре": 4, "пять": 5, "шесть": 6, "семь": 7, "восемь": 8, "девять": 9,
    "десять": 10, "одиннадцать": 11, "двенадцать": 12, "тринадцать": 13, "четырнадцать": 14,
    "пятнадцать": 15, "шестнадцать": 16, "семнадцать": 17, "восемнадцать": 18, "девятнадцать": 19,
}
_NUMERAL_TENS: dict[str, int] = {
    "двадцать": 20, "тридцать": 30, "сорок": 40, "пятьдесят": 50,
    "шестьдесят": 60, "семьдесят": 70, "восемьдесят": 80, "девяносто": 90,
}
_NUMERAL_HUNDREDS: dict[str, int] = {
    "сто": 100, "двести": 200, "триста": 300, "четыреста": 400,
    "пятьсот": 500, "шестьсот": 600, "семьсот": 700, "восемьсот": 800, "девятьсот": 900,
}

_NUMERAL_CASES: dict[str, float] = {
    "одного": 1.0, "одному": 1.0,
    "двух": 2.0, "двум": 2.0,
    "трех": 3.0, "трёх": 3.0, "трем": 3.0, "трём": 3.0,
    "четырех": 4.0, "четырёх": 4.0, "четырем": 4.0,
    "пяти": 5.0, "пятью": 5.0,
    "шести": 6.0, "шестью": 6.0,
    "семи": 7.0, "семью": 7.0,
    "восьми": 8.0, "восемью": 8.0,
    "девяти": 9.0,
    "десяти": 10.0,
    "одиннадцати": 11.0, "двенадцати": 12.0, "пятнадцати": 15.0, "двадцати": 20.0,
    "тридцати": 30.0, "сорока": 40.0, "пятидесяти": 50.0, "ста": 100.0,
    "двухсот": 200.0, "трехсот": 300.0, "четырехсот": 400.0, "пятисот": 500.0,
    "половиной": 0.5, "половина": 0.5, "половину": 0.5,
}

_WORD_COUNT_MAP: dict[str, int] = {
    "одно": 1, "одну": 1, "один": 1,
    "два": 2, "две": 2,
    "три": 3, "четыре": 4, "пять": 5,
    "шесть": 6, "семь": 7, "восемь": 8, "девять": 9, "десять": 10,
}

# Общерусские стоп-слова и мета-слова заметок для фильтрации контентного ядра в фолбэке
_RUSSIAN_STOP_WORDS: set[str] = {
    "и", "в", "во", "не", "что", "он", "на", "я", "с", "со", "как", "а", "то", "все",
    "она", "так", "его", "но", "да", "ты", "к", "у", "же", "вы", "за", "бы", "по",
    "только", "ее", "мне", "было", "вот", "от", "меня", "еще", "нет", "о", "из", "ему",
    "теперь", "когда", "даже", "ну", "вдруг", "ли", "если", "уже", "или", "ни", "быть",
    "был", "него", "до", "вас", "нибудь", "опять", "уж", "вам", "ведь", "там", "потом",
    "себя", "ничего", "ей", "может", "они", "тут", "где", "есть", "надо", "ней", "для",
    "мы", "тебя", "их", "чем", "была", "сам", "чтоб", "без", "будто", "чего", "раз",
    "тоже", "себе", "под", "будет", "ж", "тогда", "кто", "этот", "того", "потому",
    "этого", "какой", "совсем", "ним", "здесь", "этом", "один", "почти", "мой", "тем",
    "чтобы", "нее", "сейчас", "были", "куда", "зачем", "всех", "никогда", "можно", "при",
    "наконец", "два", "другой", "хоть", "после", "над", "больше", "тот", "через", "эти",
    "нас", "про", "всего", "них", "какая", "много", "разве", "три", "эту", "моя", "впрочем",
    "хорошо", "свою", "этой", "перед", "иногда", "лучше", "чуть", "том", "нельзя",
    "созвонились", "созвон", "клиент", "компания", "ищем", "ищут", "нужно", "нужны",
    "хотим", "хотят", "требуется", "планируем", "подумали", "думали", "решили",
    "посмотреть", "послушать", "выступить", "привет", "здравствуйте", "общий", "потолок",
    "руб", "рублей", "рубля", "тыс", "млн", "бюджет", "мероприятия", "мероприятий",
    "площадки", "события", "конференции", "форумы", "встречи", "тусы", "сессии",
    "город", "городе", "онлайн", "офлайн", "очно", "спикером", "делегатом", "спонсором",
    "мск", "спб", "екб", "нн", "рнд",
    # Мета-слова и вводные фразы из заметок встреч менеджера
    "запрос", "рассматриваем", "рассмотреть", "рассмотрения", "рассмотрении",
    "исключительно", "очный", "очного", "формат", "форматы", "форматах",
    "дистанционка", "исключена", "профиль", "профильные", "выделено",
    "сумма", "лимит", "тематика", "вопросы", "бриф", "первоначально",
    "ориентировались", "направления", "направление", "фокусируемся",
    "сразу", "подчеркнули", "обсуждение", "изначально", "просчитывали",
    "организуем", "поездок", "серию", "выездов", "интервью", "долгосрочная",
    "стратегия", "целимся", "старт", "кампании", "запланирован", "холдинг",
    "штатом", "базой", "масштаб", "мест", "категорически", "отказываемся",
    "активности", "различные", "варианты", "цель", "смета", "рамки",
    "утверждена", "утверждены", "зафиксирован", "зафиксирована", "заложенная",
    "разговаривали", "представителем", "подборка", "года", "либо", "роли",
    "слушателей", "деньгам", "заходим", "выставочным", "местом", "сцену",
    "выходить", "участие", "качестве", "запрашивает", "пакет", "генерального",
    "партнера", "совет", "директоров", "отменил", "южные", "крупные", "вещанием",
    "всей", "стране", "готовы", "потратить", "слота", "наших", "докладчиков",
    "столичных", "событиях", "затрат", "гибкий", "край", "деловых",
    "тусовок", "годовой", "план", "корпоративный", "фаундером",
    "финансовые", "согласуют", "акционерами", "позже", "проведением",
    "столичный", "партнерское", "объем", "финансирования", "посещение",
    "делегация", "приедет", "лично", "остальные", "рассмотрим",
}


def _city_variant_pattern(var_clean: str) -> tuple[str, str]:
    """Строит регулярное выражение для поиска города и его основы для проверки отрицания."""
    if len(var_clean) <= 3:
        return rf"\b{re.escape(var_clean)}\b", var_clean
    stem = re.sub(r"[аяьеий]$", "", var_clean)
    return rf"\b{re.escape(stem)}[а-яё]{{0,3}}\b", stem


def _match_canonical_city(
    aliases: list[str],
    canonical: str,
    low: str,
    m_only: list[str],
) -> tuple[bool, bool]:
    """Проверяет вхождение канонического города или его алиасов без локального отрицания."""
    for var in [canonical, *aliases]:
        pat, stem_for_neg = _city_variant_pattern(var.lower().strip())
        if re.search(pat, low) and not re.search(rf"\b(?:не\s+в|не|без)\s+{re.escape(stem_for_neg)}", low):
            is_only = any(bool(re.search(pat, o_token)) for o_token in m_only)
            return True, is_only
    return False, False


def _extract_cities_heuristic(low: str) -> list[str]:
    """
    Извлекает и канонизирует города из текста заметки менеджера через словарь CITY_ALIASES.
    Поддерживает столичные синонимы и простое прямое отрицание ('не в Москве').
    """
    res_cities: list[str] = []
    if re.search(r"\bстолиц[а-яё]*\b|\bстоличн[а-яё]*\b", low):
        res_cities.append("Москва")

    m_only = re.findall(r"(?:только|исключительно)\s+(?:в|на)\s+([а-яё\-]+)", low)
    only_cities: list[str] = []

    for canonical, aliases in CITY_ALIASES.items():
        matched, is_only = _match_canonical_city(aliases, canonical, low, m_only)
        if matched and canonical not in res_cities:
            res_cities.append(canonical)
        if is_only and canonical not in only_cities:
            only_cities.append(canonical)

    return only_cities or res_cities


def _extract_include_online_heuristic(low: str, cities: list[str]) -> bool:
    """Определяет, допустимы ли онлайн-события или запрошен строгий офлайн."""
    strict_offline = bool(
        re.search(
            r"\b(?:только\s+очно|строго\s+очно|только\s+офлайн|строго\s+офлайн|очный\s+формат|живой\s+контакт|"
            r"без\s+онлайн[а-яё]*|без\s+вебинар[а-яё]*|без\s+трансляц[а-яё]*|без\s+зум[а-яё]*|дистанционка\s+исключена)\b",
            low,
        )
    )
    if not strict_offline and cities:
        city_patterns = [re.escape(c.lower()) for c in cities]
        pattern = rf"только\s+(?:в\s+)?(?:{'|'.join(city_patterns)})\b"
        if re.search(pattern, low) and "онлайн" not in low:
            strict_offline = True

    online_negated = bool(re.search(r"\bбез\s+(?:онлайн|вебинар|трансляц|зум|дистанцион)", low))
    explicit_online = bool(re.search(r"\b(?:онлайн|вебинар[а-яё]*|трансляц[а-яё]*|дистанционн[а-яё]*)\b", low)) and not online_negated
    return explicit_online or not strict_offline


_NUMERAL_VALUES: dict[str, float] = {
    **{k: float(v) for k, v in _NUMERAL_UNITS.items()},
    **{k: float(v) for k, v in _NUMERAL_TENS.items()},
    **{k: float(v) for k, v in _NUMERAL_HUNDREDS.items()},
    **_NUMERAL_CASES,
    "полтора": 1.5,
    "полторы": 1.5,
    "полмиллиона": 500_000.0,
    "полмиллиарда": 500_000_000.0,
}


def _get_scale_multiplier(w: str) -> float | None:
    """Возвращает числовой множитель разряда (тысячи, миллионы, миллиарды, сленг)."""
    clean = w.rstrip(".,").strip().lower()
    if clean.startswith(("тысяч", "косар", "тыс")) or clean in ("к", "k", "тр", "т.р"):
        return 1_000.0
    if clean.startswith(("миллион", "млн")):
        return 1_000_000.0
    if clean.startswith(("миллиард", "млрд")):
        return 1_000_000_000.0
    return None


_NUMERAL_FILLER_WORDS: frozenset[str] = frozenset(
    {"и", "с", "рублей", "рубля", "руб", "потолок", "до", "бюджет", "максимум", "лимит", "край"}
)


def _apply_numeral_word(
    w: str,
    total: float,
    current: float,
    has_numeral: bool,
) -> tuple[float, float, bool, bool]:
    """Обрабатывает одно слово при разборе числительного прописью."""
    scale = _get_scale_multiplier(w)
    if scale is not None:
        if not has_numeral and current == 0.0:
            return total, current, has_numeral, False
        return total + max(current, 1.0) * scale, 0.0, has_numeral, False

    if w in _NUMERAL_VALUES:
        val = _NUMERAL_VALUES[w]
        if w in ("полмиллиона", "полмиллиарда"):
            return total + val, current, True, False
        return total, current + val, True, False

    if w in _NUMERAL_FILLER_WORDS or not has_numeral:
        return total, current, has_numeral, False

    stop = max(total, current) >= 10_000.0
    return (total, current, True, True) if stop else (0.0, 0.0, False, False)


def _parse_numeral_phrase(text: str) -> float | None:
    """
    Разбор последовательных числительных прописью через грамматические разряды
    (единицы, десятки, сотни, падежные формы и множители тысяч/миллионов).
    """
    words = re.findall(r"[а-яёa-z]+", text.lower())
    total, current, has_numeral = 0.0, 0.0, False
    for w in words:
        total, current, has_numeral, stop = _apply_numeral_word(w, total, current, has_numeral)
        if stop:
            break

    total += current
    return total if (has_numeral and total >= 10_000.0) else None


def _extract_budget_heuristic(low: str) -> float:
    """
    Универсальное извлечение бюджета: диапазоны, суммы с множителями (млн, тыс, к),
    числительные прописью и прямые числа.
    """
    # 1. Диапазоны ("от 300 до 500 тыс", "1-2 млн") -> берется верхний потолок
    m_range = re.search(
        r"(\d+(?:[.,]\d+)?)\s*(?:[-–—]|до)\s*(\d+(?:[.,]\d+)?)\s*(млн|миллион[а-яё]*|тыс[а-яё.]*|к\b|косар[а-яё]*)",
        low,
    )
    if m_range:
        scale = _get_scale_multiplier(m_range.group(3)) or 1.0
        return float(m_range.group(2).replace(",", ".")) * scale

    # 2. Суммы с множителями разряда ("1.5 млн", "350к", "6 млн рублей", "800 тыс", "400 к")
    m_scale = re.search(
        r"(\d+(?:[.,]\d+)?)\s*(млн|миллион[а-яё]*|тыс[а-яё.]*|т\.?\s*р\.?|к\b|косар[а-яё]*)",
        low,
    )
    if m_scale:
        scale = _get_scale_multiplier(m_scale.group(2)) or 1.0
        return float(m_scale.group(1).replace(",", ".")) * scale

    # 3. Числительные прописью ("до пяти миллионов", "три с половиной миллиона руб")
    parsed_phrase = _parse_numeral_phrase(low)
    if parsed_phrase is not None:
        return parsed_phrase

    # 4. Прямые суммы цифрами с пробелами или слитные ("180 000 рублей", "250000 руб")
    raw_nums = re.findall(r"\b\d{1,3}(?:[\s\u00a0]\d{3})+\b|\b\d{5,8}\b", low)
    for rn in raw_nums:
        val = float(re.sub(r"[\s\u00a0]", "", rn))
        if 2020 <= val <= 2040:
            continue
        if val >= 10000:
            return val

    logger.info("Бюджет не обнаружен в тексте заметки, применен потолок по умолчанию: %s ₽", DEFAULT_UNCONSTRAINED_BUDGET)
    return DEFAULT_UNCONSTRAINED_BUDGET


_QUARTER_PATTERNS: tuple[tuple[str, tuple[int, ...]], ...] = (
    (r"\b1[\s\-]*кв|\bq1\b|перв[а-яё]+\s+квартал", (1, 2, 3)),
    (r"\b2[\s\-]*кв|\bq2\b|втор[а-яё]+\s+квартал", (4, 5, 6)),
    (r"\b3[\s\-]*кв|\bq3\b|трет[а-яё]+\s+квартал", (7, 8, 9)),
    (r"\b4[\s\-]*кв|\bq4\b|четверт[а-яё]+\s+квартал", (10, 11, 12)),
)

_SEASON_PATTERNS: tuple[tuple[str, tuple[int, ...]], ...] = (
    (r"весна|весной|весенн", (3, 4, 5)),
    (r"лето|летом|летн", (6, 7, 8)),
    (r"конец[а-яё]*\s+осен|конц[еа-яё]*\s+осен", (11,)),
    (r"осень|осенью|осенн", (9, 10, 11)),
    (r"зима|зимой|зимн", (12, 1, 2)),
)


def _detect_seasons_and_quarters(low: str) -> list[int]:
    """Детекция кварталов и сезонов года в виде списков номеров месяцев."""
    months: list[int] = []
    for pat, q_months in _QUARTER_PATTERNS:
        if re.search(pat, low):
            months.extend(q_months)
            break
    for pat, s_months in _SEASON_PATTERNS:
        if re.search(pat, low):
            months.extend(s_months)
            break
    return months


def _detect_target_year(low: str, today: datetime.date) -> tuple[int, bool]:
    """Определяет целевой год в скользящем окне [today.year .. today.year + 4]."""
    year_candidates = [
        int(y) for y in re.findall(r"\b(20\d{2})\b", low) if today.year <= int(y) <= today.year + 4
    ]
    if year_candidates:
        return year_candidates[0], True
    if re.search(r"в\s+след(?:ующ[а-яё]+)?\s+год|на\s+след(?:ующ[а-яё]+)?\s+год|в\s+следующем\s+месяце", low):
        return today.year + (1 if today.month == 12 else 0), True
    return today.year, False


def _extract_dates_heuristic(low: str, today: datetime.date) -> tuple[datetime.date, datetime.date]:
    """
    Динамический расчет временного окна поиска относительно переданной даты.
    Использует calendar.monthrange для точного расчета високосных годов (2028 г.)
    и динамический диапазон годов [today.year .. today.year + 4].
    """
    date_from = today + datetime.timedelta(
        days=7 if re.search(r"через\s+недел[юи]|не\s+ранее\s+чем\s+через\s+недел|не\s+раньше\s+чем\s+через\s+недел", low) else 0
    )
    date_to = today + datetime.timedelta(days=120)
    target_year, year_found = _detect_target_year(low, today)

    month_keywords: tuple[tuple[str, int], ...] = (
        ("январ", 1), ("феврал", 2), ("март", 3), ("апрел", 4),
        ("ма[йяе]", 5), ("июн", 6), ("июл", 7), ("август", 8),
        ("сентябр", 9), ("октябр", 10), ("ноябр", 11), ("декабр", 12),
    )
    detected_months = [m_num for kw, m_num in month_keywords if re.search(rf"\b{kw}[а-яё]*\b", low)]
    detected_months.extend(_detect_seasons_and_quarters(low))

    if detected_months:
        # Обработка сезона "зима" (12, 1, 2) на стыке годов
        if 12 in detected_months and any(m in (1, 2) for m in detected_months):
            if today.month in (1, 2):
                start_year = target_year - 1
                end_year = target_year
            else:
                start_year = target_year
                end_year = target_year + 1
            date_from = max(today, datetime.date(start_year, 12, 1))
            end_m = max(m for m in detected_months if m in (1, 2))
            date_to = datetime.date(end_year, end_m, calendar.monthrange(end_year, end_m)[1])
        else:
            min_m, max_m = min(detected_months), max(detected_months)
            if not year_found and max_m < today.month:
                target_year = today.year + 1
            date_from = max(today, datetime.date(target_year, min_m, 1))
            date_to = datetime.date(target_year, max_m, calendar.monthrange(target_year, max_m)[1])

    if re.search(r"начал[оеу]\s*(?:след|20\d{2})", low):
        ny = target_year + 1 if not year_found else target_year
        date_to = datetime.date(ny, 3, 31)

    return date_from, max(date_to, date_from)


def _extract_target_count_heuristic(low: str) -> int:
    """Извлекает желаемое число мероприятий в диапазоне от 1 до 10."""
    # 1. Специфическое разговорное "пару"
    if re.search(r"\bпару\b", low) and re.search(r"\b(?:мероприят|площад|событ|форум|тусов|встреч|выезд|сесси|конференц|ивент)", low):
        return 2

    # 2. Числовые диапазоны ("4-5 выездов", "2-3 мероприятия") -> нижний порог
    m_range = re.search(r"\b([1-9]|10)\s*[-–—]\s*([1-9]|10)\b", low)
    if m_range:
        return int(m_range.group(1))

    # 3. Число 1-10 перед существительным мероприятия (допускается одно прилагательное)
    m_count = re.search(
        r"\b([1-9]|10)\s+(?:[а-яё\-]+\s+)?(?:мероприят|площад|событ|форум|тусов|тусы|встреч|[а-яё\-]*сесси|конференц|конгресс|[а-яё\-]*завтрак|выезд|ивент|стол|саммит)",
        low,
    )
    if m_count:
        return max(1, min(10, int(m_count.group(1))))

    # 4. Числительные прописью ("из четырех масштабных", "две конференции")
    word_to_num = {
        "одн": 1, "дву": 2, "две": 2, "два": 2, "тре": 3, "три": 3, "четыр": 4,
        "пят": 5, "шест": 6, "сем": 7, "восем": 8, "девят": 9, "десят": 10,
    }
    for w_stem, num_val in word_to_num.items():
        if re.search(rf"\b{w_stem}[а-яё]*\s+(?:[а-яё\-]+\s+)?(?:мероприят|площад|событ|форум|тусов|встреч|сесси|конференц|выезд|завтрак|стол|саммит|ивент)", low):
            return num_val

    # 5. Прямой контекст типа "лучше 5", "отобрать 4"
    m_direct = re.search(r"\b(?:лучше|отобрать|выбрать|нужно|надо|хотим)\s*([1-9]|10)\b", low)
    if m_direct:
        return int(m_direct.group(1))

    return 3


def _detect_speaker_and_sponsor_flags(low: str) -> tuple[bool, bool, bool]:
    """Определяет флаги (wants_speaker, wants_sponsor, neg_delegate) с учетом отрицаний."""
    neg_speaker = bool(re.search(
        r"\b(?:не\s+хотим\s+быть\s+спик|спикер[а-яё]*\s+не\s+будем|не\s+выступать|без\s+спикер|без\s+доклад|"
        r"никаких\s+доклад|боит[а-яё]*\s+сцен|на\s+сцену\s+не|спикерск[а-яё]+\s+активност[а-яё]*\s+исключен[а-яё]*)\b",
        low,
    ))
    wants_speaker = bool(re.search(r"\b(?:спикер[а-яё]*|выступ[а-яё]*|доклад[а-яё]*|спич[а-яё]*)\b", low)) and not neg_speaker

    neg_sponsor = bool(re.search(
        r"\b(?:отказал[а-яё]*\s+от\s+спонсор|без\s+спонсор|стенд[а-яё]*\s+не\s+нужен|спонсор[а-яё]*\s+не\s+нужн|не\s+хотим\s+стенд)\b",
        low,
    ))
    wants_sponsor = bool(re.search(r"\b(?:стенд[а-яё]*|спонсор[а-яё]*|партнер[а-яё]*|партнёр[а-яё]*|экспозици[а-яё]*)\b", low)) and not neg_sponsor

    neg_delegate = bool(re.search(
        r"\b(?:не\s+делегат|без\s+делегат|только\s+спикер|исключительно\s+(?:в\s+роли\s+)?докладчик|"
        r"слушательск[а-яё]+\s+билет[а-яё]*\s+не\s+нужн|билет[а-яё]*\s+слушател[а-яё]*\s+не\s+интересн)\b",
        low,
    ))
    return wants_speaker, wants_sponsor, neg_delegate


def _extract_roles_and_speaker_heuristic(
    low: str,
    target_count: int,
) -> tuple[list[ParticipationRole], int]:
    """Извлекает роли участия и минимальное число спикерских слотов с учетом отрицаний."""
    wants_speaker, wants_sponsor, neg_delegate = _detect_speaker_and_sponsor_flags(low)
    explicit_delegate = bool(re.search(r"\b(?:делегат[а-яё]*|посетит[а-яё]*|слушател[а-яё]*|послушать|нетворк[а-яё]*)\b", low))
    min_speaker = _calculate_min_speaker_slots(low, target_count, wants_speaker, neg_delegate)

    roles: list[ParticipationRole] = []
    if wants_speaker:
        roles.append("speaker")
    if wants_sponsor:
        roles.append("sponsor")
    needs_delegate = explicit_delegate or (wants_speaker and min_speaker < target_count)
    if not roles or (not neg_delegate and needs_delegate):
        roles.append("delegate")

    return roles, min_speaker


def _calculate_min_speaker_slots(
    low: str,
    target_count: int,
    wants_speaker: bool,
    neg_delegate: bool,
) -> int:
    """Вычисляет запрошенное минимальное количество спикерских слотов."""
    if not wants_speaker:
        return 0
    if neg_delegate or re.search(r"\b(?:на\s+всех|на\s+обоих|на\s+обеих|везде\s+спик|только\s+спикер)\b", low):
        return min(5, target_count)
    m_spk_num = re.search(
        r"\b([1-9]|10)\s+(?:[а-яё\-]+\s+)?(?:спикер|слот|доклад|выступ)|"
        r"\b(?:выступ[а-яё]*|доклад[а-яё]*|спикер[а-яё]*)\s+на\s+([1-9]|10)\b",
        low,
    )
    if m_spk_num:
        cnt_str = m_spk_num.group(1) or m_spk_num.group(2)
        return min(5, target_count, max(1, int(cnt_str)))
    return 1


def _extract_formats_heuristic(low: str) -> list[EventFormat]:
    """Извлекает предпочтительные форматы мероприятий с учетом прямого отрицания."""
    format_defs: list[tuple[EventFormat, str]] = [
        ("roundtable", r"\b(?:кругл[а-яё]+\s+стол[а-яё]*|камерн[а-яё]+|закрыт[а-яё]+\s+встреч[а-яё]*)\b"),
        ("business_breakfast", r"\b(?:бизнес[\s\-]*завтрак[а-яё]*|завтрак[а-яё]*)\b"),
        ("forum", r"\b(?:форум[а-яё]*|выставк[а-яё]*|саммит[а-яё]*|съезд[а-яё]*)\b"),
        ("conference", r"\b(?:конференц[а-яё]*|конгресс[а-яё]*|симпозиум[а-яё]*)\b"),
        ("session", r"\b(?:сесси[яиеей]|страт[\s\-]*сесси[а-яё]*|дискусси[а-яё]*)\b"),
    ]
    formats: list[EventFormat] = []
    for fmt_name, pat in format_defs:
        if re.search(pat, low):
            neg_pat = rf"\b(?:не|без|никаких|только\s+не)\s+(?:[а-яё\-]+\s+)?(?:{pat.replace(r'\b', '')})"
            if not re.search(neg_pat, low):
                formats.append(fmt_name)
    return formats


def _extract_content_tokens(low: str, cities: list[str]) -> list[str]:
    """Извлекает содержательные токены текста за вычетом стоп-слов и городов."""
    tokens = re.findall(r"[а-яёa-z\-]+", low)
    content_tokens: list[str] = []
    for tok in tokens:
        clean_tok = tok.strip("-")
        if (
            len(clean_tok) >= 3
            and clean_tok not in _RUSSIAN_STOP_WORDS
            and not any(clean_tok in c.lower() for c in cities)
        ):
            content_tokens.append(clean_tok)
    return content_tokens


def _build_semantic_query(
    themes: list[str],
    cities: list[str],
    content_tokens: list[str],
    low: str,
    raw_text: str = "",
) -> str:
    """Собирает плотный семантический запрос для векторного поиска pgvector."""
    sem_parts = [*themes, *cities]
    if "спик" in low and "не хотим" not in low:
        sem_parts.append("выступление спикером в деловой программе")
    if "стенд" in low or "спонсор" in low:
        sem_parts.append("экспозиция стенд партнерское участие")
    cleaned_core = " ".join(content_tokens[:20])
    res = f"{' '.join(sem_parts)} {cleaned_core}"[:350].strip()
    if not res:
        res = raw_text[:350].strip() or "деловые мероприятия форумы конференции"
    return res


def _extract_themes_and_query_heuristic(text: str, low: str, cities: list[str]) -> tuple[list[str], str]:
    """
    Кросс-отраслевое извлечение сущностей (Domain-Agnostic Entity Extraction):
    1. Профессиональные аббревиатуры любой сферы (API, ERP, CRM, BIM, КРТ, ИЖС, ESG, AI, ИИ, DevOps и др.)
    2. Содержательные предметные термины с фильтрацией русских стоп-слов.
    3. Формирование плотного семантического поискового запроса для pgvector.
    """
    themes: list[str] = []
    for acr in re.findall(r"\b[A-ZА-ЯЁ]{2,6}\b", text):
        acr_upper = acr.upper()
        if acr_upper.lower() not in _RUSSIAN_STOP_WORDS and acr_upper not in themes:
            themes.append(acr_upper)

    content_tokens = _extract_content_tokens(low, cities)
    for c_tok in content_tokens:
        if len(themes) >= 15:
            break
        stem = re.sub(r"[аяьеий]$", "", c_tok)
        if not any(re.search(rf"\b{re.escape(stem)}", t.lower()) for t in themes):
            themes.append(c_tok)

    return themes, _build_semantic_query(themes, cities, content_tokens, low, raw_text=text)


def extract_profile_heuristic(
    raw_notes: str,
    today: datetime.date | None = None,
) -> ClientQueryExtracted:
    """
    Чистый детерминированный извлекатель параметров запроса из текста заметки менеджера.
    Используется как мгновенный страхующий фолбэк при недоступности внешнего LLM-шлюза
    или пустом API-ключе, сохраняя работоспособность конвейера подбора без отраслевой предвзятости.
    """
    ref_today = today or datetime.date.today()
    text = raw_notes or ""
    low = text.lower()

    cities = _extract_cities_heuristic(low)
    include_online = _extract_include_online_heuristic(low, cities)
    budget = _extract_budget_heuristic(low)
    date_from, date_to = _extract_dates_heuristic(low, ref_today)
    target_count = _extract_target_count_heuristic(low)
    roles, min_speaker = _extract_roles_and_speaker_heuristic(low, target_count)
    formats = _extract_formats_heuristic(low)
    themes, semantic_query = _extract_themes_and_query_heuristic(text, low, cities)

    return ClientQueryExtracted(
        cities=cities,
        include_online=include_online,
        date_from=date_from,
        date_to=date_to,
        total_budget_max=budget,
        target_events_count=target_count,
        preferred_formats=formats,
        required_roles=roles,
        min_speaker_events=min_speaker,
        themes_keywords=themes,
        semantic_search_query=semantic_query,
    )


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
4. `total_budget_max`: Общий верхний потолок бюджета на ВСЮ серию мероприятий (число > 0). Распознавай любые разговорные числительные ("1млн" -> 1000000.0, "полтора миллиона" -> 1500000.0, "350к" -> 350000.0, "четыре миллиона" -> 4000000.0, "три с половиной миллиона" -> 3500000.0, "от 300 до 500 тыс" -> 500000.0). Если бюджет не назван, укажи верхний потолок серии по умолчанию (1000000.0).
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
    if extracted_data.cities:
        _normalize_profile_cities(extracted_data)

    low_notes = (raw_notes or "").lower()
    _clamp_profile_date_from(extracted_data, low_notes, today)

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
    today = datetime.date.today()
    if not settings.LLM_API_KEY:
        logger.info("LLM_API_KEY не задан. Применяется универсальный детерминированный парсер.")
        return extract_profile_heuristic(raw_notes, today)

    system_prompt = _build_profiler_system_prompt(today)
    try:
        async with LLM_SEMAPHORE:
            extracted_data: ClientQueryExtracted = await asyncio.wait_for(
                structured_llm_client.chat.completions.create(
                    model=settings.LLM_MODEL,
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
        return extract_profile_heuristic(raw_notes, today)

    return _postprocess_extracted_profile(extracted_data, raw_notes, today)
