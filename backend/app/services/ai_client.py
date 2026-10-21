from openai import AsyncOpenAI
import instructor
from app.core.config import settings

# ==========================================
# 1. КЛИЕНТ ДЛЯ ГЕНЕРАЦИИ ТЕКСТА (LLM)
# ==========================================
# Базовый клиент (использует Ru-OpenRouter)
raw_openai_client = AsyncOpenAI(
    api_key=settings.LLM_API_KEY,
    base_url=settings.LLM_BASE_URL,
)

# Обертка Instructor для получения структурированного вывода (Pydantic)
# Mode.MD_JSON отлично работает с большинством открытых моделей (DeepSeek, Qwen и т.д.)
structured_llm_client = instructor.from_openai(
    raw_openai_client,
    mode=instructor.Mode.MD_JSON
)

# ==========================================
# 2. КЛИЕНТ ДЛЯ ЭМБЕДДИНГОВ (ВЕКТОРОВ)
# ==========================================
# Отдельный клиент, так как OpenRouter не поддерживает эмбеддинги, 
# мы идем напрямую в Jina AI
embedding_client = AsyncOpenAI(
    api_key=settings.EMBEDDING_API_KEY,
    base_url=settings.EMBEDDING_BASE_URL,
)