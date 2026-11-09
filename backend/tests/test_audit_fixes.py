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
    yield TestClient(app)


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

    async def override_empty_session():
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_result.first.return_value = None
        mock_session.execute.return_value = mock_result
        yield mock_session

    app.dependency_overrides[get_async_session] = override_empty_session

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


def test_rag_save_chat_message_flags():
    """Проверка правильной расстановки флага needs_manager_attention в chat_messages."""
    import asyncio
    from app.services.rag import _save_chat_message

    async def _test():
        mock_session = MagicMock()
        mock_session.add = MagicMock()

        await _save_chat_message(
            session=mock_session,
            selection_id=10,
            event_id=20,
            question="Сколько стоит участие спикером?",
            answer="В регламенте нет информации.",
            needs_attention=True,
        )

        assert mock_session.add.call_count == 2
        client_msg = mock_session.add.call_args_list[0].args[0]
        ai_msg = mock_session.add.call_args_list[1].args[0]

        assert client_msg.sender_role == "client"
        assert client_msg.message_text == "Сколько стоит участие спикером?"
        assert client_msg.needs_manager_attention is True

        assert ai_msg.sender_role == "ai_assistant"
        assert ai_msg.needs_manager_attention is False

    asyncio.run(_test())


def test_scraper_endpoint_validation_and_concurrency(client):
    """Проверка валидации источников и защиты от параллельного запуска скрейпера."""
    import app.api.manager as manager_module
    from app.core.security import get_current_manager

    mock_mgr = User(
        id=1,
        email="mgr@skart.ru",
        password_hash="fakehash",
        full_name="Менеджер",
        telegram_chat_id=111,
    )
    app.dependency_overrides[get_current_manager] = lambda: mock_mgr

    try:
        # 1. Неизвестный источник -> 422 (или 400)
        res_bad = client.post("/api/manager/scraper/run", json={"source_key": "unknown_platform"})
        assert res_bad.status_code in (400, 422)

        # 2. Успешный запуск известного источника ставит задачу и блокирует повторный запуск
        mock_worker = AsyncMock()
        with patch.object(manager_module, "_execute_background_monitoring", new=mock_worker):
            manager_module._is_scraper_running = False
            res_ok = client.post("/api/manager/scraper/run", json={"source_key": "architime"})
            assert res_ok.status_code == 200
            assert mock_worker.call_count == 1
            # Флаг был выставлен в True
            assert manager_module._is_scraper_running is True

            # 3. Повторный параллельный запуск возвращает статус занятости без вызова воркера
            res_busy = client.post("/api/manager/scraper/run", json={"source_key": "architime"})
            assert res_busy.status_code == 200
            assert "уже выполняется" in res_busy.json()["message"]
            assert mock_worker.call_count == 1  # воркер повторно НЕ вызывался
    finally:
        manager_module._is_scraper_running = False


def test_matcher_fts_fallback_and_none_score_protection():
    """Проверка FTS-фолбэка при query_vec is None и защиты от каста None-оценки."""
    import asyncio
    import datetime
    from app.models.models import Event
    from app.schemas.manager import ClientQueryExtracted
    from app.services.matcher import fetch_hybrid_rrf_candidates

    async def _test():
        fake_profile = ClientQueryExtracted(
            target_events_count=2,
            total_budget_max=300000.0,
            participation_role="speaker",
            date_from=datetime.date(2026, 5, 1),
            date_to=datetime.date(2026, 6, 1),
            cities=["Москва"],
            preferred_formats=["forum"],
            themes_keywords=["архитектура"],
            semantic_search_query="архитектурный форум",
        )

        mock_event = Event(
            id=99,
            canonical_title="Тестовый форум",
            start_date=datetime.date(2026, 5, 10),
            end_date=datetime.date(2026, 5, 12),
            is_online=False,
            city="Москва",
            event_format="forum",
        )

        # Имитируем возврат SQL, где score равен None
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.all.return_value = [(mock_event, None)]
        mock_session.execute.return_value = mock_result

        # Вызов с query_vec = None должен отработать по FTS ветке без TypeError на None
        res = await fetch_hybrid_rrf_candidates(
            session=mock_session,
            profile=fake_profile,
            query_vec=None,
            fts_query_str="форум",
            today=datetime.date(2026, 4, 1),
        )

        assert len(res) == 1
        ev, score = res[0]
        assert ev.id == 99
        assert score == 0.0  # float(row[1] or 0.0) защитил от падения

    asyncio.run(_test())


def test_upload_event_material_safely_queries_tariffs():
    """Проверка вызова ingest_smart_event и безопасного SQL-подсчета тарифов без обращения к event.tariffs."""
    import asyncio
    import app.api.manager as manager_module
    from app.models.models import Event
    from app.core.security import get_current_manager

    async def _test():
        mock_mgr = User(
            id=1,
            email="mgr@skart.ru",
            password_hash="fakehash",
            full_name="Менеджер",
            telegram_chat_id=111,
        )
        app.dependency_overrides[get_current_manager] = lambda: mock_mgr

        mock_session = AsyncMock()
        mock_session.scalar.return_value = 3  # tariffs count from SQL

        created_event = Event(id=105, canonical_title="Конгресс Недвижимости", data_status="ready")

        with patch.object(manager_module, "ingest_smart_event", new=AsyncMock(return_value=created_event)):
            res = await manager_module.upload_event_material(
                current_manager=mock_mgr,
                db=mock_session,
                file=None,
                raw_text="Подробный регламент конгресса недвижимости с описанием условий участия...",
                source_url=None,
            )

            assert res.event_id == 105
            assert res.canonical_title == "Конгресс Недвижимости"
            assert res.tariffs_count == 3
            # Проверяем, что scalar запрос вызывался
            assert mock_session.scalar.call_count == 1

    asyncio.run(_test())
