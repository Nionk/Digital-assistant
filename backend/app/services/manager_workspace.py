import datetime
from typing import Literal

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import noload

from app.core.constants import normalize_city
from app.core.timeutils import today_local
from app.models.models import (
    ChatMessage,
    Client,
    Event,
    EventTariff,
    Selection,
    SelectionItem,
)
from app.schemas.manager import (
    BurningDeadlineOut,
    CatalogEventItemOut,
    ClientSummaryOut,
    ManagerDashboardOut,
    ManagerEventsCatalogOut,
    ManagerReplyIn,
    ManagerReplyOut,
    PublishSelectionIn,
    PublishSelectionOut,
    SelectionActivityOut,
    SelectionItemReactionActivity,
    SelectionQuestionActivity,
    TariffOptionOut,
)
from app.services.matcher import build_tariff_option

ManagerEventFormat = Literal[
    "roundtable", "business_breakfast", "forum", "conference", "session"
]
SelectionStatusLiteral = Literal["draft", "published"]
EventDataStatusLiteral = Literal["ready", "needs_enrichment", "archived"]


class WorkspaceNotFoundError(LookupError):
    """Запрошенная сущность не найдена или недоступна текущему менеджеру (HTTP 404)."""


class WorkspaceValidationError(ValueError):
    """Нарушение бизнес-ограничений при работе с подборкой или тарифами (HTTP 400)."""


def normalize_data_status(st: str | None) -> EventDataStatusLiteral:
    """Нормализует статус готовности карточки мероприятия к допустимому Literal-значению."""
    if st == "needs_enrichment":
        return "needs_enrichment"
    if st == "archived":
        return "archived"
    return "ready"


def normalize_event_format(fmt: str | None) -> ManagerEventFormat:
    """Нормализует формат мероприятия к допустимому Literal-значению кабинета менеджера."""
    if fmt == "roundtable":
        return "roundtable"
    if fmt == "business_breakfast":
        return "business_breakfast"
    if fmt == "forum":
        return "forum"
    if fmt == "session":
        return "session"
    return "conference"


def normalize_selection_status(st: str | None) -> SelectionStatusLiteral | None:
    """Нормализует статус подборки к 'draft' | 'published' или None."""
    if st == "draft":
        return "draft"
    if st == "published":
        return "published"
    return None


async def verify_client_owned_by_manager(
    db: AsyncSession,
    client_id: int,
    manager_id: int,
) -> Client:
    """Проверяет существование клиента и его принадлежность текущему менеджеру (защита от IDOR)."""
    client = await db.get(Client, client_id)
    if client is None or client.manager_id != manager_id:
        raise WorkspaceNotFoundError(
            f"Клиент с ID={client_id} не найден или закреплен за другим менеджером."
        )
    return client


async def _get_owned_selection(
    db: AsyncSession,
    selection_id: int,
    manager_id: int,
    *,
    use_select_stmt: bool = False,
) -> Selection:
    """Загружает подборку и проверяет, что её клиент закреплен за текущим менеджером (защита от IDOR)."""
    if use_select_stmt:
        result = await db.execute(select(Selection).where(Selection.id == selection_id))
        selection = result.scalar_one_or_none()
    else:
        selection = await db.get(Selection, selection_id)

    if selection is None:
        raise WorkspaceNotFoundError("Подборка не найдена")

    client = await db.get(Client, selection.client_id)
    if client is None or client.manager_id != manager_id:
        raise WorkspaceNotFoundError("Подборка не найдена или закреплена за другим менеджером")
    return selection


async def list_manager_clients_dashboard(
    db: AsyncSession,
    manager_id: int,
) -> ManagerDashboardOut:
    """
    Загружает клиентов менеджера со статусами последних подборок и до 5 ближайших
    горящих дедлайнов скидок Early Bird (в горизонте 3 дней).
    """
    today = today_local()
    clients_out: list[ClientSummaryOut] = []

    clients_stmt = (
        select(Client)
        .where(Client.manager_id == manager_id)
        .order_by(Client.id.asc())
    )
    clients_res = await db.execute(clients_stmt)
    db_clients = clients_res.scalars().all()

    client_ids = [c.id for c in db_clients]
    latest_sel_by_client: dict[int, Selection] = {}
    if client_ids:
        sels_stmt = (
            select(Selection)
            .options(noload("*"))
            .where(Selection.client_id.in_(client_ids))
            .order_by(Selection.created_at.desc(), Selection.id.desc())
        )
        sels_res = await db.execute(sels_stmt)
        for sel in sels_res.scalars().all():
            if sel.client_id not in latest_sel_by_client:
                latest_sel_by_client[sel.client_id] = sel

    for c in db_clients:
        latest_sel = latest_sel_by_client.get(c.id)
        sel_status: SelectionStatusLiteral | None = None
        sel_token = None
        if latest_sel is not None:
            sel_status = normalize_selection_status(latest_sel.status)
            if latest_sel.status == "published":
                sel_token = latest_sel.magic_token

        clients_out.append(
            ClientSummaryOut(
                id=c.id,
                company_name=c.company_name,
                contact_person=c.contact_person,
                raw_manager_notes=c.raw_manager_notes,
                latest_selection_id=latest_sel.id if latest_sel else None,
                latest_selection_status=sel_status,
                magic_token=sel_token,
            )
        )

    eb_stmt = (
        select(EventTariff, Event)
        .join(Event, Event.id == EventTariff.event_id)
        .where(
            Event.is_active.is_(True),
            Event.data_status == "ready",
            EventTariff.early_bird_deadline.is_not(None),
            EventTariff.early_bird_deadline >= today,
            EventTariff.early_bird_deadline <= today + datetime.timedelta(days=3),
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

    return ManagerDashboardOut(
        clients=clients_out,
        burning_deadlines=burning_deadlines_out,
    )


async def publish_selection_workspace(
    db: AsyncSession,
    selection_id: int,
    manager_id: int,
    payload: PublishSelectionIn,
) -> PublishSelectionOut:
    """
    Атомарно фиксирует утвержденный менеджером пакет, удаляет альтернативные варианты,
    пересчитывает итоговый бюджет/экономию и переводит подборку в статус 'published'.
    """
    if not payload.final_items:
        raise WorkspaceValidationError(
            "Список мероприятий для публикации (final_items) не может быть пустым"
        )

    selection = await _get_owned_selection(db, selection_id, manager_id, use_select_stmt=True)

    today = today_local()
    total_price = 0.0
    total_savings = 0.0
    validated_pairs: list[tuple[int, int, str | None]] = []

    # Пакетная валидация всех (event_id, tariff_id) без N+1 запросов к БД
    event_ids = {item_in.event_id for item_in in payload.final_items}
    tariff_ids = {item_in.tariff_id for item_in in payload.final_items}

    events_res = await db.execute(select(Event).where(Event.id.in_(event_ids)))
    events_by_id = {e.id: e for e in events_res.scalars().all()}

    tariffs_res = await db.execute(select(EventTariff).where(EventTariff.id.in_(tariff_ids)))
    tariffs_by_id = {t.id: t for t in tariffs_res.scalars().all()}

    for item_in in payload.final_items:
        event = events_by_id.get(item_in.event_id)
        if not event:
            raise WorkspaceValidationError(f"Мероприятие с ID={item_in.event_id} не найдено")

        tariff = tariffs_by_id.get(item_in.tariff_id)
        if not tariff:
            raise WorkspaceValidationError(f"Тариф с ID={item_in.tariff_id} не найден")

        if tariff.event_id != event.id:
            raise WorkspaceValidationError(
                f"Тариф ID={item_in.tariff_id} не принадлежит мероприятию ID={item_in.event_id}"
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


async def list_catalog_events(
    db: AsyncSession,
    *,
    city: str | None = None,
    event_format: ManagerEventFormat | None = None,
    data_status: EventDataStatusLiteral | None = None,
    date_from: datetime.date | None = None,
    date_to: datetime.date | None = None,
) -> ManagerEventsCatalogOut:
    """
    Загружает из БД мероприятия и их тарифы для вкладки «База мероприятий» в кабинете менеджера
    с фильтрацией по статусу, городу, формату и диапазону дат.
    """
    today = today_local()
    events_out: list[CatalogEventItemOut] = []

    ev_stmt = select(Event)
    if data_status is not None:
        ev_stmt = ev_stmt.where(Event.data_status == data_status)
        if data_status == "ready":
            ev_stmt = ev_stmt.where(Event.is_active.is_(True))
    else:
        ev_stmt = ev_stmt.where(
            (Event.is_active.is_(True)) | (Event.data_status == "needs_enrichment"),
            Event.data_status != "archived",
        )

    if city is not None and city.strip():
        clean_city = city.strip()
        if clean_city.lower() in ("онлайн", "online"):
            ev_stmt = ev_stmt.where(Event.is_online.is_(True))
        else:
            norm_city = normalize_city(clean_city)
            target_city = norm_city if norm_city else clean_city
            ev_stmt = ev_stmt.where(Event.city.ilike(target_city))

    if event_format is not None:
        ev_stmt = ev_stmt.where(Event.event_format == event_format)

    if date_from is not None:
        ev_stmt = ev_stmt.where(Event.end_date >= date_from)

    if date_to is not None:
        ev_stmt = ev_stmt.where(Event.start_date <= date_to)

    ev_stmt = ev_stmt.order_by(Event.start_date.asc(), Event.id.asc())
    ev_res = await db.execute(ev_stmt)
    db_events = ev_res.scalars().all()

    tariffs_by_event: dict[int, list[TariffOptionOut]] = {}
    if db_events:
        event_ids = [ev.id for ev in db_events]
        tar_stmt = (
            select(EventTariff)
            .where(EventTariff.event_id.in_(event_ids))
            .order_by(EventTariff.id.asc())
        )
        tar_res = await db.execute(tar_stmt)
        for t in tar_res.scalars().all():
            tariffs_by_event.setdefault(t.event_id, []).append(build_tariff_option(t, today))

    for ev in db_events:
        fmt = normalize_event_format(ev.event_format)
        primary_url = ev.source_urls[0] if (ev.source_urls and len(ev.source_urls) > 0) else None
        events_out.append(
            CatalogEventItemOut(
                event_id=ev.id,
                canonical_title=ev.canonical_title,
                event_format=fmt,
                city=ev.city,
                is_online=ev.is_online,
                venue=ev.venue,
                start_date=ev.start_date,
                end_date=ev.end_date,
                summary=ev.summary,
                themes=list(ev.themes or []),
                tariffs=tariffs_by_event.get(ev.id, []),
                website_url=primary_url,
                data_status=normalize_data_status(ev.data_status),
                missing_data_warnings=list(ev.missing_data_warnings or []),
            )
        )

    return ManagerEventsCatalogOut(
        total_count=len(events_out),
        events=events_out,
    )


async def get_selection_activity_summary(
    db: AsyncSession,
    selection_id: int,
    manager_id: int,
) -> SelectionActivityOut:
    """Возвращает реакции клиента по элементам подборки и вопросы, требующие внимания менеджера."""
    await _get_owned_selection(db, selection_id, manager_id)

    items_stmt = (
        select(SelectionItem, Event)
        .join(Event, SelectionItem.event_id == Event.id)
        .where(SelectionItem.selection_id == selection_id)
    )
    items_res = await db.execute(items_stmt)
    reaction_items: list[SelectionItemReactionActivity] = []
    for item, event in items_res.all():
        if item.client_reaction and item.client_reaction != "pending":
            reaction_items.append(
                SelectionItemReactionActivity(
                    item_id=item.id,
                    event_id=event.id,
                    event_title=event.canonical_title,
                    reaction=item.client_reaction,
                    comment=item.client_comment,
                )
            )

    chat_stmt = (
        select(ChatMessage, Event)
        .outerjoin(Event, ChatMessage.event_id == Event.id)
        .where(
            ChatMessage.selection_id == selection_id,
            ChatMessage.needs_manager_attention.is_(True),
        )
        .order_by(ChatMessage.created_at.asc())
    )
    chat_res = await db.execute(chat_stmt)
    question_items: list[SelectionQuestionActivity] = [
        SelectionQuestionActivity(
            message_id=msg.id,
            event_id=msg.event_id,
            event_title=event.canonical_title if event else None,
            question_text=msg.message_text,
            created_at=str(msg.created_at) if msg.created_at else None,
        )
        for msg, event in chat_res.all()
    ]

    return SelectionActivityOut(
        selection_id=selection_id,
        reactions=reaction_items,
        pending_questions=question_items,
    )


async def reply_to_client_question_workspace(
    db: AsyncSession,
    selection_id: int,
    manager_id: int,
    payload: ManagerReplyIn,
) -> ManagerReplyOut:
    """Сбрасывает needs_manager_attention у исходного вопроса и публикует ответ менеджера в чат."""
    await _get_owned_selection(db, selection_id, manager_id)

    target_msg = await db.get(ChatMessage, payload.message_id)
    if target_msg is None or target_msg.selection_id != selection_id:
        raise WorkspaceNotFoundError(
            f"Сообщение #{payload.message_id} не найдено в указанной подборке."
        )

    target_msg.needs_manager_attention = False

    reply_msg = ChatMessage(
        selection_id=selection_id,
        event_id=target_msg.event_id,
        sender_role="manager",
        message_text=payload.reply_text.strip(),
        needs_manager_attention=False,
    )
    db.add(reply_msg)
    await db.commit()
    await db.refresh(reply_msg)

    return ManagerReplyOut(
        message_id=target_msg.id,
        reply_message_id=reply_msg.id,
        success=True,
        message="Ответ менеджера успешно отправлен в витрину клиента.",
    )
