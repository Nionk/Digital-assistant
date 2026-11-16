import datetime
import logging
from collections import defaultdict
from dataclasses import dataclass
from typing import Literal

from pydantic import ValidationError
from sqlalchemy import delete, exists, select
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
    BundleEventItemOut,
    BundleVariantOut,
    BurningDeadlineOut,
    CatalogEventItemOut,
    ClientCreateIn,
    ClientQueryExtracted,
    ClientSummaryOut,
    ClientUpdateIn,
    ClientWorkspaceOut,
    ManagerDashboardOut,
    ManagerEventsCatalogOut,
    ManagerReplyIn,
    ManagerReplyOut,
    PublishSelectionIn,
    PublishSelectionOut,
    SelectionActivityOut,
    SelectionItemReactionActivity,
    SelectionQuestionActivity,
    SelectionResolvedQuestionActivity,
    SelectionResolvedReplyOut,
    TariffOptionOut,
    WorkspaceSelectionOut,
)
from app.services.matcher import build_tariff_option

logger = logging.getLogger(__name__)

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


def _format_iso_ts(dt: object) -> str | None:
    """Преобразует дату/время ORM в ISO-строку или None."""
    if dt is None:
        return None
    if isinstance(dt, datetime.datetime):
        return dt.isoformat()
    return str(dt)


def _build_client_summary(
    client: Client,
    latest_sel: Selection | None,
) -> ClientSummaryOut:
    """Собирает сводную карточку клиента из ORM-моделей Client и Selection."""
    sel_status: SelectionStatusLiteral | None = None
    sel_token = None
    if latest_sel is not None:
        sel_status = normalize_selection_status(latest_sel.status)
        if latest_sel.status == "published":
            sel_token = latest_sel.magic_token

    return ClientSummaryOut(
        id=client.id,
        company_name=client.company_name,
        contact_person=client.contact_person,
        raw_manager_notes=client.raw_manager_notes,
        is_active=bool(client.is_active),
        latest_selection_id=latest_sel.id if latest_sel else None,
        latest_selection_status=sel_status,
        magic_token=sel_token,
    )


def _parse_extracted_profile(raw_profile: object) -> ClientQueryExtracted | None:
    """Безопасно валидирует JSONB extracted_profile клиента без падения при устаревших/пустых данных."""
    if not isinstance(raw_profile, dict) or not raw_profile:
        return None
    try:
        return ClientQueryExtracted.model_validate(raw_profile)
    except ValidationError:
        logger.warning("Поврежденный extracted_profile в БД; возвращается None.", exc_info=True)
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

    await verify_client_owned_by_manager(db, selection.client_id, manager_id)
    return selection


async def list_manager_clients_dashboard(
    db: AsyncSession,
    manager_id: int,
    *,
    include_archived: bool = False,
) -> ManagerDashboardOut:
    """
    Загружает клиентов менеджера со статусами последних подборок и до 5 ближайших
    горящих дедлайнов скидок Early Bird (в горизонте 3 дней).
    """
    today = today_local()
    clients_out: list[ClientSummaryOut] = []

    clients_stmt = select(Client).where(Client.manager_id == manager_id)
    if not include_archived:
        clients_stmt = clients_stmt.where(Client.is_active.is_(True))
    clients_stmt = clients_stmt.order_by(Client.id.asc())

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
        clients_out.append(_build_client_summary(c, latest_sel_by_client.get(c.id)))

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


async def create_manager_client(
    db: AsyncSession,
    manager_id: int,
    payload: ClientCreateIn,
) -> ClientSummaryOut:
    """Создает нового клиента, закрепляя его за текущим менеджером."""
    client = Client(
        manager_id=manager_id,
        company_name=payload.company_name,
        contact_person=payload.contact_person,
        raw_manager_notes=payload.raw_manager_notes or "",
        extracted_profile={},
        is_active=True,
    )
    db.add(client)
    await db.commit()
    await db.refresh(client)
    return _build_client_summary(client, None)


async def update_manager_client(
    db: AsyncSession,
    client_id: int,
    manager_id: int,
    payload: ClientUpdateIn,
) -> ClientSummaryOut:
    """Обновляет поля клиента или выполняет мягкую архивацию/восстановление (is_active)."""
    client = await verify_client_owned_by_manager(db, client_id, manager_id)

    fields_set = payload.model_fields_set
    if "company_name" in fields_set and payload.company_name is not None:
        client.company_name = payload.company_name
    if "contact_person" in fields_set:
        client.contact_person = payload.contact_person
    if "raw_manager_notes" in fields_set:
        client.raw_manager_notes = payload.raw_manager_notes or ""
    if "is_active" in fields_set and payload.is_active is not None:
        client.is_active = payload.is_active

    await db.commit()
    await db.refresh(client)

    sel_stmt = (
        select(Selection)
        .options(noload("*"))
        .where(Selection.client_id == client.id)
        .order_by(Selection.created_at.desc(), Selection.id.desc())
        .limit(1)
    )
    latest_sel = (await db.execute(sel_stmt)).scalar_one_or_none()
    return _build_client_summary(client, latest_sel)


def _resolve_workspace_item_tariffs(
    item: SelectionItem,
    event_tariffs: list[TariffOptionOut],
) -> tuple[TariffOptionOut, list[TariffOptionOut]]:
    """
    Подбирает recommended_tariff и available_tariffs для сохраненной позиции подборки.
    Гарантирует отсутствие 500 при изменении/удалении тарифов или архивации события.
    """
    available = list(event_tariffs)
    recommended: TariffOptionOut | None = None

    if item.recommended_tariff_id is not None:
        recommended = next(
            (t for t in available if t.tariff_id == item.recommended_tariff_id),
            None,
        )

    if recommended is None and available:
        low_rationale = (item.ai_rationale or "").lower()
        if "спикер" in low_rationale or "выступлен" in low_rationale:
            recommended = next(
                (t for t in available if t.participation_role == "speaker"),
                None,
            )
        if recommended is None:
            priced = [t for t in available if t.actual_price is not None]
            recommended = (
                min(priced, key=lambda t: float(t.actual_price or 0.0))
                if priced
                else available[0]
            )

    if recommended is None:
        fallback = TariffOptionOut(
            tariff_id=0,
            tariff_name="Тариф уточняется (архивирован или обновлен)",
            participation_role="delegate",
            base_price=None,
            early_bird_price=None,
            early_bird_deadline=None,
            actual_price=None,
            savings=0.0,
            included_benefits="Тарифы мероприятия были изменены в каталоге.",
        )
        return fallback, [fallback]

    return recommended, available


async def get_client_workspace(
    db: AsyncSession,
    client_id: int,
    manager_id: int,
) -> ClientWorkspaceOut:
    """
    Возвращает серверное состояние рабочего пространства клиента: профиль и последнюю подборку
    (draft или published) с восстановленными пакетами для гидратации секций 01-03.
    """
    client = await verify_client_owned_by_manager(db, client_id, manager_id)
    extracted_profile = _parse_extracted_profile(client.extracted_profile)

    sel_stmt = (
        select(Selection)
        .options(noload("*"))
        .where(
            Selection.client_id == client.id,
            Selection.status.in_(("draft", "published")),
            exists(select(1).where(SelectionItem.selection_id == Selection.id)),
        )
        .order_by(Selection.created_at.desc(), Selection.id.desc())
        .limit(1)
    )
    target_selection = (await db.execute(sel_stmt)).scalar_one_or_none()
    if target_selection is None:
        return ClientWorkspaceOut(
            client_id=client.id,
            company_name=client.company_name,
            contact_person=client.contact_person,
            raw_manager_notes=client.raw_manager_notes,
            is_active=bool(client.is_active),
            extracted_profile=extracted_profile,
            selection=None,
        )

    items_stmt = (
        select(SelectionItem)
        .options(noload("*"))
        .where(SelectionItem.selection_id == target_selection.id)
        .order_by(SelectionItem.bundle_group.asc(), SelectionItem.id.asc())
    )
    sel_items = (await db.execute(items_stmt)).scalars().all()

    event_ids = sorted({it.event_id for it in sel_items})
    events_by_id: dict[int, Event] = {}
    tariffs_by_event: dict[int, list[TariffOptionOut]] = defaultdict(list)
    today = today_local()

    if event_ids:
        ev_res = await db.execute(
            select(Event).options(noload("*")).where(Event.id.in_(event_ids))
        )
        events_by_id = {e.id: e for e in ev_res.scalars().all()}

        tar_res = await db.execute(
            select(EventTariff)
            .where(EventTariff.event_id.in_(event_ids))
            .order_by(EventTariff.id.asc())
        )
        for t_orm in tar_res.scalars().all():
            tariffs_by_event[t_orm.event_id].append(build_tariff_option(t_orm, today))

    grouped_items: dict[int, list[BundleEventItemOut]] = defaultdict(list)
    for item in sel_items:
        ev = events_by_id.get(item.event_id)
        if ev is None:
            continue
        recommended, available = _resolve_workspace_item_tariffs(
            item, tariffs_by_event.get(ev.id, [])
        )
        primary_url = (
            str(ev.source_urls[0]) if (ev.source_urls and len(ev.source_urls) > 0) else None
        )
        ev_status: EventDataStatusLiteral = (
            "archived"
            if (not ev.is_active or ev.data_status == "archived")
            else normalize_data_status(ev.data_status)
        )
        group_num = 2 if item.bundle_group == 2 else 1
        grouped_items[group_num].append(
            BundleEventItemOut(
                event_id=ev.id,
                canonical_title=ev.canonical_title,
                event_format=normalize_event_format(ev.event_format),
                city=ev.city,
                is_online=bool(ev.is_online),
                venue=ev.venue,
                start_date=ev.start_date,
                end_date=ev.end_date,
                themes=list(ev.themes or []),
                recommended_tariff=recommended,
                available_tariffs=available,
                ai_rationale=item.ai_rationale or "",
                website_url=primary_url,
                data_status=ev_status,
                missing_data_warnings=list(ev.missing_data_warnings or []),
            )
        )

    sel_status = normalize_selection_status(target_selection.status) or "draft"
    budget_limit = (
        extracted_profile.total_budget_max
        if extracted_profile is not None
        else float(target_selection.total_budget_limit or 0.0)
    )

    bundle_variants_out: list[BundleVariantOut] = []
    for group_num in sorted(grouped_items.keys()):
        items_out = grouped_items[group_num]
        if not items_out:
            continue
        total_actual = round(
            sum(it.recommended_tariff.actual_price or 0.0 for it in items_out), 2
        )
        total_base = round(
            sum(
                (
                    it.recommended_tariff.base_price
                    if it.recommended_tariff.base_price is not None
                    else it.recommended_tariff.actual_price
                )
                or 0.0
                for it in items_out
            ),
            2,
        )
        total_savings = round(
            sum(it.recommended_tariff.savings or 0.0 for it in items_out), 2
        )
        deadlines = [
            it.recommended_tariff.early_bird_deadline
            for it in items_out
            if it.recommended_tariff.savings > 0
            and it.recommended_tariff.early_bird_deadline is not None
        ]
        is_over = budget_limit > 0 and total_actual > budget_limit
        if group_num == 1:
            bundle_title = (
                f"Утвержденный пакет ({len(items_out)} мероприятий)"
                if sel_status == "published"
                else f"Вариант 1: Максимальный охват тем ({len(items_out)} события)"
            )
        else:
            bundle_title = f"Вариант 2: Оптимальный по экономии бюджета ({len(items_out)} события)"

        bundle_variants_out.append(
            BundleVariantOut(
                bundle_group=group_num,
                bundle_title=bundle_title,
                items=items_out,
                total_actual_price=total_actual,
                total_base_price=total_base,
                total_savings=total_savings,
                earliest_deadline=min(deadlines) if deadlines else None,
                is_over_budget_tolerance=is_over,
            )
        )

    selection_out: WorkspaceSelectionOut | None = None
    if bundle_variants_out:
        selection_out = WorkspaceSelectionOut(
            selection_id=target_selection.id,
            status=sel_status,
            magic_token=target_selection.magic_token if sel_status == "published" else None,
            total_budget_limit=float(target_selection.total_budget_limit or 0.0),
            bundle_variants=bundle_variants_out,
            bonus_on_request_items=[],
            generated_pitch_text=target_selection.generated_pitch_text or "",
        )

    return ClientWorkspaceOut(
        client_id=client.id,
        company_name=client.company_name,
        contact_person=client.contact_person,
        raw_manager_notes=client.raw_manager_notes,
        is_active=bool(client.is_active),
        extracted_profile=extracted_profile,
        selection=selection_out,
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


@dataclass
class _ResolvedBucket:
    message_id: int
    event_id: int | None
    event_title: str | None
    question_text: str
    question_created_at: str | None
    replies: list[SelectionResolvedReplyOut]


def _find_legacy_target_client_message(
    turns_for_event: list[tuple[ChatMessage, Event | None]],
    replied_client_ids: set[int],
) -> tuple[ChatMessage, Event | None] | None:
    """Резервный поиск вопроса клиента для старых ответов менеджера с reply_to_message_id=None."""
    for c_msg, c_ev in reversed(turns_for_event):
        if c_msg.id not in replied_client_ids:
            return c_msg, c_ev
    return turns_for_event[-1] if turns_for_event else None


async def get_selection_activity_summary(
    db: AsyncSession,
    selection_id: int,
    manager_id: int,
) -> SelectionActivityOut:
    """
    Возвращает реакции клиента по элементам подборки, открытые вопросы (needs_manager_attention=True)
    и историю решенных вопросов с ответами куратора.
    """
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

    pending_stmt = (
        select(ChatMessage, Event)
        .outerjoin(Event, ChatMessage.event_id == Event.id)
        .where(
            ChatMessage.selection_id == selection_id,
            ChatMessage.sender_role == "client",
            ChatMessage.needs_manager_attention.is_(True),
        )
        .order_by(ChatMessage.created_at.asc(), ChatMessage.id.asc())
    )
    pending_res = await db.execute(pending_stmt)
    question_items: list[SelectionQuestionActivity] = [
        SelectionQuestionActivity(
            message_id=msg.id,
            event_id=msg.event_id,
            event_title=event.canonical_title if event else None,
            question_text=msg.message_text,
            created_at=_format_iso_ts(msg.created_at),
        )
        for msg, event in pending_res.all()
    ]

    history_stmt = (
        select(ChatMessage, Event)
        .outerjoin(Event, ChatMessage.event_id == Event.id)
        .where(
            ChatMessage.selection_id == selection_id,
            ChatMessage.sender_role.in_(("client", "manager")),
        )
        .order_by(ChatMessage.created_at.asc(), ChatMessage.id.asc())
    )
    history_res = await db.execute(history_stmt)

    client_msgs_by_id: dict[int, tuple[ChatMessage, Event | None]] = {}
    turns_by_event: dict[int | None, list[tuple[ChatMessage, Event | None]]] = defaultdict(list)
    replied_client_ids: set[int] = set()
    resolved_buckets: dict[int, _ResolvedBucket] = {}

    for msg, ev in history_res.all():
        if msg.sender_role == "client":
            client_msgs_by_id[msg.id] = (msg, ev)
            turns_by_event[msg.event_id].append((msg, ev))
        elif msg.sender_role == "manager":
            target_pair: tuple[ChatMessage, Event | None] | None = None
            if msg.reply_to_message_id is not None:
                target_pair = client_msgs_by_id.get(msg.reply_to_message_id)
            else:
                target_pair = _find_legacy_target_client_message(
                    turns_by_event.get(msg.event_id, []), replied_client_ids
                )

            reply_entry = SelectionResolvedReplyOut(
                reply_message_id=msg.id,
                reply_text=msg.message_text,
                created_at=_format_iso_ts(msg.created_at),
            )

            if target_pair is not None:
                q_msg, q_ev = target_pair
                replied_client_ids.add(q_msg.id)
                bucket_key = q_msg.id
                if bucket_key not in resolved_buckets:
                    resolved_buckets[bucket_key] = _ResolvedBucket(
                        message_id=q_msg.id,
                        event_id=q_msg.event_id,
                        event_title=q_ev.canonical_title if q_ev else None,
                        question_text=q_msg.message_text,
                        question_created_at=_format_iso_ts(q_msg.created_at),
                        replies=[],
                    )
            else:
                bucket_key = -msg.id
                resolved_buckets[bucket_key] = _ResolvedBucket(
                    message_id=msg.id,
                    event_id=msg.event_id,
                    event_title=ev.canonical_title if ev else None,
                    question_text="Прямой комментарий куратора",
                    question_created_at=None,
                    replies=[],
                )

            resolved_buckets[bucket_key].replies.append(reply_entry)

    resolved_items: list[SelectionResolvedQuestionActivity] = []
    for bucket in resolved_buckets.values():
        last_reply = bucket.replies[-1]
        resolved_items.append(
            SelectionResolvedQuestionActivity(
                message_id=bucket.message_id,
                event_id=bucket.event_id,
                event_title=bucket.event_title,
                question_text=bucket.question_text,
                question_created_at=bucket.question_created_at,
                replies=bucket.replies,
                latest_reply_text=last_reply.reply_text,
                replied_at=last_reply.created_at,
            )
        )

    resolved_items.sort(
        key=lambda item: (item.replied_at or "", item.replies[-1].reply_message_id),
        reverse=True,
    )

    return SelectionActivityOut(
        selection_id=selection_id,
        reactions=reaction_items,
        pending_questions=question_items,
        resolved_questions=resolved_items,
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

    if target_msg.sender_role != "client":
        raise WorkspaceValidationError(
            "Ответить можно только на вопрос клиента (sender_role='client')."
        )

    target_msg.needs_manager_attention = False

    reply_msg = ChatMessage(
        selection_id=selection_id,
        event_id=target_msg.event_id,
        reply_to_message_id=target_msg.id,
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
