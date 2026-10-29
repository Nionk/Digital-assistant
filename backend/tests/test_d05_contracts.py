import sys
import unittest
from pathlib import Path
from uuid import UUID
from fastapi.testclient import TestClient

# Добавляем backend в sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.main import app


class TestD05APIContracts(unittest.TestCase):
    """
    Автоматизированный аудит контрактов API (DoD для задачи D-05).
    Проверяет все 6 бизнес-эндпоинтов, системный /health, схему безопасности и валидацию UUID.
    """

    @classmethod
    def setUpClass(cls):
        cls._tc = TestClient(app)
        cls.client = cls._tc.__enter__()
        cls.valid_token = "550e8400-e29b-41d4-a716-446655440000"

    @classmethod
    def tearDownClass(cls):
        cls._tc.__exit__(None, None, None)

    def test_01_system_health(self):
        """Проверка работоспособности системного эндпоинта /health."""
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_02_manager_clients_dashboard(self):
        """GET /api/manager/clients: список клиентов и алерты горящих дедлайнов."""
        response = self.client.get("/api/manager/clients")
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertIn("clients", data)
        self.assertIn("burning_deadlines", data)
        self.assertGreaterEqual(len(data["clients"]), 1)
        self.assertGreaterEqual(len(data["burning_deadlines"]), 1)

        first_client = data["clients"][0]
        self.assertIn("company_name", first_client)
        self.assertIn("raw_manager_notes", first_client)

    def test_03_manager_match_endpoint_success(self):
        """POST /api/manager/clients/{id}/match: алгоритм подбора пакетов и черновик КП."""
        payload = {
            "raw_manager_notes": "Созвонились с клиентом. Нужен пакет из 3 мероприятий в Москве и СПб на ноябрь-декабрь.",
            "override_profile": {
                "cities": ["Москва", "Санкт-Петербург"],
                "include_online": True,
                "date_from": None,
                "date_to": None,
                "total_budget_max": 400000.0,
                "target_events_count": 3,
                "preferred_formats": [],
                "required_roles": ["delegate", "speaker"],
                "min_speaker_events": 1,
                "themes_keywords": ["КРТ", "строительство", "урбанистика"],
                "semantic_search_query": "Комплексное развитие территорий КРТ девелопмент строительство урбанистика",
            },
        }
        response = self.client.post("/api/manager/clients/1/match", json=payload)
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertIn("extracted_profile", data)
        self.assertTrue(data["extracted_profile"]["include_online"])
        self.assertEqual(len(data["bundle_variants"]), 2)

        # Проверка бонусного слота (цена по запросу)
        self.assertIn("bonus_on_request_items", data)
        self.assertGreaterEqual(len(data["bonus_on_request_items"]), 1)
        bonus_item = data["bonus_on_request_items"][0]
        self.assertIsNone(bonus_item["recommended_tariff"]["base_price"])
        self.assertIsInstance(bonus_item["is_online"], bool)

        # Проверка черновика письма
        self.assertTrue(len(data["generated_pitch_text"]) > 50)

    def test_04_manager_match_validation_error(self):
        """POST /api/manager/clients/{id}/match: отклонение слишком короткой заметки (<10 символов)."""
        response = self.client.post("/api/manager/clients/1/match", json={"raw_manager_notes": "коротко"})
        self.assertEqual(response.status_code, 422)

    def test_05_manager_publish_selection(self):
        """PUT /api/manager/selections/{id}/publish: фиксация и генерация ссылки Magic Link."""
        payload = {
            "selected_bundle_group": 1,
            "final_items": [
                {"event_id": 101, "tariff_id": 501, "ai_rationale": "Утверждено"},
                {"event_id": 102, "tariff_id": 502, "ai_rationale": "Утверждено"},
            ],
            "final_pitch_text": "Уважаемый клиент, направляем согласованный пакет участия.",
        }
        response = self.client.put("/api/manager/selections/10/publish", json=payload)
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertEqual(data["status"], "published")
        # Проверяем, что magic_token парсится как валидный UUID
        token = UUID(data["magic_token"])
        self.assertIsInstance(token, UUID)
        self.assertTrue(data["public_showcase_url"].startswith("/s/"))

    def test_06_public_showcase_valid_uuid(self):
        """GET /api/public/s/{magic_token}: получение данных витрины по валидному UUIDv4."""
        response = self.client.get(f"/api/public/s/{self.valid_token}")
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertIn("pitch_text", data)
        self.assertIn("items", data)
        self.assertEqual(len(data["items"]), 3)
        self.assertEqual(len(data["faq_quick_chips"]), 3)

        # Проверка структуры элемента
        item = data["items"][0]
        self.assertIn("canonical_title", item)
        self.assertIn("tariff_name", item)
        self.assertEqual(item["client_reaction"], "pending")

    def test_07_public_showcase_invalid_uuid_rejected(self):
        """GET /api/public/s/{magic_token}: автоматическое отклонение невалидного UUID (код 422)."""
        response = self.client.get("/api/public/s/invalid-token-12345")
        self.assertEqual(response.status_code, 422)

    def test_08_public_showcase_client_reaction(self):
        """POST /api/public/s/{magic_token}/items/{id}/react: отправка реакции клиента."""
        payload = {"reaction": "interested", "comment": "Отличный формат, бронируем"}
        response = self.client.post(f"/api/public/s/{self.valid_token}/items/1001/react", json=payload)
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertEqual(data["new_reaction"], "interested")
        self.assertTrue(data["manager_notified"])

        # Проверка недопустимого значения реакции
        bad_response = self.client.post(f"/api/public/s/{self.valid_token}/items/1001/react", json={"reaction": "maybe"})
        self.assertEqual(bad_response.status_code, 422)

    def test_09_public_showcase_ask_regulation_question(self):
        """POST /api/public/s/{magic_token}/events/{id}/ask: изолированный RAG-ответ и эскалация."""
        # 1. Вопрос по регламенту -> ответ найден
        res_found = self.client.post(
            f"/api/public/s/{self.valid_token}/events/101/ask",
            json={"question_text": "Что входит в рекомендованный тариф?"},
        )
        self.assertEqual(res_found.status_code, 200)
        data_found = res_found.json()
        self.assertTrue(data_found["is_answer_found"])
        self.assertIsNotNone(data_found["source_quote"])
        self.assertFalse(data_found["escalated_to_telegram"])

        # 2. Вопрос вне регламента -> эскалация менеджеру
        res_esc = self.client.post(
            f"/api/public/s/{self.valid_token}/events/101/ask",
            json={"question_text": "Предоставляется ли вертолетный трансфер из аэропорта?"},
        )
        self.assertEqual(res_esc.status_code, 200)
        data_esc = res_esc.json()
        self.assertFalse(data_esc["is_answer_found"])
        self.assertIsNone(data_esc["source_quote"])
        self.assertTrue(data_esc["escalated_to_telegram"])

    def test_10_openapi_specification_completeness(self):
        """Проверка полноты схемы OpenAPI: наличие всех 7 роутов и схемы BearerAuth."""
        schema = app.openapi()
        paths = schema.get("paths", {})

        required_endpoints = [
            "/health",
            "/api/manager/clients",
            "/api/manager/clients/{client_id}/match",
            "/api/manager/selections/{selection_id}/publish",
            "/api/public/s/{magic_token}",
            "/api/public/s/{magic_token}/items/{item_id}/react",
            "/api/public/s/{magic_token}/events/{event_id}/ask",
        ]

        for endpoint in required_endpoints:
            self.assertIn(endpoint, paths, f"Эндпоинт {endpoint} отсутствует в схеме OpenAPI")

        # Проверка схемы авторизации Bearer
        security_schemes = schema.get("components", {}).get("securitySchemes", {})
        self.assertIn("HTTPBearer", security_schemes)


if __name__ == "__main__":
    unittest.main()
