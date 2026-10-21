import asyncio
import math
import sys
import unittest
from pathlib import Path
from pydantic import BaseModel

# Add backend directory to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import settings
from app.core.constants import normalize_city, CITY_ALIASES, _clean_key
from app.services.ai_client import (
    structured_llm_client,
    embedding_client,
    get_embedding,
    get_embeddings_batch,
    l2_normalize,
    EMBEDDING_SEMAPHORE,
)


class CityExtractionSchema(BaseModel):
    city: str
    budget: int


class TestCityNormalizationUnit(unittest.TestCase):
    """Юнит-тесты на канонизацию названий городов (DoD: >= 10 вариаций)."""

    def test_city_canonicalization_variations(self):
        variations = [
            # 1. Префиксы г. / гор. / г
            ("г. СПб", "Санкт-Петербург"),
            ("гор. Казань", "Казань"),
            ("г Москва", "Москва"),
            ("город Ростов-на-Дону", "Ростов-на-Дону"),
            # 2. Сленг и сокращения
            ("питер", "Санкт-Петербург"),
            ("МСК", "Москва"),
            ("екб", "Екатеринбург"),
            ("нн", "Нижний Новгород"),
            ("рнд", "Ростов-на-Дону"),
            # 3. Региональные агломерации и синонимы
            ("московская область", "Москва"),
            ("подмосковье", "Москва"),
            ("ленинградская область", "Санкт-Петербург"),
            ("ло", "Санкт-Петербург"),
            # 4. Пробелы, регистр и точки
            ("   новосибирск   ", "Новосибирск"),
            ("н. новгород", "Нижний Новгород"),
            # 5. Онлайн-мероприятия
            ("онлайн", "Онлайн"),
            ("вебинар", "Онлайн"),
            # 6. Неизвестные города (корректное удаление префикса и title case)
            ("г. Сколково", "Сколково"),
            ("гор. суздаль", "Суздаль"),
            # 7. Пустые значения
            ("", None),
            (None, None),
        ]

        for raw_input, expected in variations:
            with self.subTest(raw_input=raw_input, expected=expected):
                actual = normalize_city(raw_input)
                self.assertEqual(
                    actual,
                    expected,
                    f"Failed for '{raw_input}': expected '{expected}', got '{actual}'",
                )

    def test_l2_normalization_math(self):
        """Проверка математической корректности L2-нормализации."""
        vec = [3.0, 4.0]
        norm_vec = l2_normalize(vec)
        self.assertAlmostEqual(norm_vec[0], 0.6)
        self.assertAlmostEqual(norm_vec[1], 0.8)
        self.assertAlmostEqual(math.sqrt(norm_vec[0]**2 + norm_vec[1]**2), 1.0)

        # Нулевой вектор
        zero_vec = [0.0, 0.0, 0.0]
        self.assertEqual(l2_normalize(zero_vec), zero_vec)


class TestAICoreIntegration(unittest.IsolatedAsyncioTestCase):
    """Интеграционные тесты ИИ-клиентов (Instructor LLM и Jina AI)."""

    async def test_instructor_structured_output(self):
        """Проверка генерации Pydantic схемы через Instructor."""
        if not settings.LLM_API_KEY:
            self.skipTest("LLM_API_KEY is not configured")

        result = await structured_llm_client.chat.completions.create(
            model=settings.LLM_MODEL,
            response_model=CityExtractionSchema,
            max_tokens=300,
            messages=[
                {"role": "user", "content": "Бюджет 150000 руб, мероприятие в городе Екатеринбург"}
            ],
        )

        self.assertIsInstance(result, CityExtractionSchema)
        self.assertEqual(result.budget, 150000)
        self.assertEqual(normalize_city(result.city), "Екатеринбург")

    async def test_single_and_batch_embeddings(self):
        """Проверка одиночных и батчевых эмбеддингов с L2-нормализацией."""
        if not settings.EMBEDDING_API_KEY:
            self.skipTest("EMBEDDING_API_KEY is not configured")

        # Одиночный
        single_vec = await get_embedding("Проверка строительного форума")
        self.assertEqual(len(single_vec), settings.EMBEDDING_DIM)
        norm = math.sqrt(sum(x * x for x in single_vec))
        self.assertAlmostEqual(norm, 1.0, places=4)

        # Батч
        texts = [
            "Девелопмент жилой недвижимости",
            "Управление коммерческими объектами",
            "Зеленое строительство и стандарты энергоэффективности",
        ]
        batch_vecs = await get_embeddings_batch(texts, batch_size=2)
        self.assertEqual(len(batch_vecs), len(texts))
        for v in batch_vecs:
            self.assertEqual(len(v), settings.EMBEDDING_DIM)
            self.assertAlmostEqual(math.sqrt(sum(x * x for x in v)), 1.0, places=4)


if __name__ == "__main__":
    unittest.main()
