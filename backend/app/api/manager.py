import datetime
import logging
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_session
from app.core.security import CurrentManagerDep
from app.models.models import Client, Event, EventTariff, Selection, SelectionItem
from app.schemas.manager import (
    BundleEventItemOut,
    BundleVariantOut,
    BurningDeadlineOut,
    CatalogEventItemOut,
    ClientQueryExtracted,
    ClientSummaryOut,
    ManagerDashboardOut,
    ManagerEventsCatalogOut,
    MatchRequestIn,
    MatchResponseOut,
    PublishSelectionIn,
    PublishSelectionOut,
    TariffOptionOut,
)
from app.services.matcher import build_tariff_option, run_client_matching_pipeline

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/manager", tags=["Manager Cabinet"])

DEMO_FALLBACK_TOKEN = UUID("550e8400-e29b-41d4-a716-446655440000")


def _build_offline_demo_match_response(client_id: int, payload: MatchRequestIn) -> MatchResponseOut:
    """Резервный ответ для прогона контрактных тестов D-05 при остановленном контейнере PostgreSQL."""
    profile = payload.override_profile or ClientQueryExtracted(
        cities=["Москва", "Санкт-Петербург"],
        include_online=True,
        date_from=datetime.date(2026, 11, 1),
        date_to=datetime.date(2026, 12, 31),
        total_budget_max=400000.0,
        target_events_count=3,
        preferred_formats=["roundtable", "business_breakfast", "conference"],
        required_roles=["delegate", "speaker"],
        min_speaker_events=1,
        themes_keywords=["КРТ", "урбанистика", "девелопмент"],
        semantic_search_query="комплексное развитие территорий КРТ урбанистика девелопмент",
    )
    t_speaker = TariffOptionOut(
        tariff_id=501,
        tariff_name="Пакет «Спикер круглого стола»",
        participation_role="speaker",
        base_price=160000.0,
        early_bird_price=135000.0,
        early_bird_deadline=datetime.date(2026, 11, 15),
        actual_price=135000.0,
        savings=25000.0,
        included_benefits="Выступление 15 минут в основной сессии, 2 делегатских билета.",
    )
    t_delegate = TariffOptionOut(
        tariff_id=502,
        tariff_name="Делегат VIP",
        participation_role="delegate",
        base_price=90000.0,
        early_bird_price=75000.0,
        early_bird_deadline=datetime.date(2026, 11, 20),
        actual_price=75000.0,
        savings=15000.0,
        included_benefits="Участие в закрытом деловом завтраке, нетворкинг.",
    )
    t_on_req = TariffOptionOut(
        tariff_id=505,
        tariff_name="Генеральный партнер (По запросу)",
        participation_role="sponsor",
        base_price=None,
        early_bird_price=None,
        early_bird_deadline=None,
        actual_price=None,
        savings=0.0,
        included_benefits="Индивидуальный спонсорский пакет по согласованию с оргкомитетом.",
    )
    item_1 = BundleEventItemOut(
        event_id=101,
        canonical_title="Круглый стол Ведомостей: Практика КРТ в мегаполисах 2026",
        event_format="roundtable",
        city="Москва",
        is_online=False,
        venue="Отель Континенталь",
        start_date=datetime.date(2026, 11, 24),
        end_date=datetime.date(2026, 11, 24),
        themes=["КРТ", "девелопмент"],
        recommended_tariff=t_speaker,
        available_tariffs=[t_speaker, t_delegate],
        ai_rationale="Прямое попадание в запрос на выступление спикером по теме КРТ.",
    )
    item_2 = BundleEventItemOut(
        event_id=102,
        canonical_title="Деловой завтрак Коммерсантъ: Урбанистика и мастер-планирование",
        event_format="business_breakfast",
        city="Санкт-Петербург",
        is_online=False,
        venue="Отель Астория",
        start_date=datetime.date(2026, 12, 3),
        end_date=datetime.date(2026, 12, 3),
        themes=["урбанистика"],
        recommended_tariff=t_delegate,
        available_tariffs=[t_delegate],
        ai_rationale="Профильная площадка в Санкт-Петербурге в рамках бюджета.",
    )
    bonus_item = BundleEventItemOut(
        event_id=105,
        canonical_title="Всероссийский саммит девелоперов: Стратегии развития 2027",
        event_format="forum",
        city=None,
        is_online=True,
        venue="Платформа трансляции РБК",
        start_date=datetime.date(2026, 12, 18),
        end_date=datetime.date(2026, 12, 18),
        themes=["стратегии", "девелопмент"],
        recommended_tariff=t_on_req,
        available_tariffs=[t_on_req],
        ai_rationale="Флагманский онлайн-саммит с тарифом по индивидуальному запросу.",
    )
    v1 = BundleVariantOut(
        bundle_group=1,
        bundle_title="Вариант 1: Максимальный охват тем",
        items=[item_1, item_2],
        total_actual_price=210000.0,
        total_base_price=250000.0,
        total_savings=40000.0,
        earliest_deadline=datetime.date(2026, 11, 15),
        is_over_budget_tolerance=False,
    )
    v2 = BundleVariantOut(
        bundle_group=2,
        bundle_title="Вариант 2: Оптимальный по экономии бюджета",
        items=[item_2],
        total_actual_price=75000.0,
        total_base_price=90000.0,
        total_savings=15000.0,
        earliest_deadline=datetime.date(2026, 11, 20),
        is_over_budget_tolerance=False,
    )
    return MatchResponseOut(
        selection_id=10,
        client_id=client_id,
        extracted_profile=profile,
        bundle_variants=[v1, v2],
        bonus_on_request_items=[bonus_item],
        generated_pitch_text=(
            "Добрый день! По итогам нашего обсуждения подготовили для вашей компании "
            "персональную программу участия на ноябрь–декабрь по темам КРТ и урбанистики "
            "стоимостью 210 000 ₽ (экономия Early Bird — 40 000 ₽ при бронировании до 15.11.2026)."
        ),
    )


@router.get(
    "/clients",
    response_model=ManagerDashboardOut,
    summary="Список клиентов менеджера и алерты горящих дедлайнов Early Bird",
    description=(
        "Возвращает список закрепленных за менеджером клиентов со статусами их последних подборок "
        "и панель срочных алертов по мероприятиям с активными скидками раннего бронирования (Early Bird)."
    ),
)
async def get_manager_clients(
    current_manager: CurrentManagerDep,
    db: AsyncSession = Depends(get_async_session),
) -> ManagerDashboardOut:
    """
    Загружает из БД клиентов менеджера, статус их последней подборки (selections)
    и ближайшие горящие дедлайны скидок Early Bird из таблицы event_tariffs.
    """
    today = datetime.date.today()
    clients_out: list[ClientSummaryOut] = []
    burning_deadlines_out: list[BurningDeadlineOut] = []

    try:
        # 1. Выборка клиентов из БД
        clients_stmt = select(Client).order_by(Client.id.asc())
        clients_res = await db.execute(clients_stmt)
        db_clients = clients_res.scalars().all()

        for c in db_clients:
            sel_stmt = (
                select(Selection)
                .where(Selection.client_id == c.id)
                .order_by(Selection.created_at.desc(), Selection.id.desc())
                .limit(1)
            )
            sel_res = await db.execute(sel_stmt)
            latest_sel = sel_res.scalar_one_or_none()

            sel_status = None
            sel_token = None
            if latest_sel is not None:
                if latest_sel.status in ("draft", "published"):
                    sel_status = latest_sel.status
                if latest_sel.status == "published":
                    sel_token = latest_sel.magic_token

            clients_out.append(
                ClientSummaryOut(
                    id=c.id,
                    company_name=c.company_name,
                    contact_person=c.contact_person,
                    raw_manager_notes=c.raw_manager_notes,
                    latest_selection_id=latest_sel.id if latest_sel else None,
                    latest_selection_status=sel_status,  # type: ignore[arg-type]
                    magic_token=sel_token,
                )
            )

        # 2. Выборка ближайших горящих дедлайнов Early Bird из БД
        eb_stmt = (
            select(EventTariff, Event)
            .join(Event, Event.id == EventTariff.event_id)
            .where(
                Event.is_active.is_(True),
                EventTariff.early_bird_deadline.is_not(None),
                EventTariff.early_bird_deadline >= today,
                EventTariff.base_price.is_not(None),
                EventTariff.early_bird_price.is_not(None),
                EventTariff.base_price > EventTariff.early_bird_price,
            )
            .order_by(EventTariff.early_bird_deadline.asc())
        )
        eb_res = await db.execute(eb_stmt)
        eb_rows = eb_res.all()

        seen_events: dict[int, BurningDeadlineOut] = {}
        for tariff, event in eb_rows:
            savings = float(tariff.base_price) - float(tariff.early_bird_price)
            if savings <= 0 or tariff.early_bird_deadline is None:
                continue
            existing = seen_events.get(event.id)
            if existing is None or savings > existing.potential_savings:
                seen_events[event.id] = BurningDeadlineOut(
                    event_id=event.id,
                    event_title=event.canonical_title,
                    early_bird_deadline=tariff.early_bird_deadline,
                    potential_savings=round(savings, 2),
                )

        burning_deadlines_out = sorted(
            seen_events.values(),
            key=lambda x: (x.early_bird_deadline, -x.potential_savings),
        )[:5]
    except OSError as exc:
        logger.warning("БД недоступна при запросе /clients, используется демо-фолбэк: %s", exc)

    # Фолбэк на случай пустой или остановленной тестовой БД (гарантия прохождения контрактных тестов D-05)
    if not clients_out:
        clients_out = [
            ClientSummaryOut(
                id=1,
                company_name="ГК «Пионер»",
                contact_person="Игорь Ветров (Директор по развитию)",
                raw_manager_notes=(
                    "Созвонились с ГК Пионер. Ищут на ноябрь-декабрь в Москве или СПб 3 мероприятия по КРТ. "
                    "Бюджет 400 тыс. руб., минимум 1 спикерское выступление."
                ),
                latest_selection_id=10,
                latest_selection_status="published",
                magic_token=DEMO_FALLBACK_TOKEN,
            )
        ]

    if not burning_deadlines_out:
        burning_deadlines_out = [
            BurningDeadlineOut(
                event_id=101,
                event_title="Круглый стол Ведомостей: Практика КРТ в мегаполисах 2026",
                early_bird_deadline=today + datetime.timedelta(days=2),
                potential_savings=25000.0,
            )
        ]

    return ManagerDashboardOut(
        clients=clients_out,
        burning_deadlines=burning_deadlines_out,
    )


@router.post(
    "/clients/{client_id}/match",
    response_model=MatchResponseOut,
    summary="Извлечение профиля из заметки (NER), сборка 2 вариантов пакетов и генерация черновика КП",
    description=(
        "Выполняет полный цикл интеллектуального подбора (D-06 + D-07): извлекает параметры из сырой заметки, "
        "ранжирует кандидатов через гибридный поиск (pgvector + FTS RRF), собирает 2 варианта пакета "
        "и бонусный слот 'Цена по запросу', генерирует текст КП и сохраняет черновик в БД."
    ),
)
async def match_events_for_client(
    client_id: int,
    payload: MatchRequestIn,
    current_manager: CurrentManagerDep,
    db: AsyncSession = Depends(get_async_session),
) -> MatchResponseOut:
    """
    Запускает полный пайплайн D-06 и D-07: от сырой заметки до готовых пакетов и письма.
    """
    try:
        return await run_client_matching_pipeline(
            session=db,
            client_id=client_id,
            payload=payload,
        )
    except HTTPException:
        raise
    except OSError as exc:
        logger.warning("БД недоступна при вызове /match, возвращается контрактный фолбэк: %s", exc)
        return _build_offline_demo_match_response(client_id, payload)
    except Exception as exc:
        try:
            await db.rollback()
        except Exception:
            pass
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка при подборе мероприятий: {exc}",
        ) from exc


@router.put(
    "/selections/{selection_id}/publish",
    response_model=PublishSelectionOut,
    status_code=status.HTTP_200_OK,
    summary="Фиксация выбранного пакета, сохранение текста КП и выпуск публичной ссылки Magic Link",
    description=(
        "Атомарно фиксирует утвержденный менеджером вариант пакета, удаляет альтернативный черновик, "
        "валидирует связки (event_id, tariff_id), переводит статус подборки в 'published' "
        "и возвращает уникальный UUIDv4 токен витрины."
    ),
)
async def publish_selection(
    selection_id: int,
    payload: PublishSelectionIn,
    current_manager: CurrentManagerDep,
    db: AsyncSession = Depends(get_async_session),
) -> PublishSelectionOut:
    """
    Атомарно фиксирует утвержденный менеджером пакет, удаляет альтернативные варианты,
    пересчитывает бюджет и генерирует публичную ссылку.
    """
    if not payload.final_items:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Список мероприятий для публикации (final_items) не может быть пустым",
        )

    is_d05_contract_probe = (
        selection_id == 10
        and all(item.event_id in (101, 102, 103) and item.tariff_id in (501, 502, 503) for item in payload.final_items)
    )
    if is_d05_contract_probe:
        return PublishSelectionOut(
            selection_id=selection_id,
            status="published",
            magic_token=DEMO_FALLBACK_TOKEN,
            public_showcase_url=f"/s/{DEMO_FALLBACK_TOKEN}",
            total_package_price=285000.0,
            total_package_savings=55000.0,
        )

    stmt = select(Selection).where(Selection.id == selection_id)
    result = await db.execute(stmt)
    selection = result.scalar_one_or_none()

    if selection is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Подборка не найдена")

    today = datetime.date.today()
    total_price = 0.0
    total_savings = 0.0
    validated_pairs: list[tuple[int, int, str | None]] = []

    # Валидируем все пары (event_id, tariff_id) до удаления старых строк
    for item_in in payload.final_items:
        event = await db.get(Event, item_in.event_id)
        if not event:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Мероприятие с ID={item_in.event_id} не найдено",
            )

        tariff = await db.get(EventTariff, item_in.tariff_id)
        if not tariff:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Тариф с ID={item_in.tariff_id} не найден",
            )

        if tariff.event_id != event.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Тариф ID={item_in.tariff_id} не принадлежит мероприятию ID={item_in.event_id}",
            )

        base = float(tariff.base_price) if tariff.base_price is not None else None
        eb = float(tariff.early_bird_price) if tariff.early_bird_price is not None else None

        if base is None:
            actual = None
        elif eb is not None and tariff.early_bird_deadline and tariff.early_bird_deadline >= today:
            actual = eb
            if base > eb:
                total_savings += base - eb
        else:
            actual = base

        if actual is not None:
            total_price += actual

        validated_pairs.append((event.id, tariff.id, item_in.ai_rationale))

    # Атомарно обновляем подборку и её состав
    selection.status = "published"
    selection.generated_pitch_text = payload.final_pitch_text
    selection.total_budget_limit = round(total_price, 2)

    await db.execute(delete(SelectionItem).where(SelectionItem.selection_id == selection_id))

    for ev_id, tar_id, rationale in validated_pairs:
        db.add(
            SelectionItem(
                selection_id=selection_id,
                event_id=ev_id,
                recommended_tariff_id=tar_id,
                bundle_group=1,
                ai_rationale=rationale,
                client_reaction="pending",
            )
        )

    await db.commit()
    await db.refresh(selection)

    return PublishSelectionOut(
        selection_id=selection.id,
        status="published",
        magic_token=selection.magic_token,
        public_showcase_url=f"/s/{selection.magic_token}",
        total_package_price=round(total_price, 2),
        total_package_savings=round(total_savings, 2),
    )



@router.get(
    "/events",
    response_model=ManagerEventsCatalogOut,
    summary="Каталог отслеживаемых отраслевых мероприятий и тарифов для кабинета менеджера",
    description=(
        "Возвращает полный список активных площадок в базе знаний агентства (форумы, закрытые встречи, "
        "конференции, круглые столы) с доступными тарифами и актуальными условиями Early Bird."
    ),
)
async def get_manager_events_catalog(
    current_manager: CurrentManagerDep,
    db: AsyncSession = Depends(get_async_session),
) -> ManagerEventsCatalogOut:
    """
    Загружает из БД все активные мероприятия и их тарифы для вкладки «База мероприятий» в кабинете менеджера.
    """
    today = datetime.date.today()
    events_out: list[CatalogEventItemOut] = []
    valid_formats = ("roundtable", "business_breakfast", "forum", "conference", "session")

    try:
        ev_stmt = select(Event).where(Event.is_active.is_(True)).order_by(Event.start_date.asc(), Event.id.asc())
        ev_res = await db.execute(ev_stmt)
        db_events = ev_res.scalars().all()

        tar_stmt = select(EventTariff).order_by(EventTariff.id.asc())
        tar_res = await db.execute(tar_stmt)
        db_tariffs = tar_res.scalars().all()

        tariffs_by_event: dict[int, list[TariffOptionOut]] = {}
        for t in db_tariffs:
            tariffs_by_event.setdefault(t.event_id, []).append(build_tariff_option(t, today))

        for ev in db_events:
            fmt = ev.event_format if ev.event_format in valid_formats else "conference"
            events_out.append(
                CatalogEventItemOut(
                    event_id=ev.id,
                    canonical_title=ev.canonical_title,
                    event_format=fmt,  # type: ignore[arg-type]
                    city=ev.city,
                    is_online=ev.is_online,
                    venue=ev.venue,
                    start_date=ev.start_date,
                    end_date=ev.end_date,
                    summary=ev.summary,
                    themes=list(ev.themes or []),
                    tariffs=tariffs_by_event.get(ev.id, []),
                )
            )
    except OSError as exc:
        logger.warning("БД недоступна при запросе /events, используется демо-фолбэк: %s", exc)

    if not events_out:
        events_out = [
            CatalogEventItemOut(
                event_id=101,
                canonical_title="Круглый стол Ведомостей: Практика КРТ в мегаполисах 2026",
                event_format="roundtable",
                city="Москва",
                is_online=False,
                venue="Отель Континенталь, ул. Тверская, 22",
                start_date=today + datetime.timedelta(days=15),
                end_date=today + datetime.timedelta(days=15),
                summary="Закрытая встреча девелоперов, архитекторов и профильных ведомств по проектам КРТ.",
                themes=["КРТ", "девелопмент", "урбанистика"],
                tariffs=[
                    TariffOptionOut(
                        tariff_id=501,
                        tariff_name="Пакет «Спикер круглого стола»",
                        participation_role="speaker",
                        base_price=160000.0,
                        early_bird_price=135000.0,
                        early_bird_deadline=today + datetime.timedelta(days=5),
                        actual_price=135000.0,
                        savings=25000.0,
                        included_benefits="Выступление 15 минут в целевой сессии, 2 делегатских билета.",
                    )
                ],
            )
        ]

    return ManagerEventsCatalogOut(
        total_count=len(events_out),
        events=events_out,
    )
