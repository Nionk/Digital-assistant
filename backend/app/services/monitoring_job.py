import logging

import app.api.manager as manager_module
from app.core.database import async_session_maker
from app.services.scraper.runner import (
    is_scraper_busy,
    run_persisted_scraper_job,
    try_enqueue_scraper_run,
)

logger = logging.getLogger(__name__)


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

