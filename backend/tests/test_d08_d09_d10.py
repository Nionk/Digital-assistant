import datetime
import json
import socket
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import httpx
from sqlalchemy import delete, select

# Добавляем backend в sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import settings
from app.core.database import async_session_maker, engine
from app.core.security import create_access_token
from app.main import app
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
from app.services.rag import (
    RAGUnavailableError,
    ask_regulation_question,
    build_rag_cache_key,
)
from app.services.telegram import (
    HttpTelegramTransport,
    StubTelegramTransport,
    escape_html,
    format_escalation_alert,
    format_monitoring_summary_alert,
    format_reaction_alert,
    send_manager_alert,
    set_telegram_transport,
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


@unittest.skipUnless(is_postgres_online(), "Требуется запущенный контейнер PostgreSQL")
class TestD08D09D10Suite(unittest.IsolatedAsyncioTestCase):
    """
    Комплексный интеграционный тест задач D-08, D-09 и D-10 на реальном PostgreSQL.
    Проверяет:
    1. Безопасное HTML-экранирование и маршрутизацию Telegram-алертов по chat_id менеджера.
    2. Защиту rag.py от падения MultipleResultsFound на черновиках с двумя пакетами.
    3. Сохранение истории чата (chat_messages) и коммит транзакции при попадании в llm_cache.
    4. Context Stuffing и Zero-Hallucination (отказ от выдумывания + флаг needs_manager_attention).
    5. Валидацию принадлежности тарифов событиям в PUT /api/manager/selections/{id}/publish.
    6. Защиту публичной витрины от IDOR-атак в POST /api/public/s/{magic_token}/items/{id}/react,
       ответ менеджера через /api/manager/selections/{id}/reply и отображение chat_messages в витрине.
    """

    async def asyncSetUp(self):
        self.stub_telegram = StubTelegramTransport()
        set_telegram_transport(self.stub_telegram)

        today = datetime.date.today()
        self.created_event_ids: list[int] = []
        self.created_selection_ids: list[int] = []
        self.created_client_id: int | None = None

        async with async_session_maker() as s:
            mgr = await s.get(User, 1)
            self.manager_id = mgr.id if mgr else 1
            self.auth_headers = {"Authorization": f"Bearer {create_access_token({'sub': str(self.manager_id)})}"}

            test_client = Client(
                manager_id=self.manager_id,
                company_name="ГК «Пионер»",
                contact_person="Игорь Ветров",
                raw_manager_notes="Тестовый клиент для D08-D10 интеграционных проверок.",
            )
            s.add(test_client)
            await s.flush()
            self.created_client_id = test_client.id

            ev1 = Event(
                canonical_title="Тестовый Круглый стол Ведомостей: Практика КРТ 2026",
                normalized_title="тестовый круглый стол ведомостей: практика крт 2026",
                event_format="roundtable",
                city="Москва",
                is_online=False,
                venue="Отель Континенталь, Тверская 22",
                start_date=today + datetime.timedelta(days=20),
                end_date=today + datetime.timedelta(days=20),
                summary=(
                    "Закрытая дискуссия девелоперов по механизмам комплексного развития территорий (КРТ), "
                    "практике согласования мастер-планов, инфраструктурным обязательствам и проектному финансированию "
                    "крупных городских кварталов с участием профильных департаментов и банков."
                ),
                full_regulation_markdown=(
                    "# Регламент Круглого стола Ведомостей: Практика КРТ 2026\n"
                    "Место проведения: Отель Континенталь, Москва, ул. Тверская 22.\n"
                    "Для участников предусмотрена подземная парковка отеля по предварительной аккредитации номеров авто.\n"
                    "Пакет Спикер включает 15-минутное выступление в пленарной сессии и 2 делегатских билета."
                ),
                themes=["КРТ", "девелопмент"],
                data_status="ready",
                is_active=True,
            )
            ev2 = Event(
                canonical_title="Тестовый Деловой завтрак Коммерсантъ: Урбанистика",
                normalized_title="тестовый деловой завтрак коммерсантъ: урбанистика",
                event_format="business_breakfast",
                city="Санкт-Петербург",
                is_online=False,
                venue="Отель Астория",
                start_date=today + datetime.timedelta(days=30),
                end_date=today + datetime.timedelta(days=30),
                summary=(
                    "Камерная встреча руководителей архитектурных бюро и девелоперских компаний Северо-Западного региона "
                    "по вопросам редевелопмента промышленных территорий, сохранения исторического наследия и экономики проектов."
                ),
                full_regulation_markdown="# Регламент делового завтрака\nУчастие по спискам аккредитации.",
                themes=["урбанистика", "КРТ"],
                data_status="ready",
                is_active=True,
            )
            s.add_all([ev1, ev2])
            await s.flush()
            self.ev1_id = ev1.id
            self.ev2_id = ev2.id
            self.created_event_ids.extend([ev1.id, ev2.id])

            t11 = EventTariff(
                event_id=ev1.id,
                tariff_name="Пакет Спикер",
                participation_role="speaker",
                base_price=160000.0,
                early_bird_price=135000.0,
                early_bird_deadline=today + datetime.timedelta(days=2),
                included_benefits="Выступление 15 мин, 2 билета делегата, пост-релиз.",
            )
            t12 = EventTariff(
                event_id=ev1.id,
                tariff_name="Делегат Стандарт",
                participation_role="delegate",
                base_price=60000.0,
                early_bird_price=45000.0,
                early_bird_deadline=today + datetime.timedelta(days=2),
                included_benefits="Участие в зале, кофе-брейк.",
            )
            t21 = EventTariff(
                event_id=ev2.id,
                tariff_name="Делегат VIP",
                participation_role="delegate",
                base_price=90000.0,
                early_bird_price=75000.0,
                early_bird_deadline=today + datetime.timedelta(days=12),
                included_benefits="Доступ к закрытому завтраку.",
            )
            s.add_all([t11, t12, t21])
            await s.flush()
            self.t11_id = t11.id
            self.t12_id = t12.id
            self.t21_id = t21.id

            self.token_draft = uuid4()
            self.token_published = uuid4()
            sel_draft = Selection(
                client_id=test_client.id,
                magic_token=self.token_draft,
                status="draft",
                generated_pitch_text="Черновик КП",
                total_budget_limit=400000.0,
            )
            sel_pub = Selection(
                client_id=test_client.id,
                magic_token=self.token_published,
                status="published",
                generated_pitch_text="Опубликованное КП для ГК Пионер",
                total_budget_limit=210000.0,
            )
            s.add_all([sel_draft, sel_pub])
            await s.flush()
            self.sel_draft_id = sel_draft.id
            self.sel_pub_id = sel_pub.id
            self.created_selection_ids.extend([sel_draft.id, sel_pub.id])

            # В черновике специально дублируем ev1 в bundle_group=1 и bundle_group=2
            it_d1 = SelectionItem(
                selection_id=sel_draft.id,
                event_id=ev1.id,
                recommended_tariff_id=t11.id,
                bundle_group=1,
                ai_rationale="Пакет 1",
                client_reaction="pending",
            )
            it_d2 = SelectionItem(
                selection_id=sel_draft.id,
                event_id=ev1.id,
                recommended_tariff_id=t12.id,
                bundle_group=2,
                ai_rationale="Пакет 2",
                client_reaction="pending",
            )
            it_p1 = SelectionItem(
                selection_id=sel_pub.id,
                event_id=ev1.id,
                recommended_tariff_id=t11.id,
                bundle_group=1,
                ai_rationale="Спикер КРТ",
                client_reaction="pending",
            )
            it_p2 = SelectionItem(
                selection_id=sel_pub.id,
                event_id=ev2.id,
                recommended_tariff_id=t21.id,
                bundle_group=1,
                ai_rationale="Делегат СПб",
                client_reaction="pending",
            )
            s.add_all([it_d1, it_d2, it_p1, it_p2])
            await s.flush()
            self.item_draft_id = it_d1.id
            self.item_pub_id = it_p1.id

            faq_key = build_rag_cache_key(ev1.id, t11.id, "Что входит в рекомендованный тариф?")
            s.add(
                LLMCache(
                    cache_key=faq_key,
                    event_id=ev1.id,
                    response_text=json.dumps(
                        {
                            "is_answer_found": True,
                            "answer_text": "В тариф Пакет Спикер входит 15-минутное выступление и 2 билета делегата.",
                            "source_quote": "Пакет Спикер включает 15-минутное выступление в пленарной сессии и 2 делегатских билета.",
                        },
                        ensure_ascii=False,
                    ),
                )
            )
            await s.commit()

        self.transport = httpx.ASGITransport(app=app)
        self.client = httpx.AsyncClient(transport=self.transport, base_url="http://testserver", timeout=45.0)

    async def asyncTearDown(self):
        set_telegram_transport(None)
        await self.client.aclose()

        async with async_session_maker() as s:
            if self.created_selection_ids:
                await s.execute(delete(ChatMessage).where(ChatMessage.selection_id.in_(self.created_selection_ids)))
                await s.execute(delete(SelectionItem).where(SelectionItem.selection_id.in_(self.created_selection_ids)))
                await s.execute(delete(Selection).where(Selection.id.in_(self.created_selection_ids)))
            if self.created_event_ids:
                await s.execute(delete(LLMCache).where(LLMCache.event_id.in_(self.created_event_ids)))
                await s.execute(delete(EventTariff).where(EventTariff.event_id.in_(self.created_event_ids)))
                await s.execute(delete(Event).where(Event.id.in_(self.created_event_ids)))
            if self.created_client_id is not None:
                await s.execute(delete(Client).where(Client.id == self.created_client_id))
            await s.commit()

        await engine.dispose()

    async def test_01_telegram_html_escaping_and_alert(self):
        """Проверка экранирования спецсимволов HTML (<, >, &), сводки мониторинга и честного контракта транспорта."""
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

        # При реакции 'rejected' задача сопровождения агентства НЕ должна добавляться
        rejected_alert = format_reaction_alert("ГК <Тест>", "Форум & Выставка", "rejected", raw_comment)
        self.assertNotIn("Этап 09", rejected_alert)

        esc_alert = format_escalation_alert("ГК <Тест>", "Форум & Выставка", "Вопрос <1>?")
        self.assertIn("Вопрос &lt;1&gt;?", esc_alert)

        summary_alert = format_monitoring_summary_alert(14, ["Форум <КРТ> & Девелопмент"])
        self.assertIn("14 новых мероприятий", summary_alert)
        self.assertIn("Форум &lt;КРТ&gt; &amp; Девелопмент", summary_alert)

        ok = await send_manager_alert(esc_alert)
        self.assertTrue(ok)
        self.assertEqual(len(self.stub_telegram.sent_messages), 1)

        # Проверка честного контракта боевого HttpTelegramTransport: при отсутствии кредов возвращает False
        http_transport = HttpTelegramTransport()
        with (
            patch.object(settings, "TELEGRAM_BOT_TOKEN", ""),
            patch.object(settings, "TELEGRAM_MANAGER_CHAT_ID", None),
        ):
            honest_res = await send_manager_alert(esc_alert, chat_id=None, transport=http_transport)
            self.assertFalse(honest_res)

    async def test_02_rag_duplicate_bundle_groups_and_cache_commit(self):
        """
        Проверка:
        1) Отсутствия MultipleResultsFound при наличии события сразу в bundle_group=1 и bundle_group=2.
        2) Сохранения сообщений в chat_messages в реальной БД при попадании в llm_cache.
        """
        async with async_session_maker() as s:
            rag_out = await ask_regulation_question(
                session=s,
                selection_id=self.sel_draft_id,
                event_id=self.ev1_id,
                question_text="Что входит в рекомендованный тариф?",
            )
            self.assertTrue(rag_out.is_answer_found)
            self.assertTrue(rag_out.from_cache)
            self.assertFalse(rag_out.escalated_to_telegram)

            msgs_res = await s.execute(
                select(ChatMessage).where(
                    ChatMessage.selection_id == self.sel_draft_id,
                    ChatMessage.event_id == self.ev1_id,
                )
            )
            msgs = msgs_res.scalars().all()
            self.assertEqual(len(msgs), 2)

    async def test_03_rag_context_stuffing_and_zero_hallucination(self):
        """
        Проверка живого вызова LLM через Context Stuffing (парковка в регламенте)
        и Zero-Hallucination (вертолетный трансфер вне регламента -> needs_manager_attention=True).
        """
        async with async_session_maker() as s:
            try:
                res_found = await ask_regulation_question(
                    session=s,
                    selection_id=self.sel_pub_id,
                    event_id=self.ev1_id,
                    question_text="Предусмотрена ли парковка для участников круглого стола?",
                )
            except RAGUnavailableError as exc:
                self.skipTest(f"Внешний LLM-шлюз временно недоступен: {exc}")

            self.assertFalse(res_found.from_cache)
            self.assertTrue(res_found.is_answer_found)
            self.assertIsNotNone(res_found.source_quote)
            self.assertFalse(res_found.escalated_to_telegram)

            # Повторный вопрос должен мгновенно прийти из llm_cache!
            res_cached = await ask_regulation_question(
                session=s,
                selection_id=self.sel_pub_id,
                event_id=self.ev1_id,
                question_text="Предусмотрена ли парковка для участников круглого стола?",
            )
            self.assertTrue(res_cached.from_cache)
            self.assertTrue(res_cached.is_answer_found)

            # 2. Провокационный вопрос вне регламента -> отказ и флаг needs_manager_attention=True
            try:
                res_prov = await ask_regulation_question(
                    session=s,
                    selection_id=self.sel_pub_id,
                    event_id=self.ev1_id,
                    question_text="Предоставляется ли бесплатный вертолет из аэропорта до отеля?",
                )
            except RAGUnavailableError as exc:
                self.skipTest(f"Внешний LLM-шлюз временно недоступен: {exc}")

            self.assertFalse(res_prov.is_answer_found)
            self.assertIsNone(res_prov.source_quote)
            self.assertFalse(res_prov.escalated_to_telegram)

            pending_res = await s.execute(
                select(ChatMessage).where(
                    ChatMessage.selection_id == self.sel_pub_id,
                    ChatMessage.event_id == self.ev1_id,
                    ChatMessage.sender_role == "client",
                    ChatMessage.needs_manager_attention.is_(True),
                )
            )
            self.assertIsNotNone(pending_res.scalars().first())

    async def test_04_manager_publish_validation_and_pricing(self):
        """
        Проверка D-08 на реальной БД:
        - GET /api/manager/clients возвращает клиентов и горящие дедлайны из БД;
        - PUT /api/manager/selections/{id}/publish отклоняет чужой тариф (400);
        - Успешно публикует валидный пакет, удаляя черновые альтернативы и рассчитывая Early Bird экономию.
        """
        dash_resp = await self.client.get("/api/manager/clients", headers=self.auth_headers)
        self.assertEqual(dash_resp.status_code, 200)
        self.assertGreaterEqual(len(dash_resp.json()["burning_deadlines"]), 1)

        catalog_resp = await self.client.get("/api/manager/events", headers=self.auth_headers)
        self.assertEqual(catalog_resp.status_code, 200)
        cat_data = catalog_resp.json()
        self.assertGreaterEqual(cat_data["total_count"], 2)
        self.assertGreaterEqual(len(cat_data["events"]), 2)
        self.assertGreaterEqual(len(cat_data["events"][0]["tariffs"]), 1)

        # Попытка привязать тариф от ev2 к ev1 -> 400 Bad Request
        bad_resp = await self.client.put(
            f"/api/manager/selections/{self.sel_draft_id}/publish",
            headers=self.auth_headers,
            json={
                "selected_bundle_group": 1,
                "final_items": [{"event_id": self.ev1_id, "tariff_id": self.t21_id, "ai_rationale": "Неверный тариф"}],
                "final_pitch_text": "Текст КП",
            },
        )
        self.assertEqual(bad_resp.status_code, 400)
        self.assertIn("не принадлежит", bad_resp.json()["detail"])

        # Валидная публикация черновика (ev1 с t11 + ev2 с t21)
        ok_resp = await self.client.put(
            f"/api/manager/selections/{self.sel_draft_id}/publish",
            headers=self.auth_headers,
            json={
                "selected_bundle_group": 1,
                "final_items": [
                    {"event_id": self.ev1_id, "tariff_id": self.t11_id, "ai_rationale": "Спикер КРТ"},
                    {"event_id": self.ev2_id, "tariff_id": self.t21_id, "ai_rationale": "Делегат СПб"},
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

    async def test_05_public_showcase_idor_reactions_and_manager_reply(self):
        """
        Проверка D-10 на реальной БД:
        - Загрузка витрины по magic_token;
        - Защита от IDOR: реакция на элемент из другой подборки отклоняется с 404;
        - Реакция на свой элемент сохраняется и отправляет уведомление менеджеру;
        - Эскалация вопроса клиента, ответ менеджера через /reply и отображение chat_messages в витрине.
        """
        token = str(self.token_published)

        show_resp = await self.client.get(f"/api/public/s/{token}")
        self.assertEqual(show_resp.status_code, 200)
        show_data = show_resp.json()
        self.assertEqual(show_data["company_name"], "ГК «Пионер»")
        self.assertEqual(show_data["total_events_count"], 2)

        # Попытка IDOR: item_draft_id принадлежит другой подборке
        idor_resp = await self.client.post(
            f"/api/public/s/{token}/items/{self.item_draft_id}/react",
            json={"reaction": "rejected", "comment": "Попытка изменить чужую подборку"},
        )
        self.assertEqual(idor_resp.status_code, 404)

        # Легитимная реакция на элемент своей витрины
        react_resp = await self.client.post(
            f"/api/public/s/{token}/items/{self.item_pub_id}/react",
            json={"reaction": "interested", "comment": "Отлично <бронируем> & ждем договор"},
        )
        self.assertEqual(react_resp.status_code, 200)
        self.assertEqual(react_resp.json()["new_reaction"], "interested")
        self.assertTrue(react_resp.json()["manager_notified"])

        # Запрос RAG к событию, не входящему в витрину (event_id=999999) -> 404
        bad_ask = await self.client.post(
            f"/api/public/s/{token}/events/999999/ask",
            json={"question_text": "Что входит в рекомендованный тариф?"},
        )
        self.assertEqual(bad_ask.status_code, 404)

        # Эскалация вопроса клиента менеджеру и ответ менеджера через /reply
        esc_resp = await self.client.post(
            f"/api/public/s/{token}/events/{self.ev1_id}/escalate-question",
            json={"question_text": "Можно ли согласовать индивидуальный слот в 11:00?"},
        )
        self.assertEqual(esc_resp.status_code, 200)
        self.assertTrue(esc_resp.json()["success"])

        act_resp = await self.client.get(
            f"/api/manager/selections/{self.sel_pub_id}/activity",
            headers=self.auth_headers,
        )
        self.assertEqual(act_resp.status_code, 200)
        pending_qs = act_resp.json()["pending_questions"]
        self.assertGreaterEqual(len(pending_qs), 1)
        question_msg_id = pending_qs[-1]["message_id"]

        reply_resp = await self.client.post(
            f"/api/manager/selections/{self.sel_pub_id}/reply",
            headers=self.auth_headers,
            json={
                "message_id": question_msg_id,
                "reply_text": "Да, оргкомитет подтвердил слот в 11:00 для вашего спикера.",
            },
        )
        self.assertEqual(reply_resp.status_code, 200)
        self.assertTrue(reply_resp.json()["success"])

        # Проверяем, что в публичной витрине появились chat_messages (и вопрос клиента, и ответ менеджера)
        show_after = await self.client.get(f"/api/public/s/{token}")
        self.assertEqual(show_after.status_code, 200)
        ev1_card = next(it for it in show_after.json()["items"] if it["event_id"] == self.ev1_id)
        roles_in_chat = [m["sender_role"] for m in ev1_card["chat_messages"]]
        self.assertIn("client", roles_in_chat)
        self.assertIn("manager", roles_in_chat)


if __name__ == "__main__":
    unittest.main()
