import asyncio
import logging
import math
from typing import Literal

# pyrefly: ignore[missing-import]
import httpx

# pyrefly: ignore[missing-import]
import instructor

# pyrefly: ignore[missing-import]
from openai import APIError, AsyncOpenAI

from app.core.config import settings

logger = logging.getLogger(__name__)

# Базовый клиент генерации текста и Pydantic-структур с ограничением времени ответа
raw_openai_client = AsyncOpenAI(
    api_key=settings.LLM_API_KEY or "unconfigured",
    base_url=settings.LLM_BASE_URL,
    timeout=30.0,
)

# Обертка Instructor для получения структурированного вывода (Pydantic v2)
# Режим Mode.MD_JSON обеспечивает совместимость с большинством открытых и проприетарных моделей
structured_llm_client = instructor.from_openai(
    raw_openai_client,
    mode=instructor.Mode.MD_JSON,
)

# Клиент эмбеддингов с базовым таймаутом соединения
embedding_client = AsyncOpenAI(
    api_key=settings.EMBEDDING_API_KEY or "unconfigured",
    base_url=settings.EMBEDDING_BASE_URL,
    timeout=30.0,
)

# Ограничители параллелизма (Rate Limit Controls)
LLM_SEMAPHORE = asyncio.Semaphore(5)
EMBEDDING_SEMAPHORE = asyncio.Semaphore(3)


def l2_normalize(vec: list[float]) -> list[float]:
    """
    Выполняет L2-нормализацию вектора для корректной работы оператора
    косинусного расстояния (<=>) в pgvector (vector_cosine_ops).
    """
    if any(math.isnan(x) or math.isinf(x) for x in vec):
        raise ValueError("Вектор эмбеддинга содержит некорректные числовые значения (NaN или Inf).")
    norm = math.sqrt(sum(x * x for x in vec))
    if norm == 0.0:
        return vec
    return [x / norm for x in vec]


async def _request_embeddings(
    texts: list[str],
    encoding_format: Literal["float"] = "float",
) -> list[list[float]]:
    """
    Выполняет строго типизированный запрос к шлюзу эмбеддингов.
    Параметр dimensions передается только для моделей с поддержкой усечения размерности (Матрёшка),
    предотвращая HTTP 400 Bad Request на нативных шлюзах (Yandex Cloud text-search-doc/query).
    """
    if settings.EMBEDDING_MODEL in ("text-search-doc", "text-search-query"):
        response = await embedding_client.embeddings.create(
            model=settings.EMBEDDING_MODEL,
            input=texts,
            encoding_format=encoding_format,
        )
    else:
        response = await embedding_client.embeddings.create(
            model=settings.EMBEDDING_MODEL,
            input=texts,
            encoding_format=encoding_format,
            dimensions=settings.EMBEDDING_DIM,
        )
    if not response or not response.data:
        raise RuntimeError("Пустой ответ от шлюза эмбеддингов.")
    ordered_data = sorted(response.data, key=lambda item: item.index)
    vectors = [l2_normalize(item.embedding) for item in ordered_data]
    if len(vectors) != len(texts):
        raise RuntimeError(f"Шлюз эмбеддингов вернул {len(vectors)} векторов на {len(texts)} текстов.")
    if any(len(v) != settings.EMBEDDING_DIM for v in vectors):
        raise RuntimeError(f"Размерность полученного вектора не совпадает с EMBEDDING_DIM={settings.EMBEDDING_DIM}.")
    return vectors


async def get_embedding(text: str) -> list[float]:
    """
    Получает L2-нормализованный вектор заданной размерности для одного текста.
    Вызов защищен семафором параллелизма (EMBEDDING_SEMAPHORE).
    """
    if not text or not text.strip():
        raise ValueError("Пустой текст для расчета эмбеддинга (нулевой вектор приводит к NaN в cosine distance).")
    if not settings.EMBEDDING_API_KEY:
        raise RuntimeError("EMBEDDING_API_KEY не задан в конфигурации приложения.")

    max_retries = 2
    for attempt in range(max_retries + 1):
        try:
            async with EMBEDDING_SEMAPHORE:
                vectors = await _request_embeddings([text], encoding_format="float")
                return vectors[0]
        except (APIError, httpx.HTTPError) as exc:
            if attempt < max_retries:
                delay = 1.0 * (attempt + 1)
                logger.warning(
                    "Сетевой сбой при получении эмбеддинга (попытка %d/%d). Повтор через %.1f сек: %s",
                    attempt + 1,
                    max_retries,
                    delay,
                    exc,
                    exc_info=True,
                )
                await asyncio.sleep(delay)
            else:
                logger.exception(
                    "Ошибка при получении эмбеддинга (model=%s)",
                    settings.EMBEDDING_MODEL,
                )
                raise
    raise RuntimeError("Не удалось получить эмбеддинг.")


async def get_embeddings_batch(texts: list[str], batch_size: int = 16) -> list[list[float]]:
    """
    Батчевая генерация эмбеддингов (10-20 текстов в пакете) с контролем частоты запросов
    через EMBEDDING_SEMAPHORE в строгом соответствии с rules.md (п. 3.3).
    """
    if not texts:
        return []

    if not settings.EMBEDDING_API_KEY:
        raise RuntimeError("EMBEDDING_API_KEY не задан в конфигурации приложения.")

    results: list[list[float]] = []
    max_retries = 2

    for i in range(0, len(texts), batch_size):
        chunk = texts[i : i + batch_size]
        for attempt in range(max_retries + 1):
            try:
                async with EMBEDDING_SEMAPHORE:
                    batch_vectors = await _request_embeddings(chunk, encoding_format="float")
                results.extend(batch_vectors)
                break
            except (APIError, httpx.HTTPError) as exc:
                if attempt < max_retries:
                    delay = 1.0 * (attempt + 1)
                    logger.warning(
                        "Сетевой сбой при получении батча эмбеддингов (попытка %d/%d). Повтор через %.1f сек: %s",
                        attempt + 1,
                        max_retries,
                        delay,
                        exc,
                        exc_info=True,
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.exception(
                        "Не удалось получить батч эмбеддингов после %d попыток",
                        max_retries + 1,
                    )
                    raise

    return results
