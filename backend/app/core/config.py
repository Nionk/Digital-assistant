import socket
from pathlib import Path
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent
BACKEND_DIR = Path(__file__).resolve().parent.parent.parent

class Settings(BaseSettings):
    # Database
    DATABASE_URL: str
    
    @field_validator("DATABASE_URL", mode="after")
    @classmethod
    def resolve_db_host(cls, v: str) -> str:
        """
        Автоматический фолбэк для хоста БД:
        Если скрипт запущен вне сети Docker и DNS-имя 'db' недоступно на хост-машине,
        подменяем '@db:' на '@localhost:'. Внутри Docker 'db' доступно и URL не меняется.
        """
        if "@db:" in v:
            try:
                socket.getaddrinfo("db", 5432)
            except (socket.gaierror, OSError):
                return v.replace("@db:", "@localhost:")
        return v
    
    # Security
    SECRET_KEY: str = "super_secret_key_for_jwt_change_me_in_production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440
    
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

    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_MANAGER_CHAT_ID: int = 0

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

