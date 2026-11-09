import logging
from pathlib import Path
from typing import Literal

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger("app.core.config")

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent
BACKEND_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    """
    Конфигурация проекта (12-Factor App).
    Настройки загружаются из переменных окружения и .env файлов.
    """

    # Окружение: prod (боевой режим по умолчанию) или dev (локальная разработка)
    ENVIRONMENT: Literal["dev", "prod"] = "prod"
    APP_TIMEZONE: str = "Europe/Moscow"
    ENABLE_SCHEDULER: bool = False

    # Database (PostgreSQL 16 + pgvector)
    # Хост по умолчанию задается через .env (localhost:5432 для локальной разработки, db:5432 внутри Docker)
    DATABASE_URL: str = ""

    # Security & JWT
    SECRET_KEY: str = ""
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440

    # Режим авторизации:
    # При True: если заголовок Authorization отсутствует, запрос обслуживается от имени ведущего менеджера id=1 (только для dev-окружения).
    # При False (Production / По умолчанию): любой запрос без валидного JWT немедленно возвращает HTTP 401 Unauthorized.
    ALLOW_DEMO_AUTH_BYPASS: bool = False

    # CORS Configuration
    CORS_ORIGINS: list[str] = [
        "http://localhost",
        "http://localhost:80",
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1",
        "http://127.0.0.1:80",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
    ]
    CORS_ORIGIN_REGEX: str = r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$"

    @field_validator("DATABASE_URL", mode="after")
    @classmethod
    def validate_database_url(cls, v: str) -> str:
        """Валидация наличия строки подключения к БД."""
        if not v or not v.strip():
            raise ValueError("DATABASE_URL must be configured in environment or .env.")
        return v

    @field_validator("SECRET_KEY", mode="after")
    @classmethod
    def validate_secret_key(cls, v: str) -> str:
        """Валидация длины и безопасности секретного ключа JWT."""
        insecure_templates = {
            "super_secret_key_for_jwt_change_me_in_production",
            "generate_with_openssl_rand_hex_32",
        }
        if not v or len(v.strip()) < 32 or v.strip() in insecure_templates:
            raise ValueError(
                "SECRET_KEY must be a cryptographically secure key of at least 32 characters. "
                "Do not use default templates. Generate with `openssl rand -hex 32`."
            )
        return v

    @model_validator(mode="after")
    def forbid_demo_bypass_in_prod(self) -> "Settings":
        """Гарантирует, что обход авторизации никогда не будет включен в production-среде."""
        if self.ENVIRONMENT == "prod" and self.ALLOW_DEMO_AUTH_BYPASS:
            raise ValueError(
                "ALLOW_DEMO_AUTH_BYPASS=true строго запрещен в production-режиме (ENVIRONMENT=prod). "
                "Установите ALLOW_DEMO_AUTH_BYPASS=false или переключите ENVIRONMENT=dev для локальной разработки."
            )
        return self

    # LLM Gateway
    LLM_API_KEY: str = ""
    LLM_BASE_URL: str = "https://api.ru-openrouter.ru/v1"
    LLM_MODEL: str = "deepseek/deepseek-chat"

    # Embedding & Jina Gateway
    JINA_API_KEY: str | None = None
    EMBEDDING_API_KEY: str = ""
    EMBEDDING_BASE_URL: str = "https://api.jina.ai/v1"
    EMBEDDING_MODEL: str = "jina-embeddings-v3"
    EMBEDDING_DIM: int = 1024

    @field_validator("EMBEDDING_DIM", mode="after")
    @classmethod
    def validate_embedding_dim(cls, v: int) -> int:
        """Защита от рассинхрона размерности векторов со схемой базы данных."""
        if v != 1024:
            raise ValueError(
                f"EMBEDDING_DIM={v} не поддерживается текущей схемой БД (alembic 58fff4bbf37c: vector(1024)). "
                "Изменение размерности требует отдельной миграции БД и пересоздания векторных индексов."
            )
        return v

    @field_validator("EMBEDDING_MODEL", mode="after")
    @classmethod
    def validate_embedding_model(cls, v: str) -> str:
        """Предотвращает рассинхрон векторного пространства с БД."""
        certified_models = {"jina-embeddings-v3", "text-search-doc", "text-search-query"}
        if v not in certified_models:
            logger.warning(
                f"EMBEDDING_MODEL '{v}' differs from certified models {certified_models}. "
                "Ensure vector dimension matches database schema."
            )
        return v

    # Telegram Bot API Alerts
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_MANAGER_CHAT_ID: int | None = None

    @field_validator("TELEGRAM_MANAGER_CHAT_ID", mode="before")
    @classmethod
    def parse_telegram_chat_id(cls, v: object) -> int | None:
        """Безопасный парсинг chat_id (поддерживает пустую строку в .env и 0 как отсутствие ID)."""
        if v is None or v == "" or v == 0 or v == "0":
            return None
        try:
            return int(str(v).strip())
        except (ValueError, TypeError):
            return None

    @property
    def jina_token(self) -> str | None:
        """
        Возвращает токен для Jina Reader API (r.jina.ai) и Jina Embeddings.
        Фолбэк: если JINA_API_KEY не задан явно, используется общий EMBEDDING_API_KEY.
        """
        token = self.JINA_API_KEY or self.EMBEDDING_API_KEY
        return token if token else None

    model_config = SettingsConfigDict(
        env_file=(
            str(BACKEND_DIR / ".env"),
            str(ROOT_DIR / ".env"),
            ".env",
        ),
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
