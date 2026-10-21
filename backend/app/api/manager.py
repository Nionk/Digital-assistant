from datetime import date
from uuid import UUID
from fastapi import APIRouter, status

from app.core.security import CurrentManagerDep
from app.schemas.manager import (
    ManagerDashboardOut,
    ClientSummaryOut,
    BurningDeadlineOut,
    MatchRequestIn,
    MatchResponseOut,
    ClientQueryExtracted,
    BundleVariantOut,
    BundleEventItemOut,
    TariffOptionOut,
    PublishSelectionIn,
    PublishSelectionOut,
)

router = APIRouter(prefix="/api/manager", tags=["Manager Cabinet"])


@router.get(
    "/clients",
    response_model=ManagerDashboardOut,
    summary="Список клиентов менеджера и алерты горящих дедлайнов Early Bird",
    description=(
        "Возвращает список закрепленных за менеджером клиентов со статусами их подборок "
        "и панель срочных алертов по мероприятиям, где скидка раннего бронирования сгорает в течение 72 часов."
    ),
)
async def get_manager_clients(current_manager: CurrentManagerDep) -> ManagerDashboardOut:
    """
    Эндпоинт дашборда менеджера.
    На этапе Демо возвращает реалистичные данные для демонстрации интерфейса.
    В задаче D-08 переключается на выборку из БД (таблицы clients, selections, event_tariffs).
    """
    return ManagerDashboardOut(
        clients=[
            ClientSummaryOut(
                id=1,
                company_name="ГК «Пионер»",
                contact_person="Игорь Ветров (Директор по развитию)",
                raw_manager_notes=(
                    "Созвонились с ГК Пионер. Ищут на ноябрь-декабрь в Москве или СПб 3 небольших мероприятия "
                    "(круглые столы или закрытые завтраки) по теме КРТ и урбанистики. Хотят выступить спикером "
                    "хотя бы на одном. Общий бюджет — потолок 400 тыс. руб."
                ),
                latest_selection_id=10,
                latest_selection_status="published",
                magic_token=UUID("550e8400-e29b-41d4-a716-446655440000"),
            ),
            ClientSummaryOut(
                id=2,
                company_name="Девелопмент-Юг",
                contact_person="Елена Смирнова (PR-директор)",
                raw_manager_notes=(
                    "Нужны 2 региональные сессии по ИЖС и мастер-планированию на конец осени. "
                    "Только делегатами, бюджет до 150 000 руб."
                ),
                latest_selection_id=None,
                latest_selection_status=None,
                magic_token=None,
            ),
            ClientSummaryOut(
                id=3,
                company_name="Брусника. Сибирь",
                contact_person="Максим Ковалев (Руководитель проектного офиса)",
                raw_manager_notes=(
                    "Интересует онлайн-конференция по BIM и цифровизации стройки, а также очный форум в Москве. "
                    "Бюджет до 250 000 руб, обязательно делегатское участие с доступом к закрытому нетворкингу."
                ),
                latest_selection_id=11,
                latest_selection_status="draft",
                magic_token=None,
            ),
        ],
        burning_deadlines=[
            BurningDeadlineOut(
                event_id=101,
                event_title="Круглый стол Ведомостей: Практика КРТ в мегаполисах 2026",
                early_bird_deadline=date(2026, 11, 15),
                potential_savings=25000.0,
            ),
            BurningDeadlineOut(
                event_id=104,
                event_title="Всероссийский конгресс девелоперов: Стандарты КРТ и комфортная среда",
                early_bird_deadline=date(2026, 11, 18),
                potential_savings=35000.0,
            ),
        ],
    )


@router.post(
    "/clients/{client_id}/match",
    response_model=MatchResponseOut,
    summary="Извлечение профиля из заметки (NER), сборка 2 вариантов пакетов и генерация черновика КП",
    description=(
        "Принимает заметку менеджера, проводит NER-экстракцию профиля потребностей, "
        "выполняет детерминированный подбор двух вариантов пакета (максимальная релевантность и максимальная экономия), "
        "добавляет бонусные слоты 'Цена по запросу' и генерирует текст сопроводительного письма."
    ),
)
async def match_events_for_client(
    client_id: int,
    payload: MatchRequestIn,
    current_manager: CurrentManagerDep,
) -> MatchResponseOut:
    """
    Эндпоинт запуска алгоритма подбора.
    В задачах D-06 и D-07 сюда интегрируются profiler.py (Instructor LLM) и matcher.py (SQL RRF + Python комбинаторика).
    """
    # 1. Извлеченный профиль (или переопределенный менеджером в UI)
    extracted = payload.override_profile or ClientQueryExtracted(
        cities=["Москва", "Санкт-Петербург"],
        include_online=True,
        date_from=date(2026, 11, 1),
        date_to=date(2026, 12, 25),
        total_budget_max=400000.0,
        target_events_count=3,
        preferred_formats=["roundtable", "business_breakfast"],
        required_roles=["speaker", "delegate"],
        min_speaker_events=1,
        themes_keywords=["КРТ", "урбанистика", "жилая застройка"],
        semantic_search_query="Комплексное развитие территорий КРТ урбанистика жилая застройка девелопмент круглый стол",
    )

    # 2. Образцы тарифов
    sample_speaker_tariff = TariffOptionOut(
        tariff_id=501,
        tariff_name="Пакет «Спикер круглого стола»",
        participation_role="speaker",
        base_price=160000.0,
        early_bird_price=135000.0,
        early_bird_deadline=date(2026, 11, 15),
        actual_price=135000.0,
        savings=25000.0,
        included_benefits="Выступление 15 минут в основной панели, упоминание в пост-релизе Ведомостей, 2 делегатских билета.",
    )

    sample_delegate_tariff_1 = TariffOptionOut(
        tariff_id=502,
        tariff_name="Участие делегата",
        participation_role="delegate",
        base_price=90000.0,
        early_bird_price=75000.0,
        early_bird_deadline=date(2026, 11, 20),
        actual_price=75000.0,
        savings=15000.0,
        included_benefits="Доступ ко всем сессиям, закрытый нетворкинг-завтрак с застройщиками, аналитические материалы.",
    )

    sample_delegate_tariff_2 = TariffOptionOut(
        tariff_id=503,
        tariff_name="Делегатский билет (Офлайн + Видеозаписи)",
        participation_role="delegate",
        base_price=90000.0,
        early_bird_price=75000.0,
        early_bird_deadline=date(2026, 11, 25),
        actual_price=75000.0,
        savings=15000.0,
        included_benefits="Полный доступ к залам конференции, кофе-брейки, доступ к базе контактов участников в мобильном приложении.",
    )

    sample_on_request_tariff = TariffOptionOut(
        tariff_id=504,
        tariff_name="Партнерский слот сессии",
        participation_role="sponsor",
        base_price=None,
        early_bird_price=None,
        early_bird_deadline=None,
        actual_price=None,
        savings=0.0,
        included_benefits="Эксклюзивный статус соорганизатора отраслевой сессии, брендинг зала и спикерский слот.",
    )

    # 3. Карточки мероприятий
    item_1 = BundleEventItemOut(
        event_id=101,
        canonical_title="Круглый стол Ведомостей: Практика КРТ в мегаполисах 2026",
        event_format="roundtable",
        city="Москва",
        is_online=False,
        venue="Отель Континенталь, Тверская 22",
        start_date=date(2026, 11, 24),
        end_date=date(2026, 11, 24),
        themes=["КРТ", "девелопмент", "регулирование"],
        recommended_tariff=sample_speaker_tariff,
        available_tariffs=[sample_speaker_tariff, sample_delegate_tariff_1],
        ai_rationale="Прямое попадание в тему КРТ. Закрывает вашу потребность выступить спикером перед целевой аудиторией застройщиков Москвы.",
    )

    item_2 = BundleEventItemOut(
        event_id=102,
        canonical_title="Деловой завтрак Коммерсантъ: Урбанистика и мастер-планирование",
        event_format="business_breakfast",
        city="Санкт-Петербург",
        is_online=False,
        venue="Гранд Отель Европа",
        start_date=date(2026, 12, 4),
        end_date=date(2026, 12, 4),
        themes=["урбанистика", "мастер-планирование"],
        recommended_tariff=sample_delegate_tariff_1,
        available_tariffs=[sample_delegate_tariff_1],
        ai_rationale="Камерный формат закрытого завтрака в СПб, позволяет установить прямые контакты с градостроительным блоком.",
    )

    item_3 = BundleEventItemOut(
        event_id=103,
        canonical_title="Конференция ЕРЗ.РФ: Тренды жилой недвижимости итоги года",
        event_format="conference",
        city="Москва",
        is_online=False,
        venue="ЦДП (Цифровое деловое пространство)",
        start_date=date(2026, 12, 11),
        end_date=date(2026, 12, 11),
        themes=["жилая застройка", "ЕРЗ", "аналитика"],
        recommended_tariff=sample_delegate_tariff_2,
        available_tariffs=[sample_delegate_tariff_2],
        ai_rationale="Ключевая площадка застройщиков РФ для подведения итогов года в рамках оставшегося лимита бюджета.",
    )

    bonus_item = BundleEventItemOut(
        event_id=105,
        canonical_title="Всероссийский саммит девелоперов: Стратегии развития 2027",
        event_format="forum",
        city=None,
        is_online=True,
        venue="Платформа трансляции РБК Конференции",
        start_date=date(2026, 12, 18),
        end_date=date(2026, 12, 18),
        themes=["стратегии", "инвестиции", "макроэкономика"],
        recommended_tariff=sample_on_request_tariff,
        available_tariffs=[sample_on_request_tariff],
        ai_rationale="Флагманский онлайн-саммит лидеров строительной отрасли. Тариф формируется по персональному согласованию с оргкомитетом.",
    )

    # 4. Варианты пакетов
    variant_1 = BundleVariantOut(
        bundle_group=1,
        bundle_title="Вариант 1: Максимальный охват тем (1 Спикер + 2 Делегата)",
        items=[item_1, item_2, item_3],
        total_actual_price=285000.0,
        total_base_price=340000.0,
        total_savings=55000.0,
        earliest_deadline=date(2026, 11, 15),
        is_over_budget_tolerance=False,
    )

    variant_2 = BundleVariantOut(
        bundle_group=2,
        bundle_title="Вариант 2: Оптимальный по экономии бюджета (2 события)",
        items=[item_1, item_2],
        total_actual_price=210000.0,
        total_base_price=250000.0,
        total_savings=40000.0,
        earliest_deadline=date(2026, 11, 15),
        is_over_budget_tolerance=False,
    )

    return MatchResponseOut(
        selection_id=10,
        client_id=client_id,
        extracted_profile=extracted,
        bundle_variants=[variant_1, variant_2],
        bonus_on_request_items=[bonus_item],
        generated_pitch_text=(
            "Игорь, добрый день! По итогам нашего разговора подготовили для ГК «Пионер» программу участия "
            "на ноябрь–декабрь по темам КРТ и урбанистики в Москве и Санкт-Петербурге.\n\n"
            "В основной пакет из 3 мероприятий включили выступление спикером на профильном круглом столе «Ведомостей» "
            "(24 ноября) и делегатское участие в закрытом завтраке «Коммерсантъ» и итоговой конференции ЕРЗ.РФ.\n\n"
            "Общая стоимость пакета составляет 285 000 ₽ (вместо 340 000 ₽) — мы укладываемся значительно ниже вашего "
            "потолка в 400 000 ₽. При подтверждении до 15 ноября вы фиксируете скидку Early Bird в размере 55 000 ₽."
        ),
    )


@router.put(
    "/selections/{selection_id}/publish",
    response_model=PublishSelectionOut,
    status_code=status.HTTP_200_OK,
    summary="Фиксация выбранного пакета, сохранение текста КП и выпуск публичной ссылки Magic Link",
    description=(
        "Атомарно фиксирует утвержденный менеджером вариант пакета, удаляет альтернативный черновик, "
        "переводит статус подборки в 'published' и возвращает уникальный UUIDv4 токен витрины."
    ),
)
async def publish_selection(
    selection_id: int,
    payload: PublishSelectionIn,
    current_manager: CurrentManagerDep,
) -> PublishSelectionOut:
    """
    Эндпоинт публикации витрины.
    В задаче D-08 выполняет транзакционное обновление БД.
    """
    token = UUID("550e8400-e29b-41d4-a716-446655440000")
    return PublishSelectionOut(
        selection_id=selection_id,
        status="published",
        magic_token=token,
        public_showcase_url=f"/s/{token}",
        total_package_price=285000.0,
        total_package_savings=55000.0,
    )
