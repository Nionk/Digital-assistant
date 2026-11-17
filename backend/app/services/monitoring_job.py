import datetime
import logging

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

import app.api.manager as manager_module
from app.core.database import async_session_maker
from app.models.models import Event
from app.services.scraper.ingestion import _get_app_today
from app.services.scraper.runner import (
    is_scraper_busy,
    run_persisted_scraper_job,
    try_enqueue_scraper_run,
)

logger = logging.getLogger(__name__)


async def archive_past_events(session: AsyncSession, grace_days: int = 1) -> int:
    """
    Переводит прошедшие мероприятия (end_date < today - grace_days)
    со статусом != 'archived' в архив (is_active=False, data_status='archived').
    """
    cutoff = _get_app_today() - datetime.timedelta(days=grace_days)
    stmt = (
        update(Event)
        .where(Event.end_date < cutoff, Event.data_status != "archived")
        .values(is_active=False, data_status="archived")
    )
    res = await session.execute(stmt)
    await session.commit()
    return int(getattr(res, "rowcount", 0) or 0)


async def run_nightly_monitoring_job() -> None:
    """
    Фоновый регламентный джоб ночного мониторинга площадок (get_data.md, Способ Б).
    Запускается планировщиком APScheduler при ENABLE_SCHEDULER=true.
    """
    if await is_scraper_busy():
        logger.info("Пропуск планового ночного мониторинга: задача скрейпинга уже выполняется.")
        return

    logger.info("Запуск планового фонового мониторинга площадок...")
    run_id: int | None = None
    try:
        async with async_session_maker() as session:
            archived_count = await archive_past_events(session)
            if archived_count > 0:
                logger.info("Авто-архивировано прошедших мероприятий: %d", archived_count)
            run_row, _ = await try_enqueue_scraper_run(
                session,
                target_source_key="all",
                triggered_by="scheduler",
            )
            if run_row is None:
                logger.info("Пропуск планового ночного мониторинга: активный прогон уже есть в БД.")
                return
            run_id = run_row.id
    except Exception:
        logger.exception("Ошибка при инициализации ночного мониторинга площадок")
        return

    try:
        await run_persisted_scraper_job(
            run_id,
            "all",
            dry_run=False,
        )
    finally:
        manager_module._is_scraper_running = False

