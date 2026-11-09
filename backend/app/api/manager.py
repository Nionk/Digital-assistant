import datetime
import logging
from typing import Annotated, Literal

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
)
from sqlalchemy import delete, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import noload

from app.core.constants import normalize_city
from app.core.database import async_session_maker, get_async_session
from app.core.security import CurrentManagerDep
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
    EventUploadOut,
    ManagerDashboardOut,
    ManagerEventsCatalogOut,
    ManagerReplyIn,
    ManagerReplyOut,
    MatchRequestIn,
    MatchResponseOut,
    PublishSelectionIn,
    PublishSelectionOut,
    ScraperRunIn,
    ScraperRunOut,
    SelectionActivityOut,
    SelectionItemReactionActivity,
    SelectionQuestionActivity,
    TariffOptionOut,
)
from app.services.matcher import build_tariff_option, run_client_matching_pipeline
from app.services.scraper import (
    CUSTOMER_SOURCES_REGISTRY,
    ingest_smart_event,
    run_customer_sources_monitoring,
)
from app.services.telegram import format_monitoring_summary_alert, send_manager_alert

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/manager", tags=["Manager Cabinet"])

AsyncSessionDep = Annotated[AsyncSession, Depends(get_async_session)]
ManagerEventFormat = Literal[
    "roundtable", "business_breakfast", "forum", "conference", "session"
]
SelectionStatusLiteral = Literal["draft", "published"]
EventDataStatusLiteral = Literal["ready", "needs_enrichment", "archived"]


def _normalize_data_status(st: str | None) -> EventDataStatusLiteral:
    if st == "needs_enrichment":
        return "needs_enrichment"
    if st == "archived":
        return "archived"
    return "ready"


def _normalize_event_format(fmt: str | None) -> ManagerEventFormat:
    if fmt == "roundtable":
        return "roundtable"
    if fmt == "business_breakfast":
        return "business_breakfast"
    if fmt == "forum":
        return "forum"
    if fmt == "session":
        return "session"
    return "conference"


def _normalize_selection_status(st: str | None) -> SelectionStatusLiteral | None:
    if st == "draft":
        return "draft"
    if st == "published":
        return "published"
    return None


_is_scraper_running: bool = False


async def _execute_background_monitoring(source_key: str | None) -> None:
    """Фоновый воркер выполнения скрейпинга площадок с атомарным сбросом флага в finally."""
    global _is_scraper_running
    try:
        async with async_session_maker() as session:
            effective_key = None if source_key == "all" else source_key
            summary = await run_customer_sources_monitoring(session, source_key=effective_key)
            logger.info("Мониторинг площадок (%s) успешно завершен: %s", source_key, summary)
            alert_text = format_monitoring_summary_alert(
                ready_count=summary.ingested_ready_count,
                needs_enrichment_titles=summary.needs_enrichment_titles,
            )
            await send_manager_alert(alert_text)
    except Exception:
        logger.exception("Ошибка при выполнении фонового скрейпинга для источника '%s'", source_key)
    finally:
        _is_scraper_running = False

@router.get(
    "/clients",
    response_model=ManagerDashboardOut,
    summary="Список клиентов менеджера и алерты горящих дедлайнов Early Bird",
    description=(
        "Возвращает список закрепленных за менеджером клиентов со статусами их последних подборок "
        "и панель срочных алертов по мероприятиям с активными скидками раннего бронирования (Early Bird)."
    ),
)
# [AUDIT-CRUTCH]: Повышенная цикломатическая сложность (ранг C в complexity_report.txt) и неиспользуемый аргумент current_manager (dead_code.txt:209).
async def get_manager_clients(
    current_manager: CurrentManagerDep,
    db: AsyncSessionDep,
) -> ManagerDashboardOut:
    """
    Загружает из БД клиентов менеджера, статус их последней подборки (selections)
    и ближайшие горящие дедлайны скидок Early Bird из таблицы event_tariffs.
    """
    today = today_local()
    clients_out: list[ClientSummaryOut] = []
    burning_deadlines_out: list[BurningDeadlineOut] = []

    try:
        clients_stmt = (
            select(Client)
            .where(Client.manager_id == current_manager.id)
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
                sel_status = _normalize_selection_status(latest_sel.status)
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
    except (SQLAlchemyError, OSError) as exc:
        logger.error("Ошибка БД при запросе /clients: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="База данных временно недоступна",
        ) from exc

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
# [AUDIT-BACKDOOR]: Аргумент current_manager не используется (dead_code.txt:337) — не проверяется принадлежность client_id текущему менеджеру (IDOR).
async def match_events_for_client(
    client_id: int,
    payload: MatchRequestIn,
    current_manager: CurrentManagerDep,
    db: AsyncSessionDep,
) -> MatchResponseOut:
    """
    Запускает полный пайплайн D-06 и D-07: от сырой заметки до готовых пакетов и письма.
    """
    # Защита от IDOR: проверяем, что клиент существует и закреплен за текущим менеджером
    try:
        client = await db.get(Client, client_id)
    except (SQLAlchemyError, OSError) as exc:
        logger.error("Ошибка БД при проверке клиента %s: %s", client_id, exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="База данных временно недоступна",
        ) from exc

    if client is None or client.manager_id != current_manager.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Клиент с ID={client_id} не найден или закреплен за другим менеджером.",
        )

    try:
        return await run_client_matching_pipeline(
            session=db,
            client_id=client_id,
            payload=payload,
        )
    except HTTPException:
        raise
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except (SQLAlchemyError, OSError) as exc:
        if isinstance(exc, TimeoutError):
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail=f"Превышено время ожидания внешнего ИИ-шлюза: {exc}",
            ) from exc
        logger.error("Ошибка БД при вызове /match: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="База данных временно недоступна",
        ) from exc
    except Exception as exc:
        try:
            await db.rollback()
        except (SQLAlchemyError, OSError) as rb_exc:
            logger.warning("Ошибка отката транзакции в /match: %s", rb_exc)
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
    db: AsyncSessionDep,
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

    stmt = select(Selection).where(Selection.id == selection_id)
    selection = None
    try:
        result = await db.execute(stmt)
        selection = result.scalar_one_or_none()
    except (SQLAlchemyError, OSError) as exc:
        logger.error("Ошибка БД при публикации подборки %s: %s", selection_id, exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="База данных временно недоступна",
        ) from exc

    if selection is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Подборка не найдена")

    # Защита от IDOR: проверяем принадлежность подборки клиенту текущего менеджера
    client = await db.get(Client, selection.client_id)
    if client is None or client.manager_id != current_manager.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Подборка не найдена или закреплена за другим менеджером",
        )

    today = today_local()
    total_price = 0.0
    total_savings = 0.0
    validated_pairs: list[tuple[int, int, str | None]] = []

    # Пакетная валидация всех (event_id, tariff_id) без N+1 запросов к БД
    event_ids = {item_in.event_id for item_in in payload.final_items}
    tariff_ids = {item_in.tariff_id for item_in in payload.final_items}

    events_stmt = select(Event).where(Event.id.in_(event_ids))
    events_res = await db.execute(events_stmt)
    events_by_id = {e.id: e for e in events_res.scalars().all()}

    tariffs_stmt = select(EventTariff).where(EventTariff.id.in_(tariff_ids))
    tariffs_res = await db.execute(tariffs_stmt)
    tariffs_by_id = {t.id: t for t in tariffs_res.scalars().all()}

    for item_in in payload.final_items:
        event = events_by_id.get(item_in.event_id)
        if not event:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Мероприятие с ID={item_in.event_id} не найдено",
            )

        tariff = tariffs_by_id.get(item_in.tariff_id)
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
# [AUDIT-STUB]: В роутере manager.py отсутствуют 4 обязательных эндпоинта из раздела 11.4 artifact.md (POST /events/upload-pdf, POST /scraper/run, GET /selections/{id}/activity, POST /selections/{id}/reply), а в GET /events нет параметров фильтрации по городу, датам, форматам и data_status.
# [AUDIT-CRUTCH]: Неиспользуемый аргумент current_manager (dead_code.txt:502).
async def get_manager_events_catalog(
    current_manager: CurrentManagerDep,
    db: AsyncSessionDep,
    city: str | None = None,
    event_format: ManagerEventFormat | None = None,
    data_status: EventDataStatusLiteral | None = None,
    date_from: datetime.date | None = None,
    date_to: datetime.date | None = None,
) -> ManagerEventsCatalogOut:
    """
    Загружает из БД все активные мероприятия и их тарифы для вкладки «База мероприятий» в кабинете менеджера.
    Поддерживает фильтрацию по городу, формату, статусу полноты карточки и диапазону дат.
    """
    today = today_local()
    events_out: list[CatalogEventItemOut] = []

    try:
        ev_stmt = select(Event).where(
            (Event.is_active.is_(True)) | (Event.data_status == "needs_enrichment")
        )
        if data_status is not None:
            ev_stmt = ev_stmt.where(Event.data_status == data_status)
        else:
            ev_stmt = ev_stmt.where(Event.data_status != "archived")

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
            db_tariffs = tar_res.scalars().all()

            for t in db_tariffs:
                tariffs_by_event.setdefault(t.event_id, []).append(build_tariff_option(t, today))

        for ev in db_events:
            fmt = _normalize_event_format(ev.event_format)
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
                    data_status=_normalize_data_status(ev.data_status),
                    missing_data_warnings=list(ev.missing_data_warnings or []),
                )
            )
    except (SQLAlchemyError, OSError) as exc:
        logger.error("Ошибка БД при запросе /events: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="База данных временно недоступна",
        ) from exc

    return ManagerEventsCatalogOut(
        total_count=len(events_out),
        events=events_out,
    )


@router.post(
    "/events/upload-pdf",
    response_model=EventUploadOut,
    summary="Ручной импорт и обогащение события через PDF-файл, текст или URL",
    description=(
        "Принимает PDF-брошюру (multipart), сырой текст или внешний URL. "
        "Выполняет извлечение структуры через Instructor, сохраняет мероприятие и тарифы в БД."
    ),
)
async def upload_event_material(
    current_manager: CurrentManagerDep,
    db: AsyncSessionDep,
    file: Annotated[UploadFile | None, File()] = None,
    raw_text: Annotated[str | None, Form()] = None,
    source_url: Annotated[str | None, Form()] = None,
) -> EventUploadOut:
    pdf_bytes: bytes | None = None
    if file is not None:
        pdf_bytes = await file.read()
        if not pdf_bytes:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Загруженный файл пуст.",
            )

    has_raw = bool(raw_text and raw_text.strip())
    has_url = bool(source_url and source_url.strip())
    if not pdf_bytes and not has_raw and not has_url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Необходимо передать либо PDF-файл, либо текстовый конспект/регламент, либо ссылку на карточку мероприятия.",
        )

    try:
        event = await ingest_smart_event(
            session=db,
            source_url=source_url.strip() if source_url and source_url.strip() else None,
            raw_text=raw_text.strip() if raw_text and raw_text.strip() else None,
            pdf_bytes=pdf_bytes,
        )
        tariffs_count = await db.scalar(
            select(func.count(EventTariff.id)).where(EventTariff.event_id == event.id)
        ) or 0

        return EventUploadOut(
            event_id=event.id,
            canonical_title=event.canonical_title,
            data_status=event.data_status or "ready",
            tariffs_count=tariffs_count,
            message="Мероприятие успешно импортировано и сохранено в базе знаний.",
        )
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.error("Ошибка структурирования и сохранения события: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка обработки мероприятия: {exc}",
        ) from exc


@router.post(
    "/scraper/run",
    response_model=ScraperRunOut,
    summary="Ручной запуск парсера по одной из утвержденных площадок",
    description="Ставит в очередь фоновую задачу скрейпинга для выбранного источника.",
)
async def run_scraper_endpoint(
    payload: ScraperRunIn,
    background_tasks: BackgroundTasks,
    current_manager: CurrentManagerDep,
) -> ScraperRunOut:
    global _is_scraper_running

    valid_sources = {s.source_key for s in CUSTOMER_SOURCES_REGISTRY} | {"all"}
    if payload.source_key not in valid_sources:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Неизвестный источник '{payload.source_key}'. Допустимые: {', '.join(sorted(valid_sources))}",
        )

    if _is_scraper_running:
        return ScraperRunOut(
            source_key=payload.source_key,
            status="queued",
            message="Задача мониторинга уже выполняется или поставлена в очередь. Повторный запуск отклонен.",
        )

    _is_scraper_running = True
    background_tasks.add_task(_execute_background_monitoring, payload.source_key)

    return ScraperRunOut(
        source_key=payload.source_key,
        status="queued",
        message=f"Фоновая задача сбора данных для '{payload.source_key}' успешно поставлена в очередь.",
    )


@router.get(
    "/selections/{selection_id}/activity",
    response_model=SelectionActivityOut,
    summary="Получение реакций клиента и вопросов, требующих внимания менеджера (Polling)",
    description=(
        "Возвращает реакции клиента по элементам витрины и вопросы в чате со статусом needs_manager_attention = True. "
        "Защищен проверкой принадлежности подборки текущему менеджеру (IDOR)."
    ),
)
async def get_selection_activity(
    selection_id: int,
    current_manager: CurrentManagerDep,
    db: AsyncSessionDep,
) -> SelectionActivityOut:
    selection = await db.get(Selection, selection_id)
    if selection is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Подборка не найдена")

    client = await db.get(Client, selection.client_id)
    if client is None or client.manager_id != current_manager.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Подборка не найдена или закреплена за другим менеджером",
        )

    # 1. Реакции клиента по мероприятиям
    items_stmt = select(SelectionItem, Event).join(
        Event, SelectionItem.event_id == Event.id
    ).where(SelectionItem.selection_id == selection_id)
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

    # 2. Вопросы клиента, требующие внимания менеджера
    chat_stmt = select(ChatMessage, Event).outerjoin(
        Event, ChatMessage.event_id == Event.id
    ).where(
        ChatMessage.selection_id == selection_id,
        ChatMessage.needs_manager_attention.is_(True),
    ).order_by(ChatMessage.created_at.asc())
    chat_res = await db.execute(chat_stmt)
    question_items: list[SelectionQuestionActivity] = []
    for msg, event in chat_res.all():
        question_items.append(
            SelectionQuestionActivity(
                message_id=msg.id,
                event_id=msg.event_id,
                event_title=event.canonical_title if event else None,
                question_text=msg.message_text,
                created_at=str(msg.created_at) if msg.created_at else None,
            )
        )

    return SelectionActivityOut(
        selection_id=selection_id,
        reactions=reaction_items,
        pending_questions=question_items,
    )


@router.post(
    "/selections/{selection_id}/reply",
    response_model=ManagerReplyOut,
    summary="Отправка ответа менеджера на вопрос клиента в чат витрины",
    description=(
        "Сбрасывает флаг needs_manager_attention у исходного вопроса и публикует "
        "ответное сообщение менеджера (sender_role = 'manager') в чат витрины."
    ),
)
async def reply_to_client_question(
    selection_id: int,
    payload: ManagerReplyIn,
    current_manager: CurrentManagerDep,
    db: AsyncSessionDep,
) -> ManagerReplyOut:
    selection = await db.get(Selection, selection_id)
    if selection is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Подборка не найдена")

    client = await db.get(Client, selection.client_id)
    if client is None or client.manager_id != current_manager.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Подборка не найдена или закреплена за другим менеджером",
        )

    target_msg = await db.get(ChatMessage, payload.message_id)
    if target_msg is None or target_msg.selection_id != selection_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Сообщение #{payload.message_id} не найдено в указанной подборке.",
        )

    # Сбрасываем флаг ожидания внимания у исходного вопроса
    target_msg.needs_manager_attention = False

    # Добавляем ответное сообщение от менеджера
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
