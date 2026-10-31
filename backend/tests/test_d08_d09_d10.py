import datetime
import json
import socket
import sys
import unittest
from pathlib import Path
from uuid import UUID, uuid4
import httpx

# Добавляем backend в sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.main import app
from app.core.database import engine, get_async_session
from app.models.models import (
    ChatMessage,
    Client,
    Event,
    EventTariff,
    LLMCache,
    Selection,
    SelectionItem,
    User,
)
from app.services.rag import ask_regulation_question, build_rag_cache_key
from app.services.telegram import (
    escape_html,
    format_escalation_alert,
    format_reaction_alert,
    send_manager_alert,
)


def is_postgres_online() -> bool:
    """Проверяет доступность TCP-порта PostgreSQL (5432) на localhost или db."""
    for host in ("localhost", "127.0.0.1", "db"):
        try:
            with socket.create_connection((host, 5432), timeout=0.5):
                return True
        except OSError:
            continue
    return False


class InMemoryResult:
    """Эмуляция результата SQLAlchemy execute() для изолированного тестирования без СУБД."""

    def __init__(self, items: list):
        self._items = items

    def scalar_one_or_none(self):
        if len(self._items) > 1:
            raise RuntimeError("MultipleResultsFound: expected at most one row")
        return self._items[0] if self._items else None

    def scalar_one(self):
        return self._items[0]

    def scalars(self):
        return self

    def first(self):
        return self._items[0] if self._items else None

    def all(self):
        return list(self._items)


class InMemoryAsyncSession:
    """
    Легковесная in-memory сессия для тестирования всех ветвей бизнес-логики
    manager.py, showcase.py и rag.py (включая кэш, чат, публикацию и защиту от IDOR).
    """

    def __init__(self):
        today = datetime.date.today()
        self.users = {
            1: User(id=1, email="manager@skart.ru", password_hash="x", full_name="Анна Соколова", telegram_chat_id=123456789)
        }
        self.clients = {
            1: Client(
                id=1,
                manager_id=1,
                company_name="ГК «Пионер»",
                contact_person="Игорь Ветров",
                raw_manager_notes="Нужны 3 мероприятия по КРТ в Москве и СПб, бюджет 400 тыс.",
            )
        }
        self.events = {
            1: Event(
                id=1,
                canonical_title="Круглый стол Ведомостей: Практика КРТ 2026",
                normalized_title="круглый стол ведомостей: практика крт 2026",
                event_format="roundtable",
                city="Москва",
                is_online=False,
                venue="Отель Континенталь, Тверская 22",
                start_date=today + datetime.timedelta(days=20),
                end_date=today + datetime.timedelta(days=20),
                summary="Закрытая дискуссия девелоперов по механизмам КРТ.",
                full_regulation_markdown=(
                    "# Регламент Круглого стола Ведомостей: Практика КРТ 2026\n"
                    "Место проведения: Отель Континенталь, Москва, ул. Тверская 22.\n"
                    "Для участников предусмотрена подземная парковка отеля по предварительной аккредитации номеров авто.\n"
                    "Пакет Спикер включает 15-минутное выступление в пленарной сессии и 2 делегатских билета."
                ),
                themes=["КРТ", "девелопмент"],
                is_active=True,
            ),
            2: Event(
                id=2,
                canonical_title="Деловой завтрак Коммерсантъ: Урбанистика",
                normalized_title="деловой завтрак коммерсантъ: урбанистика",
                event_format="business_breakfast",
                city="Санкт-Петербург",
                is_online=False,
                venue="Отель Астория",
                start_date=today + datetime.timedelta(days=30),
                end_date=today + datetime.timedelta(days=30),
                summary="Встреча руководителей архитектурных бюро.",
                full_regulation_markdown="# Регламент делового завтрака\nУчастие по спискам аккредитации.",
                themes=["урбанистика", "КРТ"],
                is_active=True,
            ),
            3: Event(
                id=3,
                canonical_title="Итоговая конференция ЕРЗ.РФ: Тренды девелопмента",
                normalized_title="итоговая конференция ерз.рф: тренды девелопмента",
                event_format="conference",
                city="Москва",
                is_online=False,
                venue="ЦДП (Цифровое деловое пространство)",
                start_date=today + datetime.timedelta(days=40),
                end_date=today + datetime.timedelta(days=40),
                summary="Ежегодная аналитическая конференция застройщиков жилья РФ.",
                full_regulation_markdown="# Регламент конференции ЕРЗ.РФ\nУчастие застройщиков.",
                themes=["КРТ", "девелопмент", "аналитика"],
                is_active=True,
            ),
        }
        self.tariffs = {
            11: EventTariff(
                id=11,
                event_id=1,
                tariff_name="Пакет Спикер",
                participation_role="speaker",
                base_price=160000.0,
                early_bird_price=135000.0,
                early_bird_deadline=today + datetime.timedelta(days=10),
                included_benefits="Выступление 15 мин, 2 билета делегата, пост-релиз.",
            ),
            12: EventTariff(
                id=12,
                event_id=1,
                tariff_name="Делегат Стандарт",
                participation_role="delegate",
                base_price=60000.0,
                early_bird_price=45000.0,
                early_bird_deadline=today + datetime.timedelta(days=10),
                included_benefits="Участие в зале, кофе-брейк.",
            ),
            21: EventTariff(
                id=21,
                event_id=2,
                tariff_name="Делегат VIP",
                participation_role="delegate",
                base_price=90000.0,
                early_bird_price=75000.0,
                early_bird_deadline=today + datetime.timedelta(days=12),
                included_benefits="Доступ к закрытому завтраку.",
            ),
            31: EventTariff(
                id=31,
                event_id=3,
                tariff_name="Делегат Стандарт",
                participation_role="delegate",
                base_price=70000.0,
                early_bird_price=55000.0,
                early_bird_deadline=today + datetime.timedelta(days=15),
                included_benefits="Доступ в залы конференции.",
            ),
        }
        self.events[1].tariffs = [self.tariffs[11], self.tariffs[12]]
        self.events[2].tariffs = [self.tariffs[21]]
        self.events[3].tariffs = [self.tariffs[31]]

        self.token_published = UUID("11111111-2222-4333-8444-555555555555")
        self.selections = {
            1: Selection(
                id=1,
                client_id=1,
                magic_token=uuid4(),
                status="draft",
                generated_pitch_text="Черновик КП",
                total_budget_limit=400000.0,
            ),
            2: Selection(
                id=2,
                client_id=1,
                magic_token=self.token_published,
                status="published",
                generated_pitch_text="Опубликованное КП для ГК Пионер",
                total_budget_limit=210000.0,
            ),
        }
        # В черновике Selection(id=1) специально дублируем event_id=1 в группе 1 и группе 2!
        self.selection_items = [
            SelectionItem(id=101, selection_id=1, event_id=1, recommended_tariff_id=11, bundle_group=1, ai_rationale="Пакет 1", client_reaction="pending"),
            SelectionItem(id=102, selection_id=1, event_id=1, recommended_tariff_id=12, bundle_group=2, ai_rationale="Пакет 2", client_reaction="pending"),
            SelectionItem(id=201, selection_id=2, event_id=1, recommended_tariff_id=11, bundle_group=1, ai_rationale="Спикер КРТ", client_reaction="pending"),
            SelectionItem(id=202, selection_id=2, event_id=2, recommended_tariff_id=21, bundle_group=1, ai_rationale="Делегат СПб", client_reaction="pending"),
        ]
        self._next_item_id = 300

        faq_key = build_rag_cache_key(1, 11, "Что входит в рекомендованный тариф?")
        self.llm_cache = {
            faq_key: LLMCache(
                cache_key=faq_key,
                event_id=1,
                response_text=json.dumps(
                    {
                        "is_answer_found": True,
                        "answer_text": "В тариф Пакет Спикер входит 15-минутное выступление и 2 билета делегата.",
                        "source_quote": "Пакет Спикер включает 15-минутное выступление в пленарной сессии и 2 делегатских билета.",
                    },
                    ensure_ascii=False,
                ),
            )
        }
        self.chat_messages: list[ChatMessage] = []
        self.commits_count = 0

    async def get(self, model_cls, ident):
        if model_cls is User:
            return self.users.get(ident)
        if model_cls is Client:
            return self.clients.get(ident)
        if model_cls is Event:
            return self.events.get(ident)
        if model_cls is EventTariff:
            return self.tariffs.get(ident)
        if model_cls is Selection:
            return self.selections.get(ident)
        if model_cls is LLMCache:
            return self.llm_cache.get(ident)
        if model_cls is SelectionItem:
            for it in self.selection_items:
                if it.id == ident:
                    return it
        return None

    async def execute(self, stmt):
        sql_str = str(stmt).lower()
        params = stmt.compile().params

        if "delete from selection_items" in sql_str:
            sel_id = next((v for k, v in params.items() if "selection_id" in k), None)
            self.selection_items = [it for it in self.selection_items if it.selection_id != sel_id]
            return InMemoryResult([])

        if "from llm_cache" in sql_str:
            ck = next((v for k, v in params.items() if "cache_key" in k), None)
            entry = self.llm_cache.get(ck)
            return InMemoryResult([entry] if entry else [])

        if "from selection_items" in sql_str:
            results = list(self.selection_items)
            for k, v in params.items():
                if "selection_id" in k:
                    results = [it for it in results if it.selection_id == v]
                elif "event_id" in k:
                    results = [it for it in results if it.event_id == v]
                elif "bundle_group" in k:
                    results = [it for it in results if it.bundle_group == v]
                elif k.startswith("id"):
                    results = [it for it in results if it.id == v]
            if "limit" in sql_str:
                results = results[:1]
            return InMemoryResult(results)

        if "from selections" in sql_str:
            results = list(self.selections.values())
            for k, v in params.items():
                if "magic_token" in k:
                    results = [s for s in results if s.magic_token == v]
                elif "status" in k:
                    results = [s for s in results if s.status == v]
                elif "client_id" in k:
                    results = [s for s in results if s.client_id == v]
                elif k.startswith("id"):
                    results = [s for s in results if s.id == v]
            if "order by" in sql_str:
                results.sort(key=lambda x: x.id, reverse=True)
            if "limit" in sql_str:
                results = results[:1]
            return InMemoryResult(results)

        if "from clients" in sql_str:
            return InMemoryResult(list(self.clients.values()))

        if "candidates" in sql_str or "ranked" in sql_str or "rrf_score" in sql_str:
            return InMemoryResult([(ev, 0.032) for ev in self.events.values()])

        if "from event_tariffs" in sql_str:
            if "join events" in sql_str:
                pairs = [(t, self.events[t.event_id]) for t in self.tariffs.values()]
                return InMemoryResult(pairs)
            return InMemoryResult(list(self.tariffs.values()))

        if "from events" in sql_str:
            return InMemoryResult(list(self.events.values()))

        return InMemoryResult([])

    def add(self, obj):
        if isinstance(obj, ChatMessage):
            self.chat_messages.append(obj)
        elif isinstance(obj, LLMCache):
            self.llm_cache[obj.cache_key] = obj
        elif isinstance(obj, SelectionItem):
            if not obj.id:
                self._next_item_id += 1
                obj.id = self._next_item_id
            self.selection_items.append(obj)
        elif isinstance(obj, Selection):
            if not obj.id:
                obj.id = max(self.selections.keys(), default=0) + 1
            if not obj.magic_token:
                obj.magic_token = uuid4()
            self.selections[obj.id] = obj

    async def flush(self):
        pass

    async def commit(self):
        self.commits_count += 1

    async def refresh(self, obj):
        pass

    async def rollback(self):
        pass


class TestD08D09D10Suite(unittest.IsolatedAsyncioTestCase):
    """
    Комплексный аудит и тестирование задач D-08, D-09 и D-10.
    Проверяет все исправленные дефекты:
    1. Безопасное HTML-экранирование и маршрутизацию Telegram-алертов по chat_id менеджера.
    2. Защиту rag.py от падения MultipleResultsFound на черновиках с двумя пакетами.
    3. Сохранение истории чата (chat_messages) и коммит транзакции при попадании в llm_cache.
    4. Context Stuffing и Zero-Hallucination (отказ от выдумывания + эскалация в Telegram).
    5. Валидацию принадлежности тарифов событиям в PUT /api/manager/selections/{id}/publish.
    6. Защиту публичной витрины от IDOR-атак в POST /api/public/s/{magic_token}/items/{id}/react.
    """

    async def asyncSetUp(self):
        self.fake_db = InMemoryAsyncSession()

        async def _override_session():
            yield self.fake_db

        app.dependency_overrides[get_async_session] = _override_session
        self.transport = httpx.ASGITransport(app=app)
        self.client = httpx.AsyncClient(transport=self.transport, base_url="http://testserver", timeout=45.0)

    async def asyncTearDown(self):
        app.dependency_overrides.pop(get_async_session, None)
        await self.client.aclose()
        await engine.dispose()

    async def test_01_telegram_html_escaping_and_alert(self):
        """Проверка экранирования спецсимволов HTML (<, >, &) и отправки алерта."""
        raw_comment = "Бюджет < 300к & нужен стенд > 10 м2"
        escaped = escape_html(raw_comment)
        self.assertIn("&lt;", escaped)
        self.assertIn("&gt;", escaped)
        self.assertIn("&amp;", escaped)

        alert = format_reaction_alert("ГК <Тест>", "Форум & Выставка", "interested", raw_comment)
        self.assertIn("<b>Реакция клиента", alert)
        self.assertIn("ГК &lt;Тест&gt;", alert)
        self.assertIn("Форум &amp; Выставка", alert)
        self.assertIn("Этап 09", alert)

        esc_alert = format_escalation_alert("ГК <Тест>", "Форум & Выставка", "Вопрос <1>?")
        self.assertIn("Вопрос &lt;1&gt;?", esc_alert)

        ok = await send_manager_alert(esc_alert, chat_id=123456789)
        self.assertTrue(ok)

    async def test_02_rag_duplicate_bundle_groups_and_cache_commit(self):
        """
        Проверка:
        1) Отсутствия MultipleResultsFound при наличии события сразу в bundle_group=1 и bundle_group=2 (Selection id=1).
        2) Сохранения сообщений в chat_messages и вызова session.commit() при попадании в llm_cache.
        """
        commits_before = self.fake_db.commits_count
        msgs_before = len(self.fake_db.chat_messages)

        rag_out = await ask_regulation_question(
            session=self.fake_db,  # type: ignore[arg-type]
            selection_id=1,
            event_id=1,
            question_text="Что входит в рекомендованный тариф?",
        )
        self.assertTrue(rag_out.is_answer_found)
        self.assertTrue(rag_out.from_cache)
        self.assertFalse(rag_out.escalated_to_telegram)
        self.assertEqual(len(self.fake_db.chat_messages), msgs_before + 2)
        self.assertEqual(self.fake_db.commits_count, commits_before + 1)

    async def test_03_rag_context_stuffing_and_zero_hallucination(self):
        """
        Проверка живого вызова LLM через Context Stuffing (парковка в регламенте)
        и Zero-Hallucination (вертолетный трансфер вне регламента -> эскалация в Telegram).
        """
        # 1. Вопрос, ответ на который есть в тексте регламента (про подземную парковку)
        res_found = await ask_regulation_question(
            session=self.fake_db,  # type: ignore[arg-type]
            selection_id=2,
            event_id=1,
            question_text="Предусмотрена ли парковка для участников круглого стола?",
        )
        self.assertFalse(res_found.from_cache)
        self.assertTrue(res_found.is_answer_found)
        self.assertIsNotNone(res_found.source_quote)
        self.assertFalse(res_found.escalated_to_telegram)

        # Повторный вопрос должен мгновенно прийти из llm_cache!
        res_cached = await ask_regulation_question(
            session=self.fake_db,  # type: ignore[arg-type]
            selection_id=2,
            event_id=1,
            question_text="Предусмотрена ли парковка для участников круглого стола?",
        )
        self.assertTrue(res_cached.from_cache)
        self.assertTrue(res_cached.is_answer_found)

        # 2. Провокационный вопрос вне регламента -> отказ и эскалация в Telegram
        res_prov = await ask_regulation_question(
            session=self.fake_db,  # type: ignore[arg-type]
            selection_id=2,
            event_id=1,
            question_text="Предоставляется ли бесплатный вертолет из аэропорта до отеля?",
        )
        self.assertFalse(res_prov.is_answer_found)
        self.assertIsNone(res_prov.source_quote)
        # Автоматическая эскалация отключена: по умолчанию False
        self.assertFalse(res_prov.escalated_to_telegram)
        self.assertTrue(self.fake_db.chat_messages[-1].needs_manager_attention)

    async def test_04_manager_publish_validation_and_pricing(self):
        """
        Проверка D-08:
        - GET /api/manager/clients возвращает клиентов и горящие дедлайны из БД;
        - PUT /api/manager/selections/{id}/publish отклоняет пустой список и чужой тариф (400);
        - Успешно публикует валидный пакет, удаляя черновые альтернативы и рассчитывая Early Bird экономию.
        """
        dash_resp = await self.client.get("/api/manager/clients")
        self.assertEqual(dash_resp.status_code, 200)
        self.assertGreaterEqual(len(dash_resp.json()["burning_deadlines"]), 1)

        catalog_resp = await self.client.get("/api/manager/events")
        self.assertEqual(catalog_resp.status_code, 200)
        cat_data = catalog_resp.json()
        self.assertEqual(cat_data["total_count"], 3)
        self.assertEqual(len(cat_data["events"]), 3)
        self.assertGreaterEqual(len(cat_data["events"][0]["tariffs"]), 1)

        # Попытка привязать тариф #21 (от события #2) к событию #1 -> 400 Bad Request
        bad_resp = await self.client.put(
            "/api/manager/selections/1/publish",
            json={
                "selected_bundle_group": 1,
                "final_items": [{"event_id": 1, "tariff_id": 21, "ai_rationale": "Неверный тариф"}],
                "final_pitch_text": "Текст КП",
            },
        )
        self.assertEqual(bad_resp.status_code, 400)
        self.assertIn("не принадлежит", bad_resp.json()["detail"])

        # Валидная публикация Selection #1 (Событие #1 с тарифом #11 + Событие #2 с тарифом #21)
        ok_resp = await self.client.put(
            "/api/manager/selections/1/publish",
            json={
                "selected_bundle_group": 1,
                "final_items": [
                    {"event_id": 1, "tariff_id": 11, "ai_rationale": "Спикер КРТ"},
                    {"event_id": 2, "tariff_id": 21, "ai_rationale": "Делегат СПб"},
                ],
                "final_pitch_text": "Финальное согласованное КП",
            },
        )
        self.assertEqual(ok_resp.status_code, 200, ok_resp.text)
        pub_data = ok_resp.json()
        self.assertEqual(pub_data["status"], "published")
        # 135 000 + 75 000 = 210 000 ₽; экономия (160к-135к) + (90к-75к) = 40 000 ₽
        self.assertEqual(pub_data["total_package_price"], 210000.0)
        self.assertEqual(pub_data["total_package_savings"], 40000.0)

    async def test_05_public_showcase_idor_and_reactions(self):
        """
        Проверка D-10:
        - Загрузка витрины по magic_token;
        - Защита от IDOR: реакция на элемент из другой подборки (item_id=101 принадлежит selection_id=1, а не 2) отклоняется с 404;
        - Реакция на свой элемент (item_id=201) сохраняется и отправляет уведомление менеджеру.
        """
        token = str(self.fake_db.token_published)

        show_resp = await self.client.get(f"/api/public/s/{token}")
        self.assertEqual(show_resp.status_code, 200)
        show_data = show_resp.json()
        self.assertEqual(show_data["company_name"], "ГК «Пионер»")
        self.assertEqual(show_data["total_events_count"], 2)

        # Попытка IDOR: item_id=101 принадлежит подборке #1, а мы обращаемся по токену подборки #2
        idor_resp = await self.client.post(
            f"/api/public/s/{token}/items/101/react",
            json={"reaction": "rejected", "comment": "Попытка изменить чужую подборку"},
        )
        self.assertEqual(idor_resp.status_code, 404)

        # Легитимная реакция на элемент своей витрины (item_id=201)
        react_resp = await self.client.post(
            f"/api/public/s/{token}/items/201/react",
            json={"reaction": "interested", "comment": "Отлично <бронируем> & ждем договор"},
        )
        self.assertEqual(react_resp.status_code, 200)
        self.assertEqual(react_resp.json()["new_reaction"], "interested")
        self.assertTrue(react_resp.json()["manager_notified"])

        # Запрос RAG к событию, не входящему в витрину (event_id=999) -> 404
        bad_ask = await self.client.post(
            f"/api/public/s/{token}/events/999/ask",
            json={"question_text": "Что входит в рекомендованный тариф?"},
        )
        self.assertEqual(bad_ask.status_code, 404)


if __name__ == "__main__":
    unittest.main()
