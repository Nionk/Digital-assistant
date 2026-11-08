import logging
from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api import auth_router, manager_router, showcase_router
from app.core.config import settings
from app.core.database import engine
from app.services.ai_client import embedding_client, raw_openai_client
from app.services.monitoring_job import run_nightly_monitoring_job
from app.services.telegram import close_telegram_http_client

logger = logging.getLogger("app.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Управление жизненным циклом приложения FastAPI (lifespan).
    При ENABLE_SCHEDULER=true запускает фоновый планировщик ночного мониторинга площадок.
    При остановке корректно закрывает соединения с БД, пулы HTTP-клиентов и фоновые задачи.
    """
    scheduler: AsyncIOScheduler | None = None
    if settings.ENABLE_SCHEDULER:
        scheduler = AsyncIOScheduler(timezone=settings.APP_TIMEZONE)
        scheduler.add_job(
            run_nightly_monitoring_job,
            CronTrigger(hour=3, minute=0, timezone=settings.APP_TIMEZONE),
            max_instances=1,
            coalesce=True,
            id="nightly_market_monitoring",
        )
        scheduler.start()
        logger.info("Фоновый планировщик APScheduler успешно запущен (03:00 %s).", settings.APP_TIMEZONE)

    yield

    if scheduler is not None and scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Фоновый планировщик APScheduler остановлен.")

    # Корректное освобождение внешних пулов соединений
    await close_telegram_http_client()
    try:
        await raw_openai_client.close()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Ошибка при закрытии raw_openai_client: %s", exc)
    try:
        await embedding_client.close()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Ошибка при закрытии embedding_client: %s", exc)
    await engine.dispose()
    logger.info("Пул соединений с БД и HTTP-клиенты закрыты.")


app = FastAPI(
    title="Digital Assistant API",
    description=(
        "Двухконтурный сервис мониторинга деловых мероприятий и пакетного подбора под бюджет компании. "
        "Включает закрытый кабинет менеджера (/api/manager/*) и интерактивную "
        "публичную витрину клиента (/api/public/s/*) с изолированным RAG-чатом по регламентам."
    ),
    version="0.1.0-demo",
    lifespan=lifespan,
)

# Настройка CORS (безопасное соответствие спецификации W3C с поддержкой credentials)
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=settings.CORS_ORIGIN_REGEX,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["System"])
async def health_check():
    """
    Системная проверка жизнеспособности сервиса (Liveness Probe).
    Подтверждает, что процесс FastAPI и event loop активны и принимают HTTP-запросы.
    """
    return {"status": "ok"}


@app.get("/ready", tags=["System"])
async def readiness_check():
    """
    Честная проверка готовности сервиса к обработке бизнес-трафика (Readiness Probe).
    Проверяет активное сетевое соединение с PostgreSQL через SELECT 1.
    """
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except (SQLAlchemyError, OSError) as exc:
        logger.warning("Проверка готовности сервиса не прошла (БД недоступна): %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Сервис временно не готов: отсутствует подключение к базе данных.",
        ) from exc
    return {"status": "ready", "database": "connected"}


# Подключение бизнес-роутеров системы
app.include_router(auth_router)
app.include_router(manager_router)
app.include_router(showcase_router)
