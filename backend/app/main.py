from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import manager_router, showcase_router
from app.core.database import engine
from app.models import models


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Управление жизненным циклом приложения FastAPI (lifespan).
    Заменяет устаревшие обработчики startup/shutdown (требование rules.md).
    На этапе P-05 сюда будет подключен планировщик регулярных задач APScheduler.
    """
    yield
    # Очистка ресурсов при завершении работы сервера
    await engine.dispose()


app = FastAPI(
    title="Digital Assistant API",
    description=(
        "Двухконтурный сервис мониторинга деловых мероприятий и пакетного подбора под бюджет компании "
        "Включает закрытый кабинет менеджера (/api/manager/*) и интерактивную "
        "публичную витрину клиента (/api/public/s/*) с изолированным RAG-чатом по регламентам."
    ),
    version="0.1.0-demo",
    lifespan=lifespan,
)

# Настройка CORS для взаимодействия с Frontend (React / Vite на localhost:5173)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Системный эндпоинт проверки здоровья сервиса (используется Docker healthcheck)
@app.get("/health", tags=["System"])
async def health_check():
    return {"status": "ok"}


# Подключение бизнес-роутеров системы
app.include_router(manager_router)
app.include_router(showcase_router)