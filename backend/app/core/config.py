from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    DATABASE_URL: str
    EMBEDDING_DIM: int = 1024
    
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
