import asyncio
import math
import sys
from pathlib import Path
from pydantic import BaseModel

# Обеспечиваем корректный импорт app.* при прямом запуске скрипта
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.ai_client import (
    structured_llm_client,
    embedding_client,
    get_embedding,
    get_embeddings_batch,
    l2_normalize,
)
from app.core.config import settings
from app.core.constants import normalize_city


class TestSchema(BaseModel):
    budget: int
    city: str


def test_cities():
    print("--- [1/3] Тестирование канонизации городов (DoD: >= 10 вариаций) ---")
    test_cases = [
        # (входное значение, ожидаемый канонический город)
        ("г. СПб", "Санкт-Петербург"),
        ("питер", "Санкт-Петербург"),
        ("ленинградская область", "Санкт-Петербург"),
        ("ло", "Санкт-Петербург"),
        ("Московская область", "Москва"),
        ("подмосковье", "Москва"),
        ("МСК", "Москва"),
        ("г Москва", "Москва"),
        ("гор. Казань", "Казань"),
        ("екб", "Екатеринбург"),
        ("н. новгород", "Нижний Новгород"),
        ("рнд", "Ростов-на-Дону"),
        ("онлайн", "Онлайн"),
        ("  г. Сколково  ", "Сколково"),  # неизвестный город с префиксом
        ("", None),
        (None, None),
    ]

    passed = 0
    for raw_input, expected in test_cases:
        actual = normalize_city(raw_input)
        assert actual == expected, f"Ошибка нормализации: '{raw_input}' -> '{actual}', ожидалось '{expected}'"
        print(f"  [OK] '{raw_input}' -> '{actual}'")
        passed += 1

    print(f"[OK] Успешно проверено {passed} вариаций названий городов.\n")


async def test_embedding():
    print("--- [2/3] Тестирование Embeddings (Jina AI 1024-dim, Semaphore, L2-Norm) ---")
    
    # Одиночный эмбеддинг через helper
    vec = await get_embedding("Тестовый текст для проверки одиночного эмбеддинга")
    assert isinstance(vec, list), "Вектор должен быть списком"
    assert len(vec) == settings.EMBEDDING_DIM, f"Размерность {len(vec)} != {settings.EMBEDDING_DIM}"
    norm = math.sqrt(sum(x * x for x in vec))
    assert math.isclose(norm, 1.0, rel_tol=1e-4), f"Вектор должен быть L2-нормализован: norm={norm}"
    print(f"  [OK] Одиночный эмбеддинг: dim={len(vec)}, L2-norm={norm:.6f}")

    # Батчевый эмбеддинг через helper (10-20 батч, семафор)
    sample_texts = [
        "Форум девелоперов и архитекторов",
        "Конференция по комплексному развитию территорий",
        "Цифровизация строительной отрасли и BIM-моделирование",
    ]
    batch_vecs = await get_embeddings_batch(sample_texts, batch_size=2)
    assert len(batch_vecs) == len(sample_texts), f"Количество векторов {len(batch_vecs)} != {len(sample_texts)}"
    for idx, b_vec in enumerate(batch_vecs):
        assert len(b_vec) == settings.EMBEDDING_DIM
        b_norm = math.sqrt(sum(x * x for x in b_vec))
        assert math.isclose(b_norm, 1.0, rel_tol=1e-4)
    print(f"  [OK] Батчевые эмбеддинги ({len(sample_texts)} текстов): все dim={settings.EMBEDDING_DIM}, L2-norm=1.0\n")


async def test_llm():
    print("--- [3/3] Тестирование LLM Instructor (Pydantic MD_JSON) ---")
    response = await structured_llm_client.chat.completions.create(
        model=settings.LLM_MODEL,
        response_model=TestSchema,
        max_tokens=300,
        messages=[
            {"role": "user", "content": "Выдели бюджет 50000 рублей и город Москва"}
        ]
    )
    print(f"  [OK] LLM вернула структурированную схему: {response}")
    assert isinstance(response.budget, int), "Бюджет должен быть int"
    assert response.budget == 50000, f"Бюджет {response.budget} != 50000"
    assert response.city == "Москва", f"Город {response.city} != 'Москва'"
    print("  [OK] Валидация Pydantic-схемы через Instructor прошла успешно.\n")


async def main():
    print("=== ЗАПУСК ПРОВЕРКИ ЯДРА ИИ И КОНСТАНТ (TASK D-03) ===\n")
    test_cities()

    if settings.EMBEDDING_API_KEY:
        await test_embedding()
    else:
        print("[SKIP] Тест эмбеддингов пропущен (нет EMBEDDING_API_KEY в .env)")

    if settings.LLM_API_KEY:
        await test_llm()
    else:
        print("[SKIP] Тест LLM пропущен (нет LLM_API_KEY в .env)")

    print("=== ВСЕ ПРОВЕРКИ TASK D-03 УСПЕШНО ПРОЙДЕНЫ! ===")


if __name__ == "__main__":
    asyncio.run(main())