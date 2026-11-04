"""
STRESS TEST SUITE: Профилировщик заметок менеджера (Senior QA Adversarial Benchmark).
Полная объективная оценка точности извлечения параметров (NER Profiling)
на 20 разносторонних провокационных кейсах из 10+ отраслей бизнеса.

ФАЛЬСИФИКАЦИЯ ТЕСТОВ СТРОГО ЗАПРЕЩЕНА.
Все несовпадения и ошибки фиксируются и выводятся с жестоким штрафованием.
"""

import asyncio
import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Настройка путей и кодировки консоли
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.schemas.manager import ClientQueryExtracted
from app.services.profiler import (
    extract_client_profile,
    extract_profile_heuristic,
)


@dataclass
class TestCase:
    id: int
    category: str
    industry: str
    text: str
    expected_cities: list[str]
    expected_online: bool
    expected_budget: float | None  # None = не указан, допустим дефолт
    expected_target_count: int
    expected_formats: list[str]
    expected_roles: list[str]
    expected_min_speaker: int
    expected_themes_contain: list[str]
    forbidden_cities: list[str] = field(default_factory=list)
    forbidden_formats: list[str] = field(default_factory=list)
    forbidden_roles: list[str] = field(default_factory=list)
    expected_year: int | None = None
    expected_month_range: tuple[int, int] | None = None
    requires_leap_day: bool = False


# 20 провокационных, кросс-отраслевых и дискурсивно сложных кейсов с естественными формулировками
STRESS_TEST_CASES: list[TestCase] = [
    # --- КАТЕГОРИЯ A: Кросс-отраслевое разнообразие ---
    TestCase(
        id=1,
        category="Cross-Industry",
        industry="FinTech / Banking",
        text="Разговаривали с представителем Точка Банка. Интересует подборка на Q1 2027 года: 3 площадки в Москве либо с дистанционным участием. Тематика — открытые API, цифровой рубль, биометрические сервисы. Планируем выступить с докладом на 2 событиях, а на оставшемся быть в роли слушателей. Лимит по деньгам за всё — три с половиной миллиона руб.",
        expected_cities=["Москва"],
        expected_online=True,
        expected_budget=3_500_000.0,
        expected_target_count=3,
        expected_formats=[],
        expected_roles=["speaker", "delegate"],
        expected_min_speaker=2,
        expected_themes_contain=["api", "рубл", "биометр"],
        expected_year=2027,
        expected_month_range=(1, 3),
    ),
    TestCase(
        id=2,
        category="Cross-Industry",
        industry="Pharma & Biotech",
        text="Запрос от Биокад: на ноябрь рассматриваем исключительно очный формат в Санкт-Петербурге, дистанционка исключена. Формат — камерные круглые столы. Профиль: онкологические препараты, генная инженерия, проведение клинических испытаний. Заходим как спонсоры с выставочным местом, на сцену с докладами выходить не планируем. Выделено 800 тыс рублей.",
        expected_cities=["Санкт-Петербург"],
        expected_online=False,
        expected_budget=800_000.0,
        expected_target_count=3,
        expected_formats=["roundtable"],
        expected_roles=["sponsor"],
        expected_min_speaker=0,
        expected_themes_contain=["онколог", "генн", "клиническ"],
        forbidden_roles=["speaker"],
    ),
    TestCase(
        id=3,
        category="Cross-Industry",
        industry="IT & Cloud Infrastructure",
        text="Яндекс Cloud планирует серию из четырех масштабных конференций или форумов. Фокус: архитектура Kubernetes, разработка на Go, построение Highload систем. Рассматриваем локации: столица, Казань или Нижний Новгород. На всех 4 ивентах заявляем собственных спикеров. Бюджетная планка — до пяти миллионов.",
        expected_cities=["Москва", "Казань", "Нижний Новгород"],
        expected_online=True,
        expected_budget=5_000_000.0,
        expected_target_count=4,
        expected_formats=["forum", "conference"],
        expected_roles=["speaker"],
        expected_min_speaker=4,
        expected_themes_contain=["kubernetes", "highload"],
    ),
    TestCase(
        id=4,
        category="Cross-Industry",
        industry="Retail & FMCG",
        text="ВкусВилл: весной нужны 2 бизнес-завтрака либо дискуссионные сессии в Екатеринбурге. Обязательно личное присутствие на Урале, без вебинаров. Вопросы СТМ, продажи на маркетплейсах, экспресс-доставка. Участие в качестве делегатов, смета 250 000 руб.",
        expected_cities=["Екатеринбург"],
        expected_online=False,
        expected_budget=250_000.0,
        expected_target_count=2,
        expected_formats=["business_breakfast", "session"],
        expected_roles=["delegate"],
        expected_min_speaker=0,
        expected_themes_contain=["маркетплейс", "доставк"],
        expected_month_range=(3, 5),
    ),
    TestCase(
        id=5,
        category="Cross-Industry",
        industry="Heavy Industry & Mining",
        text="Северсталь запрашивает участие в отраслевом промышленном форуме осенью 2027 года (Красноярск либо Новосибирск). Декарбонизация, роботизированные металлургические линии. Пакет генерального партнера с экспозицией. Смета утверждена: 6 млн рублей.",
        expected_cities=["Красноярск", "Новосибирск"],
        expected_online=True,
        expected_budget=6_000_000.0,
        expected_target_count=3,
        expected_formats=["forum"],
        expected_roles=["sponsor"],
        expected_min_speaker=0,
        expected_themes_contain=["металлург", "роботизир"],
        expected_year=2027,
        expected_month_range=(9, 11),
    ),

    # --- КАТЕГОРИЯ B: Дискурсивные ловушки, отказ от вариантов, смена решений ---
    TestCase(
        id=6,
        category="Discourse & Negation",
        industry="Cybersecurity",
        text="Бриф Сбера: первоначально ориентировались на Сочи и Ялту, но совет директоров отменил южные направления. Фокусируемся исключительно на Казани, только живой контакт. На декабрь требуется 1 закрытый круглый стол: кибербезопасность, предотвращение утечек данных. Выступать не будем, берем билеты слушателей. Сумма 180к.",
        expected_cities=["Казань"],
        expected_online=False,
        expected_budget=180_000.0,
        expected_target_count=1,
        expected_formats=["roundtable"],
        expected_roles=["delegate"],
        expected_min_speaker=0,
        expected_themes_contain=["кибер", "утечек"],
        forbidden_cities=["Сочи", "Ялта"],
        forbidden_roles=["speaker"],
    ),
    TestCase(
        id=7,
        category="Discourse & Negation",
        industry="Marketing & AI",
        text="Сразу подчеркнули: никаких круглых столов и закрытых завтраков, они неэффективны для лидогенерации! Нужны только крупные конгрессы или отраслевые форумы с онлайн-вещанием по всей стране. Фокус: искусственный интеллект в маркетинге. Готовы потратить 500 тыс, нужно 2 слота для наших докладчиков.",
        expected_cities=[],
        expected_online=True,
        expected_budget=500_000.0,
        expected_target_count=3,
        expected_formats=["conference", "forum"],
        expected_roles=["speaker"],
        expected_min_speaker=2,
        expected_themes_contain=["маркетинг", "интеллект"],
        forbidden_formats=["roundtable", "business_breakfast"],
    ),
    TestCase(
        id=8,
        category="Discourse & Negation",
        industry="HR & EdTech",
        text="Обсуждение ролей: изначально просчитывали брендированный стенд, но из-за стоимости застройки от спонсорского пакета отказались. Участвуем исключительно в роли докладчиков на 2 столичных событиях. Выделенный бюджет — 450 тыс. руб.",
        expected_cities=["Москва"],
        expected_online=True,
        expected_budget=450_000.0,
        expected_target_count=2,
        expected_formats=[],
        expected_roles=["speaker"],
        expected_min_speaker=2,
        expected_themes_contain=[],
        forbidden_roles=["sponsor"],
    ),

    # --- КАТЕГОРИЯ C: Сложные числительные, сленг, валюты, диапазоны ---
    TestCase(
        id=9,
        category="Numerals & Slang",
        industry="Logistics",
        text="Организуем серию выездов (4-5 выездов) по складской логистике и внешнеэкономической деятельности (ВЭД). География: Москва и Санкт-Петербург. Формат — экспертные сессии. Лимит затрат гибкий: от полутора до двух миллионов рублей.",
        expected_cities=["Москва", "Санкт-Петербург"],
        expected_online=True,
        expected_budget=2_000_000.0,  # Потолок диапазона
        expected_target_count=4,
        expected_formats=["session"],
        expected_roles=["delegate"],
        expected_min_speaker=0,
        expected_themes_contain=["логистик", "вэд"],
    ),
    TestCase(
        id=10,
        category="Numerals & Slang",
        industry="FinTech",
        text="Подыщите пару деловых тусовок по финтех-инновациям в мск в следующем месяце. Лимит от трехсот пятидесяти косарей, край четыреста к. Как минимум на одном событии хотим дать экспертный спич.",
        expected_cities=["Москва"],
        expected_online=True,
        expected_budget=400_000.0,  # Максимальное ограничение
        expected_target_count=2,    # 'пару деловых тусовок'
        expected_formats=[],
        expected_roles=["speaker", "delegate"],
        expected_min_speaker=1,
        expected_themes_contain=["финтех"],
    ),
    TestCase(
        id=11,
        category="Numerals & Slang",
        industry="Big Data & AI",
        text="Газпромбанк: формируем годовой план из 8 деловых выездов по внедрению искусственного интеллекта и больших данных (Big Data). Только очные площадки в мегаполисах, без зумов. Корпоративный лимит зафиксирован: двенадцать миллионов рублей.",
        expected_cities=[],
        expected_online=False,
        expected_budget=12_000_000.0,
        expected_target_count=8,  # Проверка поддержки > 5
        expected_formats=[],
        expected_roles=["delegate"],
        expected_min_speaker=0,
        expected_themes_contain=["данн", "интеллект"],
    ),
    TestCase(
        id=12,
        category="Numerals & Slang",
        industry="Venture / Startup",
        text="Интервью с фаундером стартапа. Ищем профильные питч-сессии перед венчурными фондами в EdTech-сегменте (Москва либо Иннополис). Финансовые рамки пока не утверждены, согласуют с акционерами позже.",
        expected_cities=["Москва"],
        expected_online=True,
        expected_budget=None,  # Должен сработать безопасный unconstrained default
        expected_target_count=3,
        expected_formats=["session"],
        expected_roles=["delegate"],
        expected_min_speaker=0,
        expected_themes_contain=["венчурн", "edtech", "стартап"],
    ),

    # --- КАТЕГОРИЯ D: Даты, сезоны, високосные годы, временной горизонт ---
    TestCase(
        id=13,
        category="Dates & Leap Years",
        industry="Medicine / Cardiology",
        text="Медицинская конференция по кардиохирургии в Новосибирске с проведением строго 28-29 февраля 2028 года. Лимит участия 300 000 руб.",
        expected_cities=["Новосибирск"],
        expected_online=True,
        expected_budget=300_000.0,
        expected_target_count=3,
        expected_formats=["conference"],
        expected_roles=["delegate"],
        expected_min_speaker=0,
        expected_themes_contain=["кардио"],
        expected_year=2028,
        expected_month_range=(2, 2),
        requires_leap_day=True,  # Должно захватывать 29 февраля 2028 г.
    ),
    TestCase(
        id=14,
        category="Dates & Leap Years",
        industry="Autonomous Transport",
        text="Долгосрочная стратегия: целимся в крупный столичный саммит весной 2030 года по тематике беспилотных автомобилей и машинного обучения. Заложенная сумма — полтора миллиона.",
        expected_cities=["Москва"],
        expected_online=True,
        expected_budget=1_500_000.0,
        expected_target_count=3,
        expected_formats=["forum"],
        expected_roles=["delegate"],
        expected_min_speaker=0,
        expected_themes_contain=["беспилотн", "обучен"],
        expected_year=2030,
        expected_month_range=(3, 5),
    ),
    TestCase(
        id=15,
        category="Dates & Leap Years",
        industry="AgroTech",
        text="Старт кампании запланирован не раньше чем через неделю. Ищем 2 осенних форума по сельхозтехнологиям и агробизнесу в Ростове и Краснодаре. Партнерское участие со стендом. Бюджет 700 000 рублей.",
        expected_cities=["Ростов-на-Дону", "Краснодар"],
        expected_online=True,
        expected_budget=700_000.0,
        expected_target_count=2,
        expected_formats=["forum"],
        expected_roles=["sponsor"],
        expected_min_speaker=0,
        expected_themes_contain=["сельхоз", "агро"],
        expected_month_range=(9, 11),
    ),

    # --- КАТЕГОРИЯ E: Сложные композиционные кейсы с подвохами ---
    TestCase(
        id=16,
        category="Edge Cases & Noise",
        industry="Enterprise IT",
        text="Холдинг со штатом 5000 сотрудников и базой 20000 контрагентов подбирает форум в Казани на 2027 год, масштаб зала от 1500 мест. Выделенный объем финансирования на билеты — 600 тыс руб.",
        expected_cities=["Казань"],
        expected_online=True,
        expected_budget=600_000.0,  # Не должен перепутать с 5000, 20000, 1500 или 2027!
        expected_target_count=3,
        expected_formats=["forum"],
        expected_roles=["delegate"],
        expected_min_speaker=0,
        expected_themes_contain=[],
        expected_year=2027,
    ),
    TestCase(
        id=17,
        category="Edge Cases & Noise",
        industry="Legal & Tax",
        text="Выступать со сцены категорически отказываемся, спикерские активности исключены. Нас интересует только посещение сессий в зале либо трансляция. Тема — налоговые споры и комплаенс. Бюджет 90 тыс.",
        expected_cities=[],
        expected_online=True,
        expected_budget=90_000.0,
        expected_target_count=3,
        expected_formats=[],
        expected_roles=["delegate"],
        expected_min_speaker=0,
        expected_themes_contain=["налог", "спор"],
        forbidden_roles=["speaker"],
    ),
    TestCase(
        id=18,
        category="Edge Cases & Noise",
        industry="Ecology & Recycling",
        text="Рассматривали сосновый бор и различные варианты загородных баз, но в итоге утвердили площадки в Самаре и Перми. 3 круглых стола по рециклингу и экологической повестке. Бюджет 300 000 руб.",
        expected_cities=["Самара", "Пермь"],  # Бор — омоним, не город!
        expected_online=True,
        expected_budget=300_000.0,
        expected_target_count=3,
        expected_formats=["roundtable"],
        expected_roles=["delegate"],
        expected_min_speaker=0,
        expected_themes_contain=["эколог", "рециклинг"],
        forbidden_cities=["Бор"],
    ),
    TestCase(
        id=19,
        category="Edge Cases & Noise",
        industry="Cybersecurity",
        text="Слушательские билеты нам не нужны, цель — строго спикерские выступления! Требуются 2 конференции в Москве по защите информации от взломов. Сумма один миллион.",
        expected_cities=["Москва"],
        expected_online=True,
        expected_budget=1_000_000.0,
        expected_target_count=2,
        expected_formats=["conference"],
        expected_roles=["speaker"],
        expected_min_speaker=2,
        expected_themes_contain=["информаци", "взлом"],
        forbidden_roles=["delegate"],
    ),
    TestCase(
        id=20,
        category="Edge Cases & Noise",
        industry="Quantum Computing",
        text="На главный форум в Москве делегация приедет лично, а остальные площадки рассмотрим только в онлайн-формате. Всего нужно 3 мероприятия по квантовым технологиям. Потолок 800к.",
        expected_cities=["Москва"],
        expected_online=True,
        expected_budget=800_000.0,
        expected_target_count=3,
        expected_formats=["forum"],
        expected_roles=["delegate"],
        expected_min_speaker=0,
        expected_themes_contain=["квант"],
    ),
]


@dataclass
class EvaluationDetail:
    field_name: str
    is_correct: bool
    expected: Any
    actual: Any
    error_message: str = ""


@dataclass
class CaseResult:
    test_id: int
    category: str
    industry: str
    engine_name: str
    elapsed_sec: float
    total_checks: int
    passed_checks: int
    details: list[EvaluationDetail]

    @property
    def score_percent(self) -> float:
        return (self.passed_checks / self.total_checks * 100.0) if self.total_checks else 0.0

    @property
    def is_flawless(self) -> bool:
        return self.passed_checks == self.total_checks


def evaluate_extracted_profile(
    case: TestCase,
    profile: ClientQueryExtracted,
    engine_name: str,
    elapsed_sec: float,
) -> CaseResult:
    """Жестокое судейство качества извлечения по каждому измерению контракта."""
    details: list[EvaluationDetail] = []

    # 1. Города: полнота (Recall)
    actual_cities_set = set(profile.cities)
    for ec in case.expected_cities:
        ok = ec in actual_cities_set
        details.append(
            EvaluationDetail(
                field_name=f"city_recall_{ec}",
                is_correct=ok,
                expected=ec,
                actual=profile.cities,
                error_message=f"Город '{ec}' не был найден!" if not ok else "",
            )
        )

    # 1b. Города: отсутствие ложных срабатываний (Precision / Forbidden cities)
    for fc in case.forbidden_cities:
        found_forbidden = fc in actual_cities_set
        details.append(
            EvaluationDetail(
                field_name=f"city_forbidden_{fc}",
                is_correct=not found_forbidden,
                expected=f"NOT {fc}",
                actual=profile.cities,
                error_message=f"ГРУБАЯ ОШИБКА: Запрещенный/отвергнутый город '{fc}' попал в выборку!"
                if found_forbidden
                else "",
            )
        )

    # 2. Флаг Online
    online_ok = profile.include_online == case.expected_online
    details.append(
        EvaluationDetail(
            field_name="include_online",
            is_correct=online_ok,
            expected=case.expected_online,
            actual=profile.include_online,
            error_message="Неверно распознан онлайн/офлайн режим!" if not online_ok else "",
        )
    )

    # 3. Бюджет (Допуск 1.0 руб)
    if case.expected_budget is not None:
        budget_diff = abs(profile.total_budget_max - case.expected_budget)
        budget_ok = budget_diff < 1.0
        details.append(
            EvaluationDetail(
                field_name="budget",
                is_correct=budget_ok,
                expected=case.expected_budget,
                actual=profile.total_budget_max,
                error_message=f"Бюджет не совпал: ожидалось {case.expected_budget:,.0f} руб., получено {profile.total_budget_max:,.0f} руб. (дельта {budget_diff:,.0f} руб.)"
                if not budget_ok
                else "",
            )
        )
    else:
        # Случай когда бюджет не указан: профиль обязан вернуть число > 0
        budget_ok = profile.total_budget_max > 0
        details.append(
            EvaluationDetail(
                field_name="budget_unconstrained",
                is_correct=budget_ok,
                expected="positive_fallback",
                actual=profile.total_budget_max,
                error_message="При отсутствии бюджета вернулось недопустимое значение" if not budget_ok else "",
            )
        )

    # 4. Целевое количество событий (target_events_count)
    target_ok = profile.target_events_count == case.expected_target_count
    details.append(
        EvaluationDetail(
            field_name="target_events_count",
            is_correct=target_ok,
            expected=case.expected_target_count,
            actual=profile.target_events_count,
            error_message=f"Ожидалось {case.expected_target_count} событий, получено {profile.target_events_count}"
            if not target_ok
            else "",
        )
    )

    # 5. Форматы мероприятий
    for ef in case.expected_formats:
        f_ok = ef in profile.preferred_formats
        details.append(
            EvaluationDetail(
                field_name=f"format_{ef}",
                is_correct=f_ok,
                expected=ef,
                actual=profile.preferred_formats,
                error_message=f"Формат '{ef}' был запрошен, но не найден" if not f_ok else "",
            )
        )

    for ff in case.forbidden_formats:
        f_forbidden = ff in profile.preferred_formats
        details.append(
            EvaluationDetail(
                field_name=f"format_forbidden_{ff}",
                is_correct=not f_forbidden,
                expected=f"NOT {ff}",
                actual=profile.preferred_formats,
                error_message=f"ГРУБАЯ ОШИБКА: Запрещенный формат '{ff}' включен в профиль!" if f_forbidden else "",
            )
        )

    # 6. Роли участия и спикеры
    for er in case.expected_roles:
        r_ok = er in profile.required_roles
        details.append(
            EvaluationDetail(
                field_name=f"role_{er}",
                is_correct=r_ok,
                expected=er,
                actual=profile.required_roles,
                error_message=f"Роль '{er}' не была включена" if not r_ok else "",
            )
        )

    for fr in case.forbidden_roles:
        r_forbidden = fr in profile.required_roles
        details.append(
            EvaluationDetail(
                field_name=f"role_forbidden_{fr}",
                is_correct=not r_forbidden,
                expected=f"NOT {fr}",
                actual=profile.required_roles,
                error_message=f"ГРУБАЯ ОШИБКА: Запрещенная роль '{fr}' включена в профиль!" if r_forbidden else "",
            )
        )

    speaker_ok = profile.min_speaker_events == case.expected_min_speaker
    details.append(
        EvaluationDetail(
            field_name="min_speaker_events",
            is_correct=speaker_ok,
            expected=case.expected_min_speaker,
            actual=profile.min_speaker_events,
            error_message=f"Ожидалось спикерских слотов: {case.expected_min_speaker}, получено {profile.min_speaker_events}"
            if not speaker_ok
            else "",
        )
    )

    # 7. Даты (Год, месяцы, високосный день)
    if case.expected_year is not None:
        year_ok = (profile.date_to is not None and profile.date_to.year == case.expected_year) or (
            profile.date_from is not None and profile.date_from.year == case.expected_year
        )
        details.append(
            EvaluationDetail(
                field_name="year_match",
                is_correct=year_ok,
                expected=case.expected_year,
                actual=f"{profile.date_from}..{profile.date_to}",
                error_message=f"Год даты не распознан: ожидался {case.expected_year}" if not year_ok else "",
            )
        )

    if case.expected_month_range is not None:
        min_m, max_m = case.expected_month_range
        month_ok = False
        if profile.date_to is not None:
            month_ok = min_m <= profile.date_to.month <= max_m
        details.append(
            EvaluationDetail(
                field_name="month_range",
                is_correct=month_ok,
                expected=f"month in [{min_m}..{max_m}]",
                actual=f"{profile.date_to}",
                error_message=f"Месяц даты окончания не попал в диапазон [{min_m}..{max_m}]" if not month_ok else "",
            )
        )

    if case.requires_leap_day:
        leap_ok = profile.date_to is not None and profile.date_to.month == 2 and profile.date_to.day == 29
        details.append(
            EvaluationDetail(
                field_name="leap_day_29_feb",
                is_correct=leap_ok,
                expected="YYYY-02-29",
                actual=f"{profile.date_to}",
                error_message="ВИСОКОСНЫЙ БАГ: 29 февраля не было включено в границу поиска!" if not leap_ok else "",
            )
        )

    # 8. Тематические сущности
    all_theme_text = (
        " ".join(profile.themes_keywords).lower() + " " + profile.semantic_search_query.lower()
    )
    for stem in case.expected_themes_contain:
        stem_ok = stem.lower() in all_theme_text
        details.append(
            EvaluationDetail(
                field_name=f"theme_stem_{stem}",
                is_correct=stem_ok,
                expected=stem,
                actual=profile.themes_keywords,
                error_message=f"Отраслевая сущность со стемом '{stem}' полностью потеряна в themes_keywords и semantic_query!"
                if not stem_ok
                else "",
            )
        )

    passed_cnt = sum(1 for d in details if d.is_correct)
    return CaseResult(
        test_id=case.id,
        category=case.category,
        industry=case.industry,
        engine_name=engine_name,
        elapsed_sec=elapsed_sec,
        total_checks=len(details),
        passed_checks=passed_cnt,
        details=details,
    )


async def run_stress_suite():
    print("=" * 80)
    print("  ADVERSARIAL NER STRESS TEST SUITE (SENIOR QA AUDIT)")
    print("  Проверка отказоустойчивости, честности и универсальности profiler.py")
    print(f"  Всего провокационных сценариев: {len(STRESS_TEST_CASES)}")
    print("=" * 80)

    heuristic_results: list[CaseResult] = []
    llm_results: list[CaseResult] = []

    print("\n[ЭТАП 1/2] Прогон детерминированного эвристического парсера (Fallback Heuristic)...")
    t_start = time.perf_counter()
    for case in STRESS_TEST_CASES:
        t0 = time.perf_counter()
        prof = extract_profile_heuristic(case.text)
        dt = time.perf_counter() - t0
        res = evaluate_extracted_profile(case, prof, "Deterministic Heuristic", dt)
        heuristic_results.append(res)
    t_heu_total = time.perf_counter() - t_start
    print(f"  => Эвристический парсер завершил 20 тестов за {t_heu_total*1000.0:.1f} мс (среднее: {t_heu_total/len(STRESS_TEST_CASES)*1000.0:.2f} мс/тест)")

    cache_path = Path(__file__).resolve().parent / "llm_stress_cache.json"
    cache: dict[str, dict[str, Any]] = {}
    if cache_path.exists():
        try:
            cache = json.loads(cache_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            cache = {}

    print("\n[ЭТАП 2/2] Прогон облачного LLM-профилировщика (extract_client_profile)...")
    for idx, case in enumerate(STRESS_TEST_CASES, 1):
        case_key = str(case.id)
        print(f"  [{idx}/{len(STRESS_TEST_CASES)}] Тестирование LLM: {case.industry} ({case.category})...", end="", flush=True)
        t0 = time.perf_counter()
        try:
            if case_key in cache:
                prof_llm = ClientQueryExtracted.model_validate(cache[case_key]["profile"])
                dt = cache[case_key].get("elapsed_sec", 0.0)
                cached_mark = " (кэш)"
            else:
                prof_llm = await extract_client_profile(case.text)
                dt = time.perf_counter() - t0
                cache[case_key] = {"profile": prof_llm.model_dump(mode="json"), "elapsed_sec": dt}
                cached_mark = ""
                cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")

            res_llm = evaluate_extracted_profile(case, prof_llm, "Cloud LLM (Instructor)", dt)
            print(f" {dt:.2f}с{cached_mark} -> Score: {res_llm.score_percent:.1f}% ({res_llm.passed_checks}/{res_llm.total_checks})")
            llm_results.append(res_llm)
        except (TimeoutError, RuntimeError, ValueError) as exc:
            dt = time.perf_counter() - t0
            print(f" CRASH ({dt:.2f}с): {exc}")

    # =========================================================================
    # ПОДРОБНЫЙ АНАЛИТИЧЕСКИЙ ОТЧЕТ
    # =========================================================================
    print("\n" + "=" * 80)
    print("  ПОДРОБНАЯ СВОДКА И АНАЛИЗ ОШИБОК ПО КЕЙСАМ")
    print("=" * 80)

    for h_res, l_res in zip(heuristic_results, llm_results):
        case = next(c for c in STRESS_TEST_CASES if c.id == h_res.test_id)
        print(f"\n--- КЕЙС #{case.id:02d} [{case.category}] Отрасль: {case.industry} ---")
        print(f"Текст: \"{case.text}\"")
        print(f"  * Heuristic Score: {h_res.score_percent:5.1f}% ({h_res.passed_checks}/{h_res.total_checks} проверок) за {h_res.elapsed_sec*1000:.1f} мс")
        print(f"  * LLM Score:       {l_res.score_percent:5.1f}% ({l_res.passed_checks}/{l_res.total_checks} проверок) за {l_res.elapsed_sec:.2f} с")

        # Ошибки эвристики
        heu_errors = [d for d in h_res.details if not d.is_correct]
        if heu_errors:
            print("    [Ошибки Heuristic]:")
            for err in heu_errors:
                print(f"      - {err.field_name}: {err.error_message} (Ожидалось: {err.expected!r}, Получено: {err.actual!r})")

        # Ошибки LLM
        llm_errors = [d for d in l_res.details if not d.is_correct]
        if llm_errors:
            print("    [Ошибки LLM]:")
            for err in llm_errors:
                print(f"      - {err.field_name}: {err.error_message} (Ожидалось: {err.expected!r}, Получено: {err.actual!r})")

        if not heu_errors and not llm_errors:
            print("    [БЕЗУПРЕЧНО]: Оба движка извлекли все параметры со 100% точностью!")

    # =========================================================================
    # СВОДНАЯ СТАТИСТИКА ПО КАТЕГОРИЯМ
    # =========================================================================
    print("\n" + "=" * 80)
    print("  ИТОГОВАЯ ТАБЛИЦА ТОЧНОСТИ ПО КАТЕГОРИЯМ")
    print("=" * 80)

    categories = list(dict.fromkeys(c.category for c in STRESS_TEST_CASES))
    print(f"{'Категория':<28} | {'Heuristic Accuracy':<20} | {'LLM Accuracy':<15} | {'Delta':<10}")
    print("-" * 80)

    total_heu_passed = sum(r.passed_checks for r in heuristic_results)
    total_heu_checks = sum(r.total_checks for r in heuristic_results)
    total_llm_passed = sum(r.passed_checks for r in llm_results)
    total_llm_checks = sum(r.total_checks for r in llm_results)

    for cat in categories:
        cat_h = [r for r in heuristic_results if r.category == cat]
        cat_l = [r for r in llm_results if r.category == cat]

        h_pct = (sum(r.passed_checks for r in cat_h) / sum(r.total_checks for r in cat_h)) * 100.0
        l_pct = (sum(r.passed_checks for r in cat_l) / sum(r.total_checks for r in cat_l)) * 100.0
        delta = l_pct - h_pct

        print(f"{cat:<28} | {h_pct:6.1f}%              | {l_pct:6.1f}%         | {delta:+5.1f}%")

    print("-" * 80)
    total_h_pct = (total_heu_passed / total_heu_checks) * 100.0
    total_l_pct = (total_llm_passed / total_llm_checks) * 100.0
    print(f"{'ИТОГО ПО ВСЕМ 20 КЕЙСАМ':<28} | {total_h_pct:6.1f}% ({total_heu_passed}/{total_heu_checks}) | {total_l_pct:6.1f}% ({total_llm_passed}/{total_llm_checks}) | {total_l_pct - total_h_pct:+5.1f}%")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(run_stress_suite())
