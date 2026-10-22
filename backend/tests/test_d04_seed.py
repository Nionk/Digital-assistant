import sys
import unittest
from pathlib import Path
import bcrypt

# Добавляем backend в sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.seed_db import (
    DEFAULT_MANAGER_DATA,
    TEST_CLIENTS_DATA,
    hash_password,
)
from app.models.models import User, Client
from app.core.security import get_current_manager


class TestD04SeedDataUnit(unittest.IsolatedAsyncioTestCase):
    """
    Юнит-тесты валидации данных и логики сидинга менеджера и клиентов (DoD D-04 п.5).
    """

    def test_01_default_manager_data_spec(self):
        """Проверка спецификации дефолтного менеджера: совпадение с get_current_manager stub."""
        self.assertEqual(DEFAULT_MANAGER_DATA["id"], 1)
        self.assertEqual(DEFAULT_MANAGER_DATA["email"], "manager@skart.ru")
        self.assertIn("Анна Соколова", DEFAULT_MANAGER_DATA["full_name"])
        self.assertIsNotNone(DEFAULT_MANAGER_DATA["telegram_chat_id"])

        # Проверка хэширования пароля через bcrypt
        raw_password = DEFAULT_MANAGER_DATA["password"]
        hashed = hash_password(raw_password)
        self.assertTrue(hashed.startswith("$2b$") or hashed.startswith("$2a$"))
        self.assertTrue(bcrypt.checkpw(raw_password.encode("utf-8"), hashed.encode("utf-8")))

    async def test_02_manager_security_stub_alignment(self):
        """Проверка согласованности дефолтного менеджера с функцией get_current_manager."""
        stub_manager = await get_current_manager()
        self.assertEqual(stub_manager.id, DEFAULT_MANAGER_DATA["id"])
        self.assertEqual(stub_manager.email, DEFAULT_MANAGER_DATA["email"])
        self.assertEqual(stub_manager.telegram_chat_id, DEFAULT_MANAGER_DATA["telegram_chat_id"])

    def test_03_test_clients_data_spec(self):
        """Проверка структуры 3 тестовых клиентов (DoD D-04 п.5)."""
        self.assertEqual(len(TEST_CLIENTS_DATA), 3, "Должно быть ровно 3 тестовых клиента")

        expected_companies = ["ГК «Пионер»", "Девелопмент-Юг", "Брусника. Сибирь"]
        actual_companies = [c["company_name"] for c in TEST_CLIENTS_DATA]
        self.assertEqual(actual_companies, expected_companies)

        for client in TEST_CLIENTS_DATA:
            self.assertIn("id", client)
            self.assertIn("company_name", client)
            self.assertIn("contact_person", client)
            self.assertIn("raw_manager_notes", client)
            self.assertIn("extracted_profile", client)

            # Проверка, что заметка содержательна (>= 30 символов)
            self.assertGreater(len(client["raw_manager_notes"]), 30)

            # Проверка извлеченного профиля
            profile = client["extracted_profile"]
            self.assertIn("cities", profile)
            self.assertIn("total_budget_max", profile)
            self.assertGreater(profile["total_budget_max"], 0)
            self.assertIn("target_events_count", profile)
            self.assertIn("required_roles", profile)
            self.assertIn("themes_keywords", profile)
            self.assertIn("semantic_search_query", profile)

    def test_04_orm_models_instantiation(self):
        """Проверка создания ORM объектов User и Client без исключений типов."""
        manager_user = User(
            id=DEFAULT_MANAGER_DATA["id"],
            email=DEFAULT_MANAGER_DATA["email"],
            password_hash=hash_password(DEFAULT_MANAGER_DATA["password"]),
            full_name=DEFAULT_MANAGER_DATA["full_name"],
            telegram_chat_id=DEFAULT_MANAGER_DATA["telegram_chat_id"],
        )
        self.assertEqual(manager_user.id, 1)
        self.assertEqual(manager_user.email, "manager@skart.ru")

        for client_dict in TEST_CLIENTS_DATA:
            client = Client(
                id=client_dict["id"],
                manager_id=manager_user.id,
                company_name=client_dict["company_name"],
                contact_person=client_dict["contact_person"],
                raw_manager_notes=client_dict["raw_manager_notes"],
                extracted_profile=client_dict["extracted_profile"],
            )
            self.assertEqual(client.manager_id, 1)
            self.assertIsNotNone(client.company_name)


if __name__ == "__main__":
    unittest.main()
