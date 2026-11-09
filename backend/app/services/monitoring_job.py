import logging

import app.api.manager as manager_module
from app.core.database import async_session_maker
from app.services.scraper import run_customer_sources_monitoring
from app.services.telegram import format_monitoring_summary_alert, send_manager_alert

logger = logging.getLogger(__name__)


async def run_nightly_monitoring_job() -> None:
    """
    Фоновый регламентный джоб ночного мониторинга 9 площадок (get_data.md, Способ Б).
    Запускается планировщиком APScheduler при ENABLE_SCHEDULER=true.
    """
    if manager_module._is_scraper_running:
        logger.info("Пропуск планового ночного мониторинга: задача скрейпинга уже выполняется.")
        return

    manager_module._is_scraper_running = True
    logger.info("Запуск планового фонового мониторинга площадок...")
    try:
        async with async_session_maker() as session:
            summary = await run_customer_sources_monitoring(session)
        logger.info(
            "Мониторинг завершен: проверено источников=%d, новых=%d (готово=%d, требует проверки=%d)",
            summary.checked_sources,
            summary.discovered_urls,
            summary.ingested_ready_count,
            summary.needs_enrichment_count,
        )
        alert_text = format_monitoring_summary_alert(
            ready_count=summary.ingested_ready_count,
            needs_enrichment_titles=summary.needs_enrichment_titles,
        )
        await send_manager_alert(alert_text)
    except Exception:
        logger.exception("Ошибка при выполнении ночного мониторинга площадок")
    finally:
        manager_module._is_scraper_running = False

