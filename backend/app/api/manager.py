import datetime
import logging
from typing import Annotated

import httpx
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
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session_maker, get_async_session
from app.core.security import CurrentManagerDep
from app.models.models import EventTariff
from app.schemas.manager import (
    ClientCreateIn,
    ClientSummaryOut,
    ClientUpdateIn,
    ClientWorkspaceOut,
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
)
from app.services.manager_workspace import (
    EventDataStatusLiteral,
    ManagerEventFormat,
    WorkspaceNotFoundError,
    WorkspaceValidationError,
    create_manager_client,
    get_client_workspace,
    get_selection_activity_summary,
    list_catalog_events,
    list_manager_clients_dashboard,
    publish_selection_workspace,
    reply_to_client_question_workspace,
    update_manager_client,
    verify_client_owned_by_manager,
)
from app.services.matcher import run_client_matching_pipeline
from app.services.scraper import (
    CUSTOMER_SOURCES_REGISTRY,
    ingest_smart_event,
    run_customer_sources_monitoring,
)
from app.services.telegram import format_monitoring_summary_alert, send_manager_alert

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/manager", tags=["Manager Cabinet"])

AsyncSessionDep = Annotated[AsyncSession, Depends(get_async_session)]

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
async def get_manager_clients(
    current_manager: CurrentManagerDep,
    db: AsyncSessionDep,
    include_archived: bool = False,
) -> ManagerDashboardOut:
    """
    Загружает из БД клиентов менеджера, статус их последней подборки (selections)
    и ближайшие горящие дедлайны скидок Early Bird из таблицы event_tariffs.
    """
    try:
        return await list_manager_clients_dashboard(
            db, current_manager.id, include_archived=include_archived
        )
    except (SQLAlchemyError, OSError) as exc:
        logger.error("Ошибка БД при запросе /clients: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="База данных временно недоступна",
        ) from exc


@router.post(
    "/clients",
    response_model=ClientSummaryOut,
    status_code=status.HTTP_201_CREATED,
    summary="Создание новой карточки клиента менеджера",
    description="Создает нового активного клиента с привязкой к текущему авторизованному менеджеру.",
)
async def create_client_endpoint(
    payload: ClientCreateIn,
    current_manager: CurrentManagerDep,
    db: AsyncSessionDep,
) -> ClientSummaryOut:
    try:
        return await create_manager_client(db, current_manager.id, payload)
    except (SQLAlchemyError, OSError) as exc:
        logger.error("Ошибка БД при создании клиента: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="База данных временно недоступна",
        ) from exc


@router.patch(
    "/clients/{client_id}",
    response_model=ClientSummaryOut,
    summary="Редактирование карточки клиента и мягкая архивация/восстановление",
    description=(
        "Обновляет название компании, контактное лицо, конспект встречи или флаг is_active "
        "со строгой проверкой принадлежности клиента текущему менеджеру."
    ),
)
async def update_client_endpoint(
    client_id: int,
    payload: ClientUpdateIn,
    current_manager: CurrentManagerDep,
    db: AsyncSessionDep,
) -> ClientSummaryOut:
    try:
        return await update_manager_client(db, client_id, current_manager.id, payload)
    except WorkspaceNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except (SQLAlchemyError, OSError) as exc:
        logger.error("Ошибка БД при обновлении клиента %s: %s", client_id, exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="База данных временно недоступна",
        ) from exc


@router.get(
    "/clients/{client_id}/workspace",
    response_model=ClientWorkspaceOut,
    summary="Восстановление серверного рабочего состояния клиента (профиль, последняя подборка, КП)",
    description=(
        "Возвращает сохраненный профиль клиента (Client.extracted_profile) и последнюю "
        "подборку (draft или published) с восстановленными вариантами пакетов, тарифами и письмом КП."
    ),
)
async def get_client_workspace_endpoint(
    client_id: int,
    current_manager: CurrentManagerDep,
    db: AsyncSessionDep,
) -> ClientWorkspaceOut:
    try:
        return await get_client_workspace(db, client_id, current_manager.id)
    except WorkspaceNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except (SQLAlchemyError, OSError) as exc:
        logger.error("Ошибка БД при загрузке workspace клиента %s: %s", client_id, exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="База данных временно недоступна",
        ) from exc


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
    db: AsyncSessionDep,
) -> MatchResponseOut:
    """
    Запускает полный пайплайн D-06 и D-07: от сырой заметки до готовых пакетов и письма.
    """
    try:
        await verify_client_owned_by_manager(db, client_id, current_manager.id)
    except WorkspaceNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except (SQLAlchemyError, OSError) as exc:
        logger.error("Ошибка БД при проверке клиента %s: %s", client_id, exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="База данных временно недоступна",
        ) from exc

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
    try:
        return await publish_selection_workspace(db, selection_id, current_manager.id, payload)
    except WorkspaceValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except WorkspaceNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except (SQLAlchemyError, OSError) as exc:
        logger.error("Ошибка БД при публикации подборки %s: %s", selection_id, exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="База данных временно недоступна",
        ) from exc


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
    try:
        return await list_catalog_events(
            db,
            city=city,
            event_format=event_format,
            data_status=data_status,
            date_from=date_from,
            date_to=date_to,
        )
    except (SQLAlchemyError, OSError) as exc:
        logger.error("Ошибка БД при запросе /events: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="База данных временно недоступна",
        ) from exc


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
    except httpx.InvalidURL as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Передан некорректный URL источника: {exc}",
        ) from exc
    except httpx.HTTPError as exc:
        logger.warning("Ошибка загрузки внешнего URL при импорте события: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Не удалось загрузить страницу мероприятия по указанному URL.",
        ) from exc
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
    try:
        return await get_selection_activity_summary(db, selection_id, current_manager.id)
    except WorkspaceNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


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
    try:
        return await reply_to_client_question_workspace(
            db, selection_id, current_manager.id, payload
        )
    except WorkspaceValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except WorkspaceNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
