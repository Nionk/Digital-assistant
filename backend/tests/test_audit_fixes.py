import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# Добавляем backend в sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import settings
from app.core.database import get_async_session
from app.core.security import hash_password
from app.main import app
from app.models.models import User
from app.services.telegram import StubTelegramTransport, set_telegram_transport


@pytest.fixture(autouse=True)
def setup_teardown():
    set_telegram_transport(StubTelegramTransport())
    yield
    set_telegram_transport(None)
    app.dependency_overrides.clear()


@pytest.fixture
def client():
    with TestClient(app) as tc:
        yield tc


def test_auth_login_endpoint(client):
    """Проверка рабочего эндпоинта POST /api/auth/login через чистый DI мок сессии."""
    mock_user = User(
        id=1,
        email="manager@skart.ru",
        password_hash=hash_password("password"),
        full_name="Анна Соколова",
        telegram_chat_id=123456789,
    )

    async def override_session():
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_user
        mock_session.execute.return_value = mock_result
        yield mock_session

    app.dependency_overrides[get_async_session] = override_session

    # 1. Неверный пароль -> 401
    bad_res = client.post(
        "/api/auth/login",
        json={"email": "manager@skart.ru", "password": "wrongpassword"},
    )
    assert bad_res.status_code == 401

    # 2. Корректные учетные данные -> 200 и JWT-токен
    res = client.post(
        "/api/auth/login",
        json={"email": "manager@skart.ru", "password": "password"},
    )
    assert res.status_code == 200
    data = res.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["user"]["email"] == "manager@skart.ru"
    assert data["user"]["full_name"] == "Анна Соколова"


def test_production_environment_blocks_demo_fallbacks(client):
    """В prod-окружении (ENVIRONMENT != 'dev') демо-токены и хардкодные моки блокируются."""
    demo_token = "550e8400-e29b-41d4-a716-446655440000"

    with patch.object(settings, "ENVIRONMENT", "prod"):
        # 1. Запрос к витрине по демо-токену не должен возвращать 200 с фейковыми данными Пионера
        res_showcase = client.get(f"/api/public/s/{demo_token}")
        assert res_showcase.status_code in (404, 503)

        # 2. Реакция по демо-токену возвращает 404 или 503
        res_react = client.post(
            f"/api/public/s/{demo_token}/items/1001/react",
            json={"reaction": "interested"},
        )
        assert res_react.status_code in (404, 503)

        # 3. Вопрос по демо-токену возвращает 404 или 503
        res_ask = client.post(
            f"/api/public/s/{demo_token}/events/101/ask",
            json={"question_text": "Что входит в тариф?"},
        )
        assert res_ask.status_code in (404, 503)

        # 4. Эскалация по демо-токену возвращает 404 или 503
        res_esc = client.post(
            f"/api/public/s/{demo_token}/events/101/escalate-question",
            json={"question_text": "Вопрос менеджеру"},
        )
        assert res_esc.status_code in (404, 503)


def test_cors_security(client):
    """Проверка корректной конфигурации CORS без использования wildcard при allow_credentials=True."""
    # Локальный origin разрешен
    res = client.options(
        "/api/auth/login",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert res.status_code == 200
    assert res.headers.get("access-control-allow-origin") == "http://localhost:3000"
    assert res.headers.get("access-control-allow-credentials") == "true"
