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
    from app.models.models import ScraperRun

    mock_mgr = User(
        id=1,
        email="mgr@skart.ru",
        password_hash="fakehash",
        full_name="Менеджер",
        telegram_chat_id=111,
    )
    app.dependency_overrides[get_current_manager] = lambda: mock_mgr

    async def override_session():
        mock_session = AsyncMock()
        mock_session.new = set()
        mock_session.add = MagicMock()

        async def _execute(stmt):
            res = MagicMock()
            res.scalars.return_value.all.return_value = []
            res.scalar_one_or_none.return_value = None
            return res

        async def _refresh(obj):
            if isinstance(obj, ScraperRun) and obj.id is None:
                obj.id = 1

        mock_session.execute = AsyncMock(side_effect=_execute)
        mock_session.refresh = AsyncMock(side_effect=_refresh)
        yield mock_session

    app.dependency_overrides[get_async_session] = override_session

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
    from app.core.security import get_current_manager
    from app.models.models import Event

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


def test_rag_grounding_rejects_punctuation_only_quotes():
    """Пустые после очистки пунктуации цитаты не должны проходить проверку _is_quote_grounded."""
    from app.services.rag import _is_quote_grounded

    ctx = "Официальный регламент форума по строительству и девелопменту."
    assert _is_quote_grounded("..........", ctx) is False
    assert _is_quote_grounded("--- --- ---", ctx) is False
    assert _is_quote_grounded("!!! ... !!! ... ???", ctx) is False
    assert _is_quote_grounded("регламент форума по строительству", ctx) is True


def test_upload_event_material_url_and_http_errors(client):
    """Некорректный URL возвращает 400, а сбой загрузки внешнего сайта — 502."""
    import httpx

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

    async def override_session():
        yield AsyncMock()

    app.dependency_overrides[get_async_session] = override_session

    with patch.object(
        manager_module,
        "ingest_smart_event",
        new=AsyncMock(side_effect=httpx.InvalidURL("Invalid URL")),
    ):
        res_400 = client.post("/api/manager/events/upload-pdf", data={"source_url": "bad-url"})
        assert res_400.status_code == 400

    with patch.object(
        manager_module,
        "ingest_smart_event",
        new=AsyncMock(side_effect=httpx.ConnectError("Connection refused")),
    ):
        res_502 = client.post("/api/manager/events/upload-pdf", data={"source_url": "https://example.com/event"})
        assert res_502.status_code == 502


def test_manager_events_catalog_archived_filter(client):
    """При ?data_status=archived SQL-фильтр не требует is_active=True."""
    from app.core.security import get_current_manager

    mock_mgr = User(
        id=1,
        email="mgr@skart.ru",
        password_hash="fakehash",
        full_name="Менеджер",
        telegram_chat_id=111,
    )
    app.dependency_overrides[get_current_manager] = lambda: mock_mgr

    captured_stmts = []

    async def override_session():
        mock_session = AsyncMock()

        async def _execute(stmt):
            captured_stmts.append(stmt)
            mock_res = MagicMock()
            mock_res.scalars.return_value.all.return_value = []
            return mock_res

        mock_session.execute = _execute
        yield mock_session

    app.dependency_overrides[get_async_session] = override_session

    res = client.get("/api/manager/events?data_status=archived")
    assert res.status_code == 200
    sql_str = str(captured_stmts[0])
    assert "events.data_status =" in sql_str
    assert "events.is_active IS true" not in sql_str


def test_telegram_masks_bot_token_in_error_logs(caplog):
    """Сетевая ошибка httpx не должна раскрывать TELEGRAM_BOT_TOKEN в логах."""
    import asyncio
    import logging

    import httpx

    from app.services.telegram import HttpTelegramTransport

    secret_token = "123456:ABC-SECRET-BOT-TOKEN"
    req = httpx.Request("POST", f"https://api.telegram.org/bot{secret_token}/sendMessage")
    err = httpx.ConnectError(f"Failed to connect to https://api.telegram.org/bot{secret_token}/sendMessage", request=req)

    transport = HttpTelegramTransport()
    with (
        patch.object(settings, "TELEGRAM_BOT_TOKEN", secret_token),
        patch.object(settings, "TELEGRAM_MANAGER_CHAT_ID", 999999),
        patch("app.services.telegram._post_telegram_message", new=AsyncMock(side_effect=err)),
        caplog.at_level(logging.ERROR),
    ):
        ok = asyncio.run(transport.send_message("Тест", chat_id=999999))
        assert ok is False

    assert secret_token not in caplog.text
    assert "***" in caplog.text


def test_selection_activity_filters_out_non_client_pending_questions(client):
    """GET /api/manager/selections/{id}/activity возвращает только сообщения клиента (sender_role='client')."""
    import datetime

    from app.core.security import get_current_manager
    from app.models.models import ChatMessage, Client, Event, Selection

    mock_mgr = User(
        id=1,
        email="mgr@skart.ru",
        password_hash="fakehash",
        full_name="Менеджер",
        telegram_chat_id=111,
    )
    app.dependency_overrides[get_current_manager] = lambda: mock_mgr

    test_event = Event(
        id=7,
        canonical_title="Форум КРТ 2026",
        normalized_title="форум крт 2026",
        event_format="forum",
        city="Москва",
        is_online=False,
        start_date=datetime.date(2026, 11, 20),
        end_date=datetime.date(2026, 11, 21),
        summary="Описание форума",
    )
    now = datetime.datetime(2026, 11, 16, 12, 0, tzinfo=datetime.UTC)
    ai_msg = ChatMessage(
        id=101,
        selection_id=55,
        event_id=7,
        sender_role="ai_assistant",
        message_text="Точных данных по этому вопросу нет в открытом регламенте.",
        needs_manager_attention=True,
        created_at=now,
    )
    client_msg = ChatMessage(
        id=102,
        selection_id=55,
        event_id=7,
        sender_role="client",
        message_text="Возможна ли скидка при участии двух спикеров?",
        needs_manager_attention=True,
        created_at=now + datetime.timedelta(seconds=5),
    )

    captured_chat_sql: list[str] = []

    async def override_session():
        mock_session = AsyncMock()

        async def _get(model, ident):
            if model is Selection and ident == 55:
                return Selection(
                    id=55,
                    client_id=10,
                    status="published",
                    total_budget_limit=200000.0,
                )
            if model is Client and ident == 10:
                return Client(
                    id=10,
                    manager_id=1,
                    company_name="Девелопмент-Юг",
                    raw_manager_notes="Тестовая заметка",
                )
            return None

        async def _execute(stmt):
            sql_str = str(stmt.compile(compile_kwargs={"literal_binds": True}))
            mock_res = MagicMock()
            if "FROM chat_messages" in sql_str:
                captured_chat_sql.append(sql_str)
                rows = [(ai_msg, test_event), (client_msg, test_event)]
                if "needs_manager_attention IS true" in sql_str:
                    filtered = [
                        (msg, ev)
                        for msg, ev in rows
                        if msg.sender_role == "client" and msg.needs_manager_attention
                    ]
                else:
                    filtered = [
                        (msg, ev)
                        for msg, ev in rows
                        if msg.sender_role in ("client", "manager")
                    ]
                mock_res.all.return_value = filtered
                return mock_res
            mock_res.all.return_value = []
            return mock_res

        mock_session.get = _get
        mock_session.execute = _execute
        yield mock_session

    app.dependency_overrides[get_async_session] = override_session

    res = client.get("/api/manager/selections/55/activity")
    assert res.status_code == 200, res.text
    assert len(captured_chat_sql) >= 1
    assert any(
        "chat_messages.sender_role = 'client'" in sql and "needs_manager_attention IS true" in sql
        for sql in captured_chat_sql
    )

    data = res.json()
    assert data["selection_id"] == 55
    assert len(data["pending_questions"]) == 1
    assert data["pending_questions"][0]["message_id"] == 102
    assert data["pending_questions"][0]["question_text"] == "Возможна ли скидка при участии двух спикеров?"
    assert data["pending_questions"][0]["event_title"] == "Форум КРТ 2026"


def test_benchmark_cleanup_deletes_only_tracked_messages():
    """Очистка бенчмарка удаляет только отслеживаемые тестовые строки, не трогая обычные диалоги."""
    import asyncio
    import datetime

    import tests.run_benchmark as bench_mod
    from app.models.models import ChatMessage

    now = datetime.datetime(2026, 11, 16, 12, 0, tzinfo=datetime.UTC)
    existing_client = ChatMessage(
        id=10, selection_id=128, event_id=16, sender_role="client", message_text="Реальный вопрос", created_at=now
    )
    existing_ai = ChatMessage(
        id=11, selection_id=128, event_id=16, sender_role="ai_assistant", message_text="Реальный ответ", created_at=now
    )
    bench_client = ChatMessage(
        id=50,
        selection_id=128,
        event_id=16,
        sender_role="client",
        message_text="Тест (ts_123)",
        created_at=now + datetime.timedelta(seconds=10),
    )
    bench_ai = ChatMessage(
        id=51,
        selection_id=128,
        event_id=16,
        sender_role="ai_assistant",
        message_text="Ответ ИИ",
        created_at=now + datetime.timedelta(seconds=10),
    )
    concurrent_real = ChatMessage(
        id=52,
        selection_id=128,
        event_id=16,
        sender_role="client",
        message_text="Живой вопрос клиента",
        created_at=now + datetime.timedelta(seconds=12),
    )

    all_rows = [existing_client, existing_ai, bench_client, bench_ai, concurrent_real]
    deleted_stmts: list[str] = []

    class FakeCtx:
        def __init__(self, session):
            self._s = session

        async def __aenter__(self):
            return self._s

        async def __aexit__(self, exc_type, exc, tb):
            return False

    async def _test():
        mock_session = AsyncMock()

        async def _execute(stmt):
            sql_str = str(stmt.compile(compile_kwargs={"literal_binds": True}))
            mock_res = MagicMock()
            if sql_str.startswith("DELETE"):
                deleted_stmts.append(sql_str)
                return mock_res
            mock_res.scalars.return_value.all.return_value = [m for m in all_rows if m.id > 11]
            return mock_res

        mock_session.execute = _execute
        scope = bench_mod.TrackedChatScope(
            min_id=11,
            selection_id=128,
            event_id=16,
            questions={"Тест (ts_123)"},
            answers={"Ответ ИИ"},
        )
        with patch.object(bench_mod, "async_session_maker", return_value=FakeCtx(mock_session)):
            deleted_count = await bench_mod._cleanup_benchmark_chat_messages([scope])

        assert deleted_count == 2
        assert len(deleted_stmts) == 1
        assert "50" in deleted_stmts[0] and "51" in deleted_stmts[0]
        assert "52" not in deleted_stmts[0]
        assert "10" not in deleted_stmts[0]

    asyncio.run(_test())


def test_fallback_pitch_without_themes_has_no_tautology():
    """При пустом themes_keywords шаблон КП не содержит тавтологии 'по направлениям: ключевым отраслевым направлениям'."""
    import datetime

    from app.models.models import Event
    from app.schemas.manager import ClientQueryExtracted, TariffOptionOut
    from app.services.matcher import (
        EvaluatedCombo,
        ScoredEventCandidate,
        build_fallback_pitch,
    )

    ev = Event(
        id=1,
        canonical_title="Форум КРТ",
        city="Москва",
        is_online=False,
        start_date=datetime.date(2026, 11, 20),
        end_date=datetime.date(2026, 11, 20),
    )
    tariff = TariffOptionOut(
        tariff_id=10,
        tariff_name="Делегат",
        participation_role="delegate",
        actual_price=50000.0,
        base_price=50000.0,
    )
    cand = ScoredEventCandidate(
        event=ev, rrf_score=0.5, all_tariffs=[tariff], priced_tariffs=[tariff], on_request_tariffs=[]
    )
    combo = EvaluatedCombo(
        candidates=(cand,),
        chosen_tariffs=(tariff,),
        total_actual_price=50000.0,
        total_base_price=50000.0,
        total_savings=0.0,
        earliest_deadline=None,
        combo_score=0.5,
        is_over_budget_tolerance=False,
        matched_speaker_count=0,
    )
    profile = ClientQueryExtracted(
        themes_keywords=[],
        total_budget_max=100000.0,
        semantic_search_query="профильные форумы",
    )
    pitch = build_fallback_pitch("ГК Тест", profile, combo)
    assert "по ключевым отраслевым направлениям." in pitch
    assert "по направлениям: ключевым" not in pitch


def test_generate_selection_pitch_endpoint_success_fallback_validation_and_idor(client):
    """Проверка POST /api/manager/selections/{id}/pitch: LLM успех, fallback при сбое, 400 и IDOR 404."""
    import datetime
    from types import SimpleNamespace

    import app.services.matcher as matcher_pkg
    from app.core.security import get_current_manager
    from app.models.models import Client, Event, EventTariff, Selection

    today = datetime.date.today()
    ev1 = Event(
        id=101,
        canonical_title="Форум Девелопмент 2026",
        event_format="forum",
        city="Москва",
        is_online=False,
        start_date=today + datetime.timedelta(days=10),
        end_date=today + datetime.timedelta(days=11),
        themes=["КРТ", "ИЖС"],
    )
    ev2 = Event(
        id=102,
        canonical_title="Саммит СтройТех",
        event_format="conference",
        city="Санкт-Петербург",
        is_online=False,
        start_date=today + datetime.timedelta(days=20),
        end_date=today + datetime.timedelta(days=21),
        themes=["Цифровизация"],
    )
    tar1 = EventTariff(
        id=1001,
        event_id=101,
        tariff_name="Спикер сессии",
        participation_role="speaker",
        base_price=200000.0,
        early_bird_price=150000.0,
        early_bird_deadline=today + datetime.timedelta(days=5),
    )
    tar2 = EventTariff(
        id=1002,
        event_id=102,
        tariff_name="Делегат",
        participation_role="delegate",
        base_price=80000.0,
        early_bird_price=None,
        early_bird_deadline=None,
    )
    tar_other_event = EventTariff(
        id=1999,
        event_id=999,
        tariff_name="Чужой тариф",
        participation_role="delegate",
        base_price=50000.0,
    )

    owned_client = Client(
        id=10,
        manager_id=1,
        company_name="ГК Пионер",
        raw_manager_notes="Нужны форумы по КРТ и цифровизации",
        extracted_profile={
            "cities": ["Москва"],
            "include_online": True,
            "total_budget_max": 350000.0,
            "target_events_count": 2,
            "themes_keywords": ["КРТ"],
            "semantic_search_query": "форумы КРТ",
            "budget_is_assumed": False,
        },
    )
    foreign_client = Client(
        id=20,
        manager_id=2,
        company_name="Чужая компания",
        raw_manager_notes="",
        extracted_profile={},
    )
    owned_selection = Selection(
        id=50,
        client_id=10,
        status="draft",
        total_budget_limit=350000.0,
        generated_pitch_text="Старый черновик",
    )
    foreign_selection = Selection(
        id=60,
        client_id=20,
        status="draft",
        total_budget_limit=200000.0,
        generated_pitch_text="Чужой черновик",
    )

    def _make_session():
        mock_session = AsyncMock()

        async def _get(model, pk):
            if model is Client:
                return {10: owned_client, 20: foreign_client}.get(pk)
            if model is Selection:
                return {50: owned_selection, 60: foreign_selection}.get(pk)
            return None

        async def _execute(stmt):
            sql_text = str(stmt)
            res = MagicMock()
            if "FROM selections" in sql_text:
                # Проверяем ID по параметрам запроса, если переданы
                params = stmt.compile().params
                sel_id = next(iter(params.values()), 50)
                res.scalar_one_or_none.return_value = {50: owned_selection, 60: foreign_selection}.get(sel_id)
                return res
            if "FROM events" in sql_text:
                params = stmt.compile().params
                ids = set()
                for v in params.values():
                    if isinstance(v, (list, tuple, set)):
                        ids.update(v)
                    elif isinstance(v, int):
                        ids.add(v)
                res.scalars.return_value.all.return_value = [e for e in (ev1, ev2) if e.id in ids]
                return res
            if "FROM event_tariffs" in sql_text:
                params = stmt.compile().params
                ids = set()
                for v in params.values():
                    if isinstance(v, (list, tuple, set)):
                        ids.update(v)
                    elif isinstance(v, int):
                        ids.add(v)
                res.scalars.return_value.all.return_value = [
                    t for t in (tar1, tar2, tar_other_event) if t.id in ids
                ]
                return res
            res.scalar_one_or_none.return_value = None
            res.scalars.return_value.all.return_value = []
            return res

        mock_session.get = _get
        mock_session.execute = _execute
        return mock_session

    mock_session = _make_session()

    async def override_session():
        yield mock_session

    app.dependency_overrides[get_async_session] = override_session
    app.dependency_overrides[get_current_manager] = lambda: User(
        id=1, email="m@skart.ru", password_hash="x", full_name="Менеджер"
    )

    # 1. Успешная живая генерация через замоканный structured_llm_client
    captured_messages = []

    async def fake_create(**kwargs):
        captured_messages.append(kwargs["messages"])
        return SimpleNamespace(generated_pitch_text="Живое письмо для ГК Пионер на 230 000 ₽.")

    mock_llm_client = MagicMock()
    mock_llm_client.chat.completions.create = AsyncMock(side_effect=fake_create)

    with (
        patch.object(matcher_pkg.settings, "LLM_API_KEY", "test-key"),
        patch.object(matcher_pkg, "structured_llm_client", mock_llm_client),
    ):
        res_ok = client.post(
            "/api/manager/selections/50/pitch",
            json={
                "final_items": [
                    {"event_id": 101, "tariff_id": 1001},
                    {"event_id": 102, "tariff_id": 1002},
                ],
                "raw_manager_notes": "Хотим выступить спикером и посетить саммит",
                "total_budget_max": 350000,
                "include_budget_limit": True,
            },
        )

    assert res_ok.status_code == 200
    body_ok = res_ok.json()
    assert body_ok["selection_id"] == 50
    assert body_ok["used_llm"] is True
    assert body_ok["generated_pitch_text"] == "Живое письмо для ГК Пионер на 230 000 ₽."
    assert owned_selection.generated_pitch_text == "Живое письмо для ГК Пионер на 230 000 ₽."
    assert mock_session.commit.await_count == 1
    # Проверяем, что LLM получила точные Python-цифры: 150000 + 80000 = 230000, базовая 280000, экономия 50000
    user_msg = captured_messages[0][1]["content"]
    assert "230000" in user_msg
    assert "280000" in user_msg
    assert "50000" in user_msg

    # 2. Безопасный откат на build_fallback_pitch при сбое LLM (used_llm=False)
    failing_llm_client = MagicMock()
    failing_llm_client.chat.completions.create = AsyncMock(side_effect=TimeoutError("LLM timeout"))

    with (
        patch.object(matcher_pkg.settings, "LLM_API_KEY", "test-key"),
        patch.object(matcher_pkg, "structured_llm_client", failing_llm_client),
    ):
        res_fb = client.post(
            "/api/manager/selections/50/pitch",
            json={
                "final_items": [
                    {"event_id": 101, "tariff_id": 1001},
                    {"event_id": 102, "tariff_id": 1002},
                ],
            },
        )

    assert res_fb.status_code == 200
    body_fb = res_fb.json()
    assert body_fb["used_llm"] is False
    assert "ГК Пионер" in body_fb["generated_pitch_text"]
    assert "230 000 ₽" in body_fb["generated_pitch_text"]

    # 3. Неверная связка (event_id, tariff_id) -> 400
    res_bad_pair = client.post(
        "/api/manager/selections/50/pitch",
        json={
            "final_items": [{"event_id": 101, "tariff_id": 1999}],
        },
    )
    assert res_bad_pair.status_code == 400

    # 4. IDOR чужой подборки -> 404
    res_idor = client.post(
        "/api/manager/selections/60/pitch",
        json={
            "final_items": [{"event_id": 101, "tariff_id": 1001}],
        },
    )
    assert res_idor.status_code == 404
