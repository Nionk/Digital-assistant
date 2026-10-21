import asyncio
from pydantic import BaseModel
from app.services.ai_client import structured_llm_client, embedding_client
from app.core.config import settings
from app.core.constants import normalize_city


class TestSchema(BaseModel):
    budget: int
    city: str

async def test_llm():
    print("--- Тест LLM (Pydantic) ---")
    try:
        response = await structured_llm_client.chat.completions.create(
            model=settings.LLM_MODEL,
            response_model=TestSchema,
            messages=[
                {"role": "user", "content": "Выдели бюджет 50000 рублей и город Москва"}
            ]
        )
        print(f"[OK] LLM вернула схему: {response}")
        assert isinstance(response.budget, int)
        assert response.city == "Москва"
    except Exception as e:
        print(f"[FAIL] Ошибка LLM: {e}")

async def test_embedding():
    print("\n--- Тест Embeddings (Jina AI) ---")
    try:
        response = await embedding_client.embeddings.create(
            model=settings.EMBEDDING_MODEL,
            input=["Тестовый текст для проверки"],
            dimensions=settings.EMBEDDING_DIM
        )
        vec = response.data[0].embedding
        print(f"[OK] Получен вектор длиной {len(vec)}")
        assert isinstance(vec, list)
        assert isinstance(vec[0], float)
        assert len(vec) == settings.EMBEDDING_DIM
    except Exception as e:
        print(f"[FAIL] Ошибка эмбеддинга: {e}")

def test_cities():
    print("\n--- Тест нормализации городов ---")
    test_cases = ["г. СПб", "Московская область", "МСК", "Казань"]
    for city in test_cases:
        print(f"'{city}' -> '{normalize_city(city)}'")

async def main():
    test_cities()
    
    if settings.LLM_API_KEY:
        await test_llm()
    else:
        print("\n[SKIP] Тест LLM пропущен (нет LLM_API_KEY в .env)")
        
    if settings.EMBEDDING_API_KEY:
        await test_embedding()
    else:
        print("\n[SKIP] Тест эмбеддингов пропущен (нет EMBEDDING_API_KEY в .env)")

if __name__ == "__main__":
    asyncio.run(main())