import logging
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger("app.core.config")

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent
BACKEND_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    """
    Конфигурация проекта (12-Factor App).
    Настройки загружаются из переменных окружения и .env файлов.
    """

    # Database (PostgreSQL 16 + pgvector)
    # Хост по умолчанию задается через .env (localhost:5432 для локальной разработки, db:5432 внутри Docker)
    DATABASE_URL: str = ""

    # Security & JWT
    SECRET_KEY: str = ""
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440

    # Флаг переходного режима авторизации для этапа Демо:
    # При True: если заголовок Authorization отсутствует, запрос обслуживается от имени ведущего менеджера id=1 из БД.
    # При False (Production): любой запрос без валидного JWT немедленно возвращает HTTP 401 Unauthorized.
    # [TODO-PHASE-P01]: Переключить в False по умолчанию после добавления экрана входа во фронтенде (Шаг 6).
    ALLOW_DEMO_AUTH_BYPASS: bool = True

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
        if not v or len(v.strip()) < 32:
            raise ValueError("SECRET_KEY must be at least 32 characters long for security.")
        insecure_templates = {
            "super_secret_key_for_jwt_change_me_in_production",
            "generate_with_openssl_rand_hex_32",
        }
        if v.strip() in insecure_templates:
            logger.warning(
                "SECURITY WARNING: SECRET_KEY is set to insecure default template! "
                "Generate a cryptographically secure key with `openssl rand -hex 32`."
            )
        return v

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
        extra="ignore",
    )


settings = Settings()
