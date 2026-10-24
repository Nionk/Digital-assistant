import asyncio
import math
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

# ==========================================
# 3. ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ И ОГРАНИЧИТЕЛИ (RULES.MD SECTION 3)
# ==========================================
# Ограничитель параллельных запросов к API эмбеддингов для предотвращения HTTP 429
EMBEDDING_SEMAPHORE = asyncio.Semaphore(3)


def l2_normalize(vec: list[float]) -> list[float]:
    """
    Выполняет L2-нормализацию вектора для корректной работы оператора
    косинусного расстояния (<=>) в pgvector (vector_cosine_ops).
    """
    norm = math.sqrt(sum(x * x for x in vec))
    if norm == 0.0:
        return vec
    return [x / norm for x in vec]


async def get_embedding(text: str) -> list[float]:
    """
    Получает L2-нормализованный вектор заданной размерности для одного текста.
    Вызов защищен семафором параллелизма (asyncio.Semaphore(3)).
    Явно передается encoding_format="float", предотвращая возврат base64-строк.
    """
    async with EMBEDDING_SEMAPHORE:
        response = await embedding_client.embeddings.create(
            model=settings.EMBEDDING_MODEL,
            input=[text],
            dimensions=settings.EMBEDDING_DIM,
            encoding_format="float",
        )
        return l2_normalize(response.data[0].embedding)


async def get_embeddings_batch(texts: list[str], batch_size: int = 16) -> list[list[float]]:
    """
    Батчевая генерация эмбеддингов (10-20 текстов в пакете) с контролем частоты запросов
    через asyncio.Semaphore(3) в строгом соответствии с rules.md (п. 3.3).
    Явно передается encoding_format="float", предотвращая возврат base64-строк.
    """
    if not texts:
        return []

    results: list[list[float]] = []
    for i in range(0, len(texts), batch_size):
        chunk = texts[i:i + batch_size]
        async with EMBEDDING_SEMAPHORE:
            response = await embedding_client.embeddings.create(
                model=settings.EMBEDDING_MODEL,
                input=chunk,
                dimensions=settings.EMBEDDING_DIM,
                encoding_format="float",
            )
            # Сортируем по исходному индексу для гарантии сохранения порядка
            ordered_data = sorted(response.data, key=lambda item: item.index)
            results.extend([l2_normalize(item.embedding) for item in ordered_data])

    return results