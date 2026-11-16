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
    Query,
    UploadFile,
    status,
)
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_async_session
from app.core.security import CurrentManagerDep
from app.models.models import EventTariff, ScraperRun, ScraperSource
from app.schemas.manager import (
    ClientCreateIn,
    ClientSummaryOut,
    ClientUpdateIn,
    ClientWorkspaceOut,
    EventUploadOut,
    GeneratePitchIn,
    GeneratePitchOut,
    ManagerDashboardOut,
    ManagerEventsCatalogOut,
    ManagerReplyIn,
    ManagerReplyOut,
    MatchRequestIn,
    MatchResponseOut,
    PublishSelectionIn,
    PublishSelectionOut,
    ScraperPreviewCandidateOut,
    ScraperRunDetailOut,
    ScraperRunIn,
    ScraperRunOut,
    ScraperRunsListOut,
    ScraperSourceCreateIn,
    ScraperSourceDeleteOut,
    ScraperSourceOut,
    ScraperSourcePreviewIn,
    ScraperSourcePreviewOut,
    ScraperSourceUpdateIn,
    SelectionActivityOut,
    slugify_source_key,
)
from app.services.manager_workspace import (
    EventDataStatusLiteral,
    ManagerEventFormat,
    WorkspaceNotFoundError,
    WorkspaceValidationError,
    create_manager_client,
    generate_selection_pitch_workspace,
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
    CaptchaBlockedError,
    CustomerSourceConfig,
    HttpCatalogSourceScraper,
    UnsafeUrlError,
    ensure_builtin_scraper_sources,
    ingest_smart_event,
    run_persisted_scraper_job,
    try_enqueue_scraper_run,
    validate_safe_public_url,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/manager", tags=["Manager Cabinet"])

AsyncSessionDep = Annotated[AsyncSession, Depends(get_async_session)]

_UPLOAD_PDF_CHUNK_SIZE: int = 256 * 1024
_is_scraper_running: bool = False


async def _execute_background_monitoring(
    source_key: str | None,
    *,
    run_id: int | None = None,
    dry_run: bool = False,
    max_urls_per_source: int | None = None,
) -> None:
    """Фоновый воркер выполнения скрейпинга площадок через единый координатор runner.py."""
    effective_key = source_key or "all"
    await run_persisted_scraper_job(
        run_id,
        effective_key,
        dry_run=dry_run,
        max_urls_per_source=max_urls_per_source,
    )


async def _ensure_and_commit_builtin_sources(db: AsyncSession) -> list[ScraperSource]:
    """Синхронизирует встроенные источники и коммитит новые записи (если они были добавлены)."""
    rows = await ensure_builtin_scraper_sources(db)
    session_new = getattr(db, "new", ())
    new_sources: list[ScraperSource] = []
    if isinstance(session_new, (list, tuple, set)) or hasattr(session_new, "__iter__"):
        try:
            new_sources = [obj for obj in session_new if isinstance(obj, ScraperSource)]
        except TypeError:
            new_sources = []
    if new_sources:
        await db.commit()
        for src_row in new_sources:
            await db.refresh(src_row)
    return sorted(rows, key=lambda r: (not bool(r.is_builtin), r.id or 0))


async def _validate_public_catalog_urls(urls: list[str]) -> None:
    """Проверяет список catalog_urls на SSRF перед сохранением или обходом."""
    for url in urls:
        try:
            await validate_safe_public_url(url)
        except UnsafeUrlError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            ) from exc


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


@router.post(
    "/selections/{selection_id}/pitch",
    response_model=GeneratePitchOut,
    status_code=status.HTTP_200_OK,
    summary="Живая перегенерация сопроводительного письма КП через ИИ",
    description=(
        "Валидирует выбранные пары (event_id, tariff_id) по БД, детерминированно пересчитывает "
        "стоимость, экономию Early Bird, ближайший дедлайн и календарные накладки в Python, "
        "после чего генерирует живое сопроводительное письмо через LLM (с откатом на шаблон при сбое)."
    ),
)
async def generate_selection_pitch(
    selection_id: int,
    payload: GeneratePitchIn,
    current_manager: CurrentManagerDep,
    db: AsyncSessionDep,
) -> GeneratePitchOut:
    """Перегенерирует сопроводительное письмо КП по актуальному составу конструктора."""
    try:
        return await generate_selection_pitch_workspace(
            db, selection_id, current_manager.id, payload
        )
    except WorkspaceValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except WorkspaceNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except (SQLAlchemyError, OSError) as exc:
        logger.error("Ошибка БД при генерации письма подборки %s: %s", selection_id, exc)
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
        max_bytes = settings.SCRAPER_MAX_PDF_BYTES
        limit_label = (
            f"{max_bytes // (1024 * 1024)} МБ"
            if max_bytes >= 1024 * 1024
            else f"{max_bytes} байт"
        )
        buf = bytearray()
        try:
            while True:
                chunk = await file.read(_UPLOAD_PDF_CHUNK_SIZE)
                if not chunk:
                    break
                if len(buf) + len(chunk) > max_bytes:
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=f"Размер PDF-файла превышает допустимый лимит ({limit_label}).",
                    )
                buf.extend(chunk)
        finally:
            await file.close()

        if not buf:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Загруженный файл пуст.",
            )
        pdf_bytes = bytes(buf)

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
    summary="Ручной запуск парсера по площадке из БД или по всем активным сразу",
    description="Проверяет источник в таблице scraper_sources, создает запись ScraperRun и ставит задачу в фон.",
)
async def run_scraper_endpoint(
    payload: ScraperRunIn,
    background_tasks: BackgroundTasks,
    current_manager: CurrentManagerDep,
    db: AsyncSessionDep,
) -> ScraperRunOut:
    try:
        source_rows = await _ensure_and_commit_builtin_sources(db)
        if payload.source_key != "all":
            target_row = next(
                (r for r in source_rows if r.source_key == payload.source_key),
                None,
            )
            if target_row is None:
                valid_keys = ", ".join(sorted(r.source_key for r in source_rows) + ["all"])
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Неизвестный источник '{payload.source_key}'. Допустимые: {valid_keys}",
                )
            if target_row.adapter_type == "manual_only":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Источник работает только в режиме ручного Умного импорта",
                )
            if not target_row.is_enabled:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Источник отключен в настройках",
                )

        triggered_by = "manual_dry_run" if payload.dry_run else "manual"
        run_row, active_run_id = await try_enqueue_scraper_run(
            db,
            target_source_key=payload.source_key,
            triggered_by=triggered_by,
        )
        if run_row is None:
            return ScraperRunOut(
                source_key=payload.source_key,
                status="queued",
                message="Задача мониторинга уже выполняется или поставлена в очередь. Повторный запуск отклонен.",
                run_id=active_run_id,
                dry_run=payload.dry_run,
            )
    except HTTPException:
        raise
    except (SQLAlchemyError, OSError) as exc:
        logger.error("Ошибка БД при запуске /scraper/run: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="База данных временно недоступна",
        ) from exc

    background_tasks.add_task(
        _execute_background_monitoring,
        payload.source_key,
        run_id=run_row.id,
        dry_run=payload.dry_run,
        max_urls_per_source=payload.max_urls_per_source,
    )

    return ScraperRunOut(
        source_key=payload.source_key,
        status="queued",
        message=f"Фоновая задача сбора данных для '{payload.source_key}' успешно поставлена в очередь.",
        run_id=run_row.id,
        dry_run=payload.dry_run,
    )


@router.get(
    "/scraper/sources",
    response_model=list[ScraperSourceOut],
    summary="Список всех источников мониторинга (встроенных и пользовательских)",
)
async def list_scraper_sources(
    current_manager: CurrentManagerDep,
    db: AsyncSessionDep,
) -> list[ScraperSourceOut]:
    try:
        rows = await _ensure_and_commit_builtin_sources(db)
        return [ScraperSourceOut.model_validate(row) for row in rows]
    except (SQLAlchemyError, OSError) as exc:
        logger.error("Ошибка БД при запросе /scraper/sources: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="База данных временно недоступна",
        ) from exc


@router.post(
    "/scraper/sources",
    response_model=ScraperSourceOut,
    status_code=status.HTTP_201_CREATED,
    summary="Создание новой пользовательской площадки мониторинга",
)
async def create_scraper_source(
    payload: ScraperSourceCreateIn,
    current_manager: CurrentManagerDep,
    db: AsyncSessionDep,
) -> ScraperSourceOut:
    await _validate_public_catalog_urls(payload.catalog_urls)
    target_key = payload.source_key or slugify_source_key(payload.display_name)
    if target_key == "all":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ключ 'all' зарезервирован системой.",
        )

    try:
        existing_rows = await _ensure_and_commit_builtin_sources(db)
        if any(r.source_key == target_key for r in existing_rows):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Источник с ключом '{target_key}' уже существует.",
            )
        dup_res = await db.execute(
            select(ScraperSource).where(ScraperSource.source_key == target_key)
        )
        if dup_res.scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Источник с ключом '{target_key}' уже существует.",
            )

        effective_enabled = False if payload.adapter_type == "manual_only" else payload.is_enabled
        row = ScraperSource(
            source_key=target_key,
            display_name=payload.display_name,
            catalog_urls=list(payload.catalog_urls),
            adapter_type=payload.adapter_type,
            card_url_patterns=list(payload.card_url_patterns),
            exclude_url_patterns=list(payload.exclude_url_patterns),
            b2b_filter_enabled=payload.b2b_filter_enabled,
            russia_online_only=payload.russia_online_only,
            use_jina_reader=payload.use_jina_reader,
            encoding=payload.encoding,
            required_cookies=dict(payload.required_cookies),
            max_urls_per_run=payload.max_urls_per_run,
            is_enabled=effective_enabled,
            is_builtin=False,
        )
        db.add(row)
        try:
            await db.commit()
        except IntegrityError as exc:
            await db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Источник с ключом '{target_key}' уже существует.",
            ) from exc
        await db.refresh(row)
        return ScraperSourceOut.model_validate(row)
    except HTTPException:
        raise
    except (SQLAlchemyError, OSError) as exc:
        logger.error("Ошибка БД при создании источника '%s': %s", target_key, exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="База данных временно недоступна",
        ) from exc


@router.post(
    "/scraper/sources/preview",
    response_model=ScraperSourcePreviewOut,
    summary="Бесплатный предпросмотр Discovery по первому URL каталога (0 токенов LLM)",
)
async def preview_scraper_source(
    payload: ScraperSourcePreviewIn,
    current_manager: CurrentManagerDep,
) -> ScraperSourcePreviewOut:
    await _validate_public_catalog_urls(payload.catalog_urls)

    if payload.adapter_type == "manual_only":
        return ScraperSourcePreviewOut(
            discovered_count=0,
            checked_url=payload.catalog_urls[0],
            total_catalog_urls=len(payload.catalog_urls),
            error="Источник настроен в режиме manual_only: автоматический обход каталога отключен.",
        )

    preview_cfg = CustomerSourceConfig(
        source_key="preview",
        display_name="Preview",
        catalog_urls=(payload.catalog_urls[0],),
        card_url_patterns=tuple(payload.card_url_patterns),
        exclude_url_patterns=tuple(payload.exclude_url_patterns),
        adapter_type=payload.adapter_type,
        b2b_filter_enabled=payload.b2b_filter_enabled,
        russia_online_only=payload.russia_online_only,
        encoding=payload.encoding,
        use_jina_reader=payload.use_jina_reader,
        required_cookies=tuple(payload.required_cookies.items()),
    )

    try:
        discovery = await HttpCatalogSourceScraper().discover_catalog(preview_cfg)
    except UnsafeUrlError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except (CaptchaBlockedError, httpx.HTTPError, ValueError, RuntimeError, OSError) as exc:
        logger.warning("Ошибка предпросмотра Discovery (%s): %s", payload.catalog_urls[0], exc)
        return ScraperSourcePreviewOut(
            discovered_count=0,
            rejected_b2c=0,
            rejected_geo=0,
            sample_candidates=[],
            checked_url=payload.catalog_urls[0],
            total_catalog_urls=len(payload.catalog_urls),
            error=str(exc) or type(exc).__name__,
        )

    sample = [
        ScraperPreviewCandidateOut(
            url=cand.url,
            title=cand.title,
            snippet=cand.snippet,
            is_digest=cand.is_digest,
        )
        for cand in discovery.candidates[:10]
    ]
    return ScraperSourcePreviewOut(
        discovered_count=len(discovery.candidates),
        rejected_b2c=discovery.rejected_b2c,
        rejected_geo=discovery.rejected_geo,
        sample_candidates=sample,
        checked_url=payload.catalog_urls[0],
        total_catalog_urls=len(payload.catalog_urls),
        error=None,
    )


@router.patch(
    "/scraper/sources/{source_key}",
    response_model=ScraperSourceOut,
    summary="Обновление настроек источника мониторинга",
)
async def update_scraper_source(
    source_key: str,
    payload: ScraperSourceUpdateIn,
    current_manager: CurrentManagerDep,
    db: AsyncSessionDep,
) -> ScraperSourceOut:
    if payload.catalog_urls is not None:
        await _validate_public_catalog_urls(payload.catalog_urls)

    try:
        rows = await _ensure_and_commit_builtin_sources(db)
        row = next((r for r in rows if r.source_key == source_key), None)
        if row is None:
            res = await db.execute(
                select(ScraperSource).where(ScraperSource.source_key == source_key)
            )
            row = res.scalar_one_or_none()
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Источник '{source_key}' не найден.",
            )

        if row.source_key == "archdialog" and payload.adapter_type is not None and payload.adapter_type != "manual_only":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Площадка АрхДиалог (Timepad) работает только в режиме manual_only.",
            )

        effective_adapter = payload.adapter_type if payload.adapter_type is not None else row.adapter_type
        if effective_adapter == "manual_only" and payload.is_enabled is True:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Нельзя включить автоматический мониторинг для источника в режиме manual_only.",
            )

        updates = payload.model_dump(exclude_unset=True)
        for field_name, field_value in updates.items():
            setattr(row, field_name, field_value)

        if payload.adapter_type == "manual_only" and payload.is_enabled is None:
            row.is_enabled = False

        await db.commit()
        await db.refresh(row)
        return ScraperSourceOut.model_validate(row)
    except HTTPException:
        raise
    except (SQLAlchemyError, OSError) as exc:
        logger.error("Ошибка БД при обновлении источника '%s': %s", source_key, exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="База данных временно недоступна",
        ) from exc


@router.delete(
    "/scraper/sources/{source_key}",
    response_model=ScraperSourceDeleteOut,
    summary="Удаление пользовательской площадки мониторинга",
)
async def delete_scraper_source(
    source_key: str,
    current_manager: CurrentManagerDep,
    db: AsyncSessionDep,
) -> ScraperSourceDeleteOut:
    try:
        rows = await _ensure_and_commit_builtin_sources(db)
        row = next((r for r in rows if r.source_key == source_key), None)
        if row is None:
            res = await db.execute(
                select(ScraperSource).where(ScraperSource.source_key == source_key)
            )
            row = res.scalar_one_or_none()
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Источник '{source_key}' не найден.",
            )
        if row.is_builtin:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Встроенные площадки заказчика нельзя удалить, но можно отключить.",
            )

        await db.delete(row)
        await db.commit()
        return ScraperSourceDeleteOut(deleted=True, source_key=source_key)
    except HTTPException:
        raise
    except (SQLAlchemyError, OSError) as exc:
        logger.error("Ошибка БД при удалении источника '%s': %s", source_key, exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="База данных временно недоступна",
        ) from exc


@router.get(
    "/scraper/runs",
    response_model=ScraperRunsListOut,
    summary="История запусков парсера и статистика по площадкам",
)
async def list_scraper_runs(
    current_manager: CurrentManagerDep,
    db: AsyncSessionDep,
    limit: int = Query(default=10, ge=1, le=50),
) -> ScraperRunsListOut:
    try:
        res = await db.execute(
            select(ScraperRun).order_by(ScraperRun.id.desc()).limit(limit)
        )
        rows = list(res.scalars().all())
        return ScraperRunsListOut(
            items=[ScraperRunDetailOut.model_validate(r) for r in rows]
        )
    except (SQLAlchemyError, OSError) as exc:
        logger.error("Ошибка БД при запросе /scraper/runs: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="База данных временно недоступна",
        ) from exc


@router.get(
    "/scraper/runs/latest",
    response_model=ScraperRunDetailOut | None,
    summary="Последний (или текущий выполняемый) прогон парсера",
)
async def get_latest_scraper_run(
    current_manager: CurrentManagerDep,
    db: AsyncSessionDep,
) -> ScraperRunDetailOut | None:
    try:
        res = await db.execute(
            select(ScraperRun).order_by(ScraperRun.id.desc()).limit(1)
        )
        row = res.scalar_one_or_none()
        return ScraperRunDetailOut.model_validate(row) if row is not None else None
    except (SQLAlchemyError, OSError) as exc:
        logger.error("Ошибка БД при запросе /scraper/runs/latest: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="База данных временно недоступна",
        ) from exc


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
