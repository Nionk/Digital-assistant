import asyncio
import datetime
import logging
from weakref import WeakKeyDictionary

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session_maker
from app.models.models import ScraperRun
from app.services.scraper.crawler import _filter_supported_kwargs
from app.services.scraper.monitoring import ScrapingRunSummary
from app.services.telegram import format_monitoring_summary_alert, send_manager_alert

logger = logging.getLogger(__name__)

_loop_scraper_locks: WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Lock] = (
    WeakKeyDictionary()
)
_loop_enqueue_locks: WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Lock] = (
    WeakKeyDictionary()
)


def _get_scraper_lock() -> asyncio.Lock:
    loop = asyncio.get_running_loop()
    lock = _loop_scraper_locks.get(loop)
    if lock is None:
        lock = asyncio.Lock()
        _loop_scraper_locks[loop] = lock
    return lock


def _get_enqueue_lock() -> asyncio.Lock:
    loop = asyncio.get_running_loop()
    lock = _loop_enqueue_locks.get(loop)
    if lock is None:
        lock = asyncio.Lock()
        _loop_enqueue_locks[loop] = lock
    return lock


def _is_inprocess_lock_held() -> bool:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return False
    lock = _loop_scraper_locks.get(loop)
    return bool(lock is not None and lock.locked())


async def recover_stale_scraper_runs(session: AsyncSession) -> int:
    """
    Переводит зависшие после падения/перезапуска записи ScraperRun со статусом queued/running
    в статус failed, чтобы не оставалось вечной блокировки запуска парсера.
    """
    res = await session.execute(
        select(ScraperRun).where(ScraperRun.status.in_(("queued", "running")))
    )
    stale_runs = [row for row in res.scalars().all() if isinstance(row, ScraperRun)]
    if not stale_runs:
        return 0

    now_ts = datetime.datetime.now(datetime.UTC)
    for run in stale_runs:
        run.status = "failed"
        run.error_message = "Прервано перезапуском сервера"
        run.finished_at = now_ts
    await session.commit()
    return len(stale_runs)


async def get_active_scraper_run_id(session: AsyncSession | None = None) -> int | None:
    """Возвращает ID последнего активного прогона (queued/running) в БД, если он есть."""
    if session is None:
        return None
    res = await session.execute(
        select(ScraperRun.id)
        .where(ScraperRun.status.in_(("queued", "running")))
        .order_by(ScraperRun.id.desc())
        .limit(1)
    )
    active_id = res.scalar_one_or_none()
    return int(active_id) if isinstance(active_id, int) else None


async def is_scraper_busy(session: AsyncSession | None = None) -> bool:
    """Проверяет внутрипроцессную блокировку и (опционально) активные прогоны в БД."""
    import app.api.manager as manager_module

    if getattr(manager_module, "_is_scraper_running", False) or _is_inprocess_lock_held():
        return True
    if session is not None:
        return (await get_active_scraper_run_id(session)) is not None
    return False


async def start_scraper_run_record(
    session: AsyncSession,
    *,
    target_source_key: str,
    triggered_by: str = "manual",
) -> ScraperRun:
    """Создает запись ScraperRun в статусе queued и фиксирует ее в БД."""
    run_row = ScraperRun(
        status="queued",
        target_source_key=target_source_key,
        triggered_by=triggered_by,
    )
    session.add(run_row)
    await session.commit()
    await session.refresh(run_row)
    return run_row


async def try_enqueue_scraper_run(
    session: AsyncSession,
    *,
    target_source_key: str,
    triggered_by: str = "manual",
) -> tuple[ScraperRun | None, int | None]:
    """
    Атомарная критическая секция постановки скрейпера в очередь:
    под _enqueue_lock проверяет is_scraper_busy, выставляет _is_scraper_running = True
    и создает запись ScraperRun(status='queued').
    Возвращает (run_row, None) при успехе или (None, active_run_id) при занятости.
    """
    import app.api.manager as manager_module

    async with _get_enqueue_lock():
        if await is_scraper_busy(session):
            return None, await get_active_scraper_run_id(session)

        manager_module._is_scraper_running = True
        try:
            run_row = await start_scraper_run_record(
                session,
                target_source_key=target_source_key,
                triggered_by=triggered_by,
            )
        except Exception:
            manager_module._is_scraper_running = False
            raise
        return run_row, None


def _apply_totals_to_run(
    run_row: ScraperRun,
    totals: dict[str, int],
    source_logs: list[dict[str, object]],
) -> None:
    run_row.sources_total = int(totals.get("sources_total", 0))
    run_row.sources_done = int(totals.get("sources_done", 0))
    run_row.urls_discovered = int(totals.get("urls_discovered", 0))
    run_row.events_created = int(totals.get("events_created", 0))
    run_row.events_updated = int(totals.get("events_updated", 0))
    run_row.rejected_b2c = int(totals.get("rejected_b2c", 0))
    run_row.rejected_geo = int(totals.get("rejected_geo", 0))
    run_row.rejected_past = int(totals.get("rejected_past", 0))
    run_row.errors_count = int(totals.get("errors_count", 0))
    run_row.source_logs = list(source_logs)


async def _persist_run_failed(run_id: int | None, error_message: str) -> None:
    """Переводит запись ScraperRun в статус failed и сохраняет причину ошибки."""
    if run_id is None:
        return
    try:
        async with async_session_maker() as err_session:
            row = await err_session.get(ScraperRun, run_id)
            if isinstance(row, ScraperRun):
                row.status = "failed"
                row.error_message = error_message[:1000]
                row.finished_at = datetime.datetime.now(datetime.UTC)
                await err_session.commit()
    except SQLAlchemyError:
        logger.exception(
            "Не удалось сохранить статус failed в scraper_runs (run_id=%s)",
            run_id,
        )


async def run_persisted_scraper_job(
    run_id: int | None,
    target_source_key: str,
    *,
    dry_run: bool = False,
    max_urls_per_source: int | None = None,
) -> ScrapingRunSummary | None:
    """
    Единый координатор выполнения фонового скрейпинга:
    - удерживает внутрипроцессный asyncio.Lock и синхронизирует manager._is_scraper_running;
    - переводит ScraperRun в running и сохраняет live-прогресс после каждой площадки;
    - по завершении фиксирует completed/failed и отправляет Telegram-сводку (если not dry_run).
    """
    import app.api.manager as manager_module
    import app.services.scraper as scraper_pkg

    lock = _get_scraper_lock()
    async with lock:
        manager_module._is_scraper_running = True
        accumulated_logs: list[dict[str, object]] = []

        async def _on_source_progress(
            src_log: dict[str, object],
            totals: dict[str, int],
        ) -> None:
            accumulated_logs.append(dict(src_log))
            if run_id is None:
                return
            try:
                async with async_session_maker() as progress_session:
                    row = await progress_session.get(ScraperRun, run_id)
                    if isinstance(row, ScraperRun):
                        _apply_totals_to_run(row, totals, accumulated_logs)
                        await progress_session.commit()
            except SQLAlchemyError:
                logger.exception(
                    "Не удалось сохранить live-прогресс прогона в scraper_runs (run_id=%s)",
                    run_id,
                )

        try:
            if run_id is not None:
                async with async_session_maker() as status_session:
                    row = await status_session.get(ScraperRun, run_id)
                    if isinstance(row, ScraperRun):
                        row.status = "running"
                        await status_session.commit()

            effective_key = None if target_source_key == "all" else target_source_key
            async with async_session_maker() as work_session:
                monitor_fn = scraper_pkg.run_customer_sources_monitoring
                extra_kwargs = _filter_supported_kwargs(
                    monitor_fn,
                    {"on_source_progress": _on_source_progress},
                )
                summary = await monitor_fn(
                    work_session,
                    source_key=effective_key,
                    max_urls_per_source=max_urls_per_source,
                    dry_run=dry_run,
                    **extra_kwargs,  # type: ignore[arg-type]
                )

            if run_id is not None:
                async with async_session_maker() as final_session:
                    row = await final_session.get(ScraperRun, run_id)
                    if isinstance(row, ScraperRun):
                        row.status = "completed"
                        row.sources_total = summary.checked_sources
                        row.sources_done = summary.checked_sources
                        row.urls_discovered = summary.discovered_urls
                        row.events_created = summary.events_created_count
                        row.events_updated = summary.events_updated_count
                        row.rejected_b2c = summary.rejected_b2c_count
                        row.rejected_geo = summary.rejected_geo_count
                        row.rejected_past = summary.rejected_past_count
                        row.errors_count = summary.failed_count
                        row.source_logs = (
                            [dict(item) for item in summary.per_source_report]
                            if summary.per_source_report
                            else list(accumulated_logs)
                        )
                        row.error_message = None
                        row.finished_at = datetime.datetime.now(datetime.UTC)
                        await final_session.commit()

            if not dry_run:
                alert_text = format_monitoring_summary_alert(
                    ready_count=summary.ingested_ready_count,
                    needs_enrichment_titles=summary.needs_enrichment_titles,
                )
                await send_manager_alert(alert_text)

            return summary
        except asyncio.CancelledError:
            logger.warning(
                "Прогон скрейпера прерван через CancelledError (run_id=%s, source=%s)",
                run_id,
                target_source_key,
            )
            await _persist_run_failed(run_id, "Прогон прерван (CancelledError)")
            raise
        except Exception as exc:
            logger.exception(
                "Ошибка при выполнении прогона скрейпера (run_id=%s, source=%s)",
                run_id,
                target_source_key,
            )
            await _persist_run_failed(run_id, str(exc).strip() or type(exc).__name__)
            return None
        finally:
            manager_module._is_scraper_running = False
