from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # Database
    DATABASE_URL: str
    
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

    @property
    def jina_token(self) -> str | None:
        """
        Возвращает токен для Jina Reader API (r.jina.ai) и Jina Embeddings.
        Фолбэк: если JINA_API_KEY не задан явно, используется общий EMBEDDING_API_KEY.
        """
        token = self.JINA_API_KEY or self.EMBEDDING_API_KEY
        return token if token else None

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
