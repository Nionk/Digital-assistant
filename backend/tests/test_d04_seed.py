import unittest
import asyncio
import json
import math
import sys
from pathlib import Path
from datetime import date

# Add backend directory to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select, func

from app.core.database import async_session_maker
from app.models.models import User, Client, Event, EventTariff, LLMCache
from app.core.config import settings
from tests.test_d08_d09_d10 import is_postgres_online


@unittest.skipUnless(is_postgres_online(), "Требуется запущенный контейнер PostgreSQL")
class TestD04DatabaseSeed(unittest.IsolatedAsyncioTestCase):
    """
    Интеграционный тест верификации Задачи D-04:
    «Золотой датасет» девелоперских мероприятий, тарифов, векторов и кэша регламентов.
    """

    async def asyncTearDown(self):
        from app.core.database import engine
        await engine.dispose()


    async def test_01_default_manager_and_clients(self):
        """Проверка наличия ведущего менеджера (id=1) и 3 тестовых клиентов."""
        async with async_session_maker() as s:

            # Менеджер
            manager = await s.get(User, 1)
            self.assertIsNotNone(manager, "Дефолтный менеджер с ID=1 должен существовать")
            self.assertEqual(manager.email, "manager@skart.ru")

            # Клиенты
            stmt = select(Client)
            res = await s.execute(stmt)
            clients = res.scalars().all()
            self.assertGreaterEqual(len(clients), 3, "В базе должно быть минимум 3 тестовых клиента")

            client_ids = {c.id for c in clients}
            self.assertTrue({1, 2, 3}.issubset(client_ids), "Клиенты с ID 1, 2, 3 обязаны присутствовать")

    async def test_02_events_count_and_embeddings(self):
        """Проверка наличия 15 событий с 1024-мерными L2-нормализованными эмбеддингами."""
        async with async_session_maker() as s:
            stmt = select(Event).where(Event.is_active == True)
            res = await s.execute(stmt)
            events = res.scalars().all()

            self.assertEqual(len(events), 15, "В базе должно быть ровно 15 активных мероприятий из seed_data.json")

            for e in events:
                self.assertIsNotNone(e.summary_embedding, f"Событие {e.id} '{e.canonical_title}' должно иметь эмбеддинг")
                emb = list(e.summary_embedding)
                self.assertEqual(
                    len(emb),
                    settings.EMBEDDING_DIM,
                    f"Размерность эмбеддинга должна быть {settings.EMBEDDING_DIM}"
                )
                # Проверка L2-нормализации: длина вектора близка к 1.0
                norm = math.sqrt(sum(x * x for x in emb))
                self.assertAlmostEqual(norm, 1.0, places=3, msg="Эмбеддинг должен быть L2-нормализован для vector_cosine_ops")

                # Проверка дат
                self.assertGreaterEqual(e.end_date, e.start_date, "Дата окончания должна быть >= даты начала")

                # Проверка ограничения города/онлайна
                self.assertTrue(
                    e.city is not None or e.is_online,
                    f"Событие {e.id} обязано иметь город или флаг is_online=True"
                )

                # Проверка Markdown-регламента
                self.assertTrue(
                    e.full_regulation_markdown and len(e.full_regulation_markdown) > 500,
                    f"Событие {e.id} должно содержать связный регламент в Markdown"
                )

    async def test_03_tariffs_structure_and_pricing_diversity(self):
        """
        Проверка тарифной сетки:
        - Всего 43 тарифа
        - Наличие платных тарифов (base_price > 0)
        - Наличие тарифов 'По запросу' (base_price is None)
        - Наличие бесплатных тарифов (base_price == 0.0)
        - Наличие скидок Early Bird
        """
        async with async_session_maker() as s:
            stmt = select(EventTariff)
            res = await s.execute(stmt)
            tariffs = res.scalars().all()

            self.assertEqual(len(tariffs), 43, "В базе должно быть 43 тарифа")

            paid_tariffs = [t for t in tariffs if t.base_price is not None and t.base_price > 0]
            free_tariffs = [t for t in tariffs if t.base_price == 0.0]
            on_request_tariffs = [t for t in tariffs if t.base_price is None]
            early_bird_tariffs = [
                t for t in tariffs
                if t.early_bird_price is not None and t.early_bird_deadline is not None
            ]

            self.assertGreater(len(paid_tariffs), 0, "Должны быть стандартные платные тарифы")
            self.assertGreaterEqual(len(free_tariffs), 1, "Должны присутствовать бесплатные тарифы (base_price = 0.0)")
            self.assertGreaterEqual(len(on_request_tariffs), 1, "Должны присутствовать тарифы 'По запросу' (base_price = NULL)")
            self.assertGreaterEqual(len(early_bird_tariffs), 1, "Должны присутствовать тарифы со скидкой Early Bird")

            # Проверка Early Bird скидки: early_bird_price < base_price
            for eb in early_bird_tariffs:
                self.assertIsNotNone(eb.base_price)
                self.assertLess(eb.early_bird_price, eb.base_price, "Льготная цена Early Bird должна быть меньше базовой")

    async def test_04_llm_cache_integrity(self):
        """Проверка таблицы llm_cache: SHA-256 ключи, привязка к event_id, валидный JSON."""
        async with async_session_maker() as s:
            stmt = select(LLMCache)
            res = await s.execute(stmt)
            cache_entries = res.scalars().all()

            self.assertGreaterEqual(len(cache_entries), 50, "В кэше llm_cache должно быть не менее 50 предпрогретых записей")

            for entry in cache_entries:
                self.assertEqual(len(entry.cache_key), 64, "Ключ кэша обязан быть SHA-256 хэшем длиной 64 символа")
                self.assertIsNotNone(entry.event_id, "Запись кэша должна быть привязана к event_id")

                # Проверка JSON payload
                payload = json.loads(entry.response_text)
                self.assertIn("is_answer_found", payload)
                self.assertIn("answer_text", payload)
                self.assertIn("source_quote", payload)
                self.assertTrue(len(payload["answer_text"]) > 10, "Текст ответа в кэше должен быть содержательным")


if __name__ == "__main__":
    unittest.main()
