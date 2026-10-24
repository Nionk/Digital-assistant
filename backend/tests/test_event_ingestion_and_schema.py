import sys
import unittest
from datetime import date
from pathlib import Path

# Add backend directory to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import Settings
from app.models.models import Event
from app.schemas.event_ingestion import (
    TariffExtracted,
    FAQCacheItem,
    EventIngestionSchema,
)


class TestEventIngestionAndSchema(unittest.TestCase):
    """
    Тестирование:
    1. Новых полей data_status и missing_data_warnings в ORM Event.
    2. Строгой типизации дат (datetime.date) и валидаторов EventIngestionSchema.
    3. Фолбэк-логики jina_token в Settings.
    """

    def test_01_event_orm_model_columns(self):
        """Проверка колонок data_status и missing_data_warnings в Event."""
        event = Event(
            canonical_title="Форум КРТ 2026",
            normalized_title="форум крт 2026",
            event_format="forum",
            city="Москва",
            is_online=False,
            venue="Отель Балчуг",
            start_date=date(2026, 11, 20),
            end_date=date(2026, 11, 21),
            summary="Ключевое мероприятие девелоперов жилой недвижимости по вопросам комплексного развития территорий.",
            themes=["КРТ", "девелопмент"],
            data_status="ready",
            missing_data_warnings=["tariffs.sponsor_price_missing"],
        )
        self.assertEqual(event.data_status, "ready")
        self.assertEqual(event.missing_data_warnings, ["tariffs.sponsor_price_missing"])

    def test_02_pydantic_date_parsing_success(self):
        """Pydantic автоматически парсит валидные ISO-строки в datetime.date."""
        data = {
            "canonical_title": "Строительная неделя БРИКС 2026",
            "event_format": "forum",
            "city": "Казань",
            "is_online": False,
            "venue": "Казань Экспо",
            "start_date": "2026-11-10",
            "end_date": "2026-11-13",
            "summary": (
                "Международный строительно-девелоперский форум стран БРИКС объединяет свыше трех тысяч "
                "ведущих девелоперов, архитекторов и производителей строительных материалов. В фокусе: "
                "механизмы комплексного развития территорий (КРТ), цифровизация проектирования и ТИМ-моделирование, "
                "экспорт стройматериалов и привлечение инвестиций в масштабные жилые кластеры России."
            ),
            "themes": ["строительство", "BIM", "КРТ"],
            "full_regulation_markdown": "# Регламент\n\n1. Общие положения\n2. Программа\n3. Аккредитация\n4. Спикеры\n5. Тарифы\n6. Логистика",
            "tariffs": [
                {
                    "tariff_name": "Делегат",
                    "participation_role": "delegate",
                    "base_price": 50000.0,
                    "early_bird_price": 40000.0,
                    "early_bird_deadline": "2026-10-31",
                    "is_vat_included": True,
                    "included_benefits": "Доступ во все залы и кофе-брейки",
                }
            ],
            "faq_cache": [
                {
                    "question": "Что входит в тариф?",
                    "answer": "В тариф входит доступ во все залы и кофе-брейки.",
                    "source_quote": "Доступ во все залы и кофе-брейки",
                }
            ],
            "missing_data_warnings": [],
        }

        parsed = EventIngestionSchema.model_validate(data)
        self.assertIsInstance(parsed.start_date, date)
        self.assertEqual(parsed.start_date, date(2026, 11, 10))
        self.assertIsInstance(parsed.end_date, date)
        self.assertEqual(parsed.end_date, date(2026, 11, 13))
        self.assertIsInstance(parsed.tariffs[0].early_bird_deadline, date)
        self.assertEqual(parsed.tariffs[0].early_bird_deadline, date(2026, 10, 31))

    def test_03_pydantic_invalid_date_rejection(self):
        """Pydantic отклоняет невалидный формат даты (строку текста вместо YYYY-MM-DD)."""
        data = {
            "canonical_title": "Тестовое событие",
            "event_format": "conference",
            "city": "Москва",
            "is_online": False,
            "start_date": "середина ноября 2026",  # Невалидная дата!
            "end_date": "2026-11-20",
            "summary": (
                "Краткое описание мероприятия на двести пятьдесят символов для успешного прохождения "
                "минимальной валидации длины поля summary в схеме Pydantic v2. Отраслевые тренды, "
                "жилищное строительство и инвестиции в инфраструктуру мегаполисов."
            ),
            "themes": ["BIM"],
            "full_regulation_markdown": "Полный текст регламента",
        }
        with self.assertRaises(Exception):
            EventIngestionSchema.model_validate(data)

    def test_04_enforce_online_constraint(self):
        """Проверка автоматической нормализации онлайн-события (city -> None, is_online -> True)."""
        data = {
            "canonical_title": "Вебинар по ТИМ и BIM",
            "event_format": "conference",
            "city": "Онлайн",
            "is_online": False,  # Должно автоматически стать True!
            "start_date": "2026-12-01",
            "end_date": "2026-12-01",
            "summary": (
                "Онлайн-вебинар по практическому внедрению технологий информационного моделирования "
                "в девелоперских проектах жилой недвижимости. Разбор реальных кейсов застройщиков, "
                "нормативное регулирование, переход на отечественное программное обеспечение и экспертиза."
            ),
            "themes": ["BIM", "онлайн"],
            "full_regulation_markdown": "Регламент подключения к вебинару",
        }

        parsed = EventIngestionSchema.model_validate(data)
        self.assertIsNone(parsed.city)
        self.assertTrue(parsed.is_online)

    def test_05_jina_token_property_fallback(self):
        """Проверка фолбэка jina_token в Settings."""
        # Случай 1: задан только EMBEDDING_API_KEY
        s1 = Settings(
            DATABASE_URL="postgresql+asyncpg://user:pass@localhost:5432/db",
            EMBEDDING_API_KEY="jina_emb_key_123",
            JINA_API_KEY=None,
        )
        self.assertEqual(s1.jina_token, "jina_emb_key_123")

        # Случай 2: задан явный JINA_API_KEY (приоритет над EMBEDDING_API_KEY)
        s2 = Settings(
            DATABASE_URL="postgresql+asyncpg://user:pass@localhost:5432/db",
            EMBEDDING_API_KEY="jina_emb_key_123",
            JINA_API_KEY="dedicated_jina_reader_key_456",
        )
        self.assertEqual(s2.jina_token, "dedicated_jina_reader_key_456")

        # Случай 3: оба пустые
        s3 = Settings(
            DATABASE_URL="postgresql+asyncpg://user:pass@localhost:5432/db",
            EMBEDDING_API_KEY="",
            JINA_API_KEY=None,
        )
        self.assertIsNone(s3.jina_token)


    def test_06_faq_question_normalization(self):
        """Проверка автоматической нормализации вопросов к каноническим чипсам."""
        # 1. Алиасы
        faq1 = FAQCacheItem.model_validate({
            "question": "Что входит в тариф?",
            "answer": "В тариф входит посещение всех сессий.",
            "source_quote": "Посещение всех сессий",
        })
        self.assertEqual(faq1.question, "Что входит в рекомендованный тариф?")

        faq2 = FAQCacheItem.model_validate({
            "question": "Условия Early Bird",
            "answer": "Скидка действует до 31 октября.",
            "source_quote": "До 31 октября",
        })
        self.assertEqual(faq2.question, "Какие условия раннего бронирования и дедлайны?")

        faq3 = FAQCacheItem.model_validate({
            "question": "Требования к спикеру",
            "answer": "Доклад 20 минут, презентация 16:9.",
            "source_quote": "Презентация 16:9",
        })
        self.assertEqual(faq3.question, "Формат участия и требования к спикеру")

        # 2. Неточные совпадения / эвристика
        faq_custom = FAQCacheItem.model_validate({
            "question": "Что входит в пакет «Премиум»?",
            "answer": "Стенд 6 кв.м и 2 бейджа.",
            "source_quote": "Стенд 6 кв.м",
        })
        self.assertEqual(faq_custom.question, "Что входит в рекомендованный тариф?")

    def test_07_summary_min_length_relaxed_and_date_protection(self):
        """Проверка relaxed min_length=100 и автоматической коррекции end_date < start_date."""
        data = {
            "canonical_title": "Конференция Девелопмент 2026",
            "event_format": "conference",
            "city": "Москва",
            "is_online": False,
            "start_date": "2026-11-20",
            "end_date": "2026-11-18",  # Перепутаны даты: end_date < start_date!
            # Длина 120 символов (проходит валидацию min_length=100, ранее падало при min_length=250)
            "summary": "Конференция по современному жилищному девелопменту, новым технологиям монолитного строительства и урбанистике городов.",
            "themes": ["девелопмент"],
            "full_regulation_markdown": "Регламент мероприятия",
        }
        parsed = EventIngestionSchema.model_validate(data)
        # Проверяем, что end_date скорректирована до start_date
        self.assertEqual(parsed.end_date, parsed.start_date)
        self.assertEqual(parsed.end_date, date(2026, 11, 20))
        self.assertEqual(len(parsed.summary), 118)

    def test_08_orm_relationships_and_bigint(self):
        """Проверка BigInteger для telegram_chat_id и наличия relationship-связей в моделях."""
        from sqlalchemy import BigInteger
        from app.models.models import (
            User,
            Client,
            Event,
            EventTariff,
            EventChunk,
            Selection,
            SelectionItem,
            ChatMessage,
            LLMCache,
        )

        # 1. Проверка типа telegram_chat_id
        col_type = User.telegram_chat_id.property.columns[0].type
        self.assertIsInstance(col_type, BigInteger)

        # 2. Проверка связей в User / Client
        self.assertTrue(hasattr(User, "clients"))
        self.assertTrue(hasattr(Client, "manager"))
        self.assertTrue(hasattr(Client, "selections"))

        # 3. Проверка связей в Event / EventTariff / EventChunk
        self.assertTrue(hasattr(Event, "tariffs"))
        self.assertTrue(hasattr(Event, "chunks"))
        self.assertTrue(hasattr(Event, "selection_items"))
        self.assertTrue(hasattr(EventTariff, "event"))
        self.assertTrue(hasattr(EventChunk, "event"))

        # 4. Проверка связей в Selection / SelectionItem / ChatMessage / LLMCache
        self.assertTrue(hasattr(Selection, "client"))
        self.assertTrue(hasattr(Selection, "items"))
        self.assertTrue(hasattr(Selection, "chat_messages"))
        self.assertTrue(hasattr(SelectionItem, "selection"))
        self.assertTrue(hasattr(SelectionItem, "event"))
        self.assertTrue(hasattr(SelectionItem, "recommended_tariff"))
        self.assertTrue(hasattr(ChatMessage, "selection"))
        self.assertTrue(hasattr(ChatMessage, "event"))
        self.assertTrue(hasattr(LLMCache, "event"))

    def test_09_ai_client_encoding_format_float(self):
        """Проверка передачи encoding_format='float' в методах ai_client."""
        import inspect
        from app.services import ai_client

        get_emb_src = inspect.getsource(ai_client.get_embedding)
        get_batch_src = inspect.getsource(ai_client.get_embeddings_batch)

        self.assertIn('encoding_format="float"', get_emb_src)
        self.assertIn('encoding_format="float"', get_batch_src)


if __name__ == "__main__":
    unittest.main()
