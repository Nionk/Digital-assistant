import datetime
import sys
import unittest
from pathlib import Path
from uuid import uuid4

import httpx
from sqlalchemy import delete, select

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.database import async_session_maker, engine
from app.core.security import create_access_token, hash_password
from app.main import app
from app.models.models import (
    ChatMessage,
    Client,
    Event,
    EventTariff,
    Selection,
    SelectionItem,
    User,
)
from app.services.telegram import StubTelegramTransport, set_telegram_transport
from tests.test_d08_d09_d10 import is_postgres_online


@unittest.skipUnless(is_postgres_online(), "Требуется запущенный контейнер PostgreSQL")
class TestBlock2ContractsSuite(unittest.IsolatedAsyncioTestCase):
    """
    Интеграционные тесты Блока 2 на реальном PostgreSQL:
    1. CRUD и мягкая архивация/восстановление клиентов (Client.is_active).
    2. IDOR-изоляция между двумя менеджерами (HTTP 404).
    3. Серверное восстановление GET /api/manager/clients/{id}/workspace
       (без подборки, с draft/published, с архивированным событием и измененными/удаленными тарифами).
    4. Строгая привязка reply_to_message_id, валидация sender_role='client',
       resolved_questions в /activity и manager_email / reply_to_message_id в публичной витрине.
    """

    async def asyncSetUp(self) -> None:
        self.stub_telegram = StubTelegramTransport()
        set_telegram_transport(self.stub_telegram)

        self.created_user_ids: list[int] = []
        self.created_client_ids: list[int] = []
        self.created_event_ids: list[int] = []
        self.created_selection_ids: list[int] = []

        today = datetime.date.today()

        async with async_session_maker() as s:
            mgr_a = await s.get(User, 1)
            if mgr_a is None:
                mgr_a = User(
                    email=f"mgr_a_{uuid4().hex[:8]}@skart.ru",
                    password_hash=hash_password("secret_a"),
                    full_name="Менеджер А",
                )
                s.add(mgr_a)
                await s.flush()
                self.created_user_ids.append(mgr_a.id)

            mgr_b = User(
                email=f"mgr_b_{uuid4().hex[:8]}@skart.ru",
                password_hash=hash_password("secret_b"),
                full_name="Менеджер Б",
            )
            s.add(mgr_b)
            await s.flush()
            self.created_user_ids.append(mgr_b.id)

            self.mgr_a_id = mgr_a.id
            self.mgr_a_email = mgr_a.email
            self.mgr_b_id = mgr_b.id
            self.headers_a = {
                "Authorization": f"Bearer {create_access_token({'sub': str(self.mgr_a_id)})}"
            }
            self.headers_b = {
                "Authorization": f"Bearer {create_access_token({'sub': str(self.mgr_b_id)})}"
            }

            ev_active = Event(
                canonical_title="Тест Блок 2: Активный форум",
                normalized_title="тест блок 2: активный форум",
                event_format="forum",
                city="Москва",
                is_online=False,
                venue="Центр международной торговли",
                start_date=today + datetime.timedelta(days=15),
                end_date=today + datetime.timedelta(days=16),
                summary="Активный форум для проверки серверного восстановления workspace.",
                themes=["КРТ", "девелопмент"],
                data_status="ready",
                is_active=True,
            )
            ev_archived = Event(
                canonical_title="Тест Блок 2: Архивированный конгресс",
                normalized_title="тест блок 2: архивированный конгресс",
                event_format="conference",
                city="Санкт-Петербург",
                is_online=False,
                venue="Экспофорум",
                start_date=today + datetime.timedelta(days=25),
                end_date=today + datetime.timedelta(days=26),
                summary="Архивированное событие, оставшееся в опубликованной подборке.",
                themes=["урбанистика"],
                data_status="archived",
                is_active=False,
            )
            ev_no_tariffs = Event(
                canonical_title="Тест Блок 2: Событие без тарифов",
                normalized_title="тест блок 2: событие без тарифов",
                event_format="roundtable",
                city="Казань",
                is_online=False,
                start_date=today + datetime.timedelta(days=35),
                end_date=today + datetime.timedelta(days=35),
                summary="Событие, у которого удалены тарифы после публикации.",
                themes=["ИЖС"],
                data_status="ready",
                is_active=True,
            )
            s.add_all([ev_active, ev_archived, ev_no_tariffs])
            await s.flush()
            self.ev_active_id = ev_active.id
            self.ev_archived_id = ev_archived.id
            self.ev_no_tariffs_id = ev_no_tariffs.id
            self.created_event_ids.extend([ev_active.id, ev_archived.id, ev_no_tariffs.id])

            tar_spk = EventTariff(
                event_id=ev_active.id,
                tariff_name="Пакет Спикер",
                participation_role="speaker",
                base_price=150000.0,
                early_bird_price=120000.0,
                early_bird_deadline=today + datetime.timedelta(days=5),
                included_benefits="Выступление 20 мин.",
            )
            tar_del = EventTariff(
                event_id=ev_active.id,
                tariff_name="Делегат",
                participation_role="delegate",
                base_price=50000.0,
                early_bird_price=None,
                early_bird_deadline=None,
                included_benefits="Вход в залы.",
            )
            tar_arch = EventTariff(
                event_id=ev_archived.id,
                tariff_name="Архивный делегат",
                participation_role="delegate",
                base_price=40000.0,
                early_bird_price=None,
                early_bird_deadline=None,
                included_benefits="Доступ на площадку.",
            )
            s.add_all([tar_spk, tar_del, tar_arch])
            await s.commit()
            self.tar_spk_id = tar_spk.id
            self.tar_del_id = tar_del.id
            self.tar_arch_id = tar_arch.id

        self.transport = httpx.ASGITransport(app=app)
        self.client = httpx.AsyncClient(
            transport=self.transport, base_url="http://testserver", timeout=30.0
        )

    async def asyncTearDown(self) -> None:
        set_telegram_transport(None)
        await self.client.aclose()

        async with async_session_maker() as s:
            if self.created_selection_ids:
                await s.execute(
                    delete(ChatMessage).where(ChatMessage.selection_id.in_(self.created_selection_ids))
                )
                await s.execute(
                    delete(SelectionItem).where(
                        SelectionItem.selection_id.in_(self.created_selection_ids)
                    )
                )
                await s.execute(
                    delete(Selection).where(Selection.id.in_(self.created_selection_ids))
                )
            if self.created_client_ids:
                # Удаляем также любые selection/chat, созданные через API для этих клиентов
                sel_res = await s.execute(
                    select(Selection.id).where(Selection.client_id.in_(self.created_client_ids))
                )
                extra_sel_ids = list(sel_res.scalars().all())
                if extra_sel_ids:
                    await s.execute(
                        delete(ChatMessage).where(ChatMessage.selection_id.in_(extra_sel_ids))
                    )
                    await s.execute(
                        delete(SelectionItem).where(SelectionItem.selection_id.in_(extra_sel_ids))
                    )
                    await s.execute(delete(Selection).where(Selection.id.in_(extra_sel_ids)))
                await s.execute(delete(Client).where(Client.id.in_(self.created_client_ids)))
            if self.created_event_ids:
                await s.execute(
                    delete(EventTariff).where(EventTariff.event_id.in_(self.created_event_ids))
                )
                await s.execute(delete(Event).where(Event.id.in_(self.created_event_ids)))
            if self.created_user_ids:
                await s.execute(delete(User).where(User.id.in_(self.created_user_ids)))
            await s.commit()

        await engine.dispose()

    async def test_01_client_crud_soft_archive_and_idor_isolation(self) -> None:
        """Создание, валидация, редактирование, мягкая архивация/восстановление и IDOR-изоляция (404)."""
        # 1. Пустое название -> 422
        bad_create = await self.client.post(
            "/api/manager/clients",
            headers=self.headers_a,
            json={"company_name": "   ", "contact_person": "Тест"},
        )
        self.assertEqual(bad_create.status_code, 422)

        # 2. Валидное создание -> 201
        create_res = await self.client.post(
            "/api/manager/clients",
            headers=self.headers_a,
            json={
                "company_name": "Аквилон-Тест",
                "contact_person": "Ольга Петрова",
                "raw_manager_notes": "Первичный звонок",
            },
        )
        self.assertEqual(create_res.status_code, 201, create_res.text)
        created = create_res.json()
        cid = created["id"]
        self.created_client_ids.append(cid)
        self.assertEqual(created["company_name"], "Аквилон-Тест")
        self.assertEqual(created["contact_person"], "Ольга Петрова")
        self.assertTrue(created["is_active"])
        self.assertIsNone(created["latest_selection_id"])

        # 3. IDOR: чужой менеджер B получает 404 на PATCH, /workspace и /match
        idor_patch = await self.client.patch(
            f"/api/manager/clients/{cid}",
            headers=self.headers_b,
            json={"company_name": "Взломано"},
        )
        self.assertEqual(idor_patch.status_code, 404)

        idor_ws = await self.client.get(
            f"/api/manager/clients/{cid}/workspace",
            headers=self.headers_b,
        )
        self.assertEqual(idor_ws.status_code, 404)

        idor_match = await self.client.post(
            f"/api/manager/clients/{cid}/match",
            headers=self.headers_b,
            json={"raw_manager_notes": "Попытка запуска подбора чужому клиенту"},
        )
        self.assertEqual(idor_match.status_code, 404)

        # 4. Редактирование своим менеджером + защита от пустого company_name
        bad_patch = await self.client.patch(
            f"/api/manager/clients/{cid}",
            headers=self.headers_a,
            json={"company_name": "  "},
        )
        self.assertEqual(bad_patch.status_code, 422)

        patch_res = await self.client.patch(
            f"/api/manager/clients/{cid}",
            headers=self.headers_a,
            json={
                "company_name": "ГК «Аквилон-Тест»",
                "contact_person": "",
                "raw_manager_notes": "Обновленный бриф после созвона",
            },
        )
        self.assertEqual(patch_res.status_code, 200, patch_res.text)
        patched = patch_res.json()
        self.assertEqual(patched["company_name"], "ГК «Аквилон-Тест»")
        self.assertIsNone(patched["contact_person"])
        self.assertEqual(patched["raw_manager_notes"], "Обновленный бриф после созвона")

        # 5. Создаем опубликованную подборку, затем архивируем клиента и проверяем сохранность витрины
        pub_token = uuid4()
        async with async_session_maker() as s:
            sel = Selection(
                client_id=cid,
                magic_token=pub_token,
                status="published",
                generated_pitch_text="Письмо архивного теста",
                total_budget_limit=120000.0,
            )
            s.add(sel)
            await s.flush()
            self.created_selection_ids.append(sel.id)
            s.add(
                SelectionItem(
                    selection_id=sel.id,
                    event_id=self.ev_active_id,
                    recommended_tariff_id=self.tar_spk_id,
                    bundle_group=1,
                    ai_rationale="Спикерство по КРТ",
                )
            )
            await s.commit()

        arch_res = await self.client.patch(
            f"/api/manager/clients/{cid}",
            headers=self.headers_a,
            json={"is_active": False},
        )
        self.assertEqual(arch_res.status_code, 200)
        self.assertFalse(arch_res.json()["is_active"])

        # В дефолтном дашборде архивный клиент скрыт, с ?include_archived=true — виден
        dash_default = await self.client.get("/api/manager/clients", headers=self.headers_a)
        self.assertEqual(dash_default.status_code, 200)
        self.assertNotIn(cid, [c["id"] for c in dash_default.json()["clients"]])

        dash_with_arch = await self.client.get(
            "/api/manager/clients?include_archived=true",
            headers=self.headers_a,
        )
        self.assertEqual(dash_with_arch.status_code, 200)
        self.assertIn(cid, [c["id"] for c in dash_with_arch.json()["clients"]])

        # Опубликованная витрина продолжает работать после архивации клиента
        showcase_res = await self.client.get(f"/api/public/s/{pub_token}")
        self.assertEqual(showcase_res.status_code, 200)
        self.assertEqual(showcase_res.json()["company_name"], "ГК «Аквилон-Тест»")

        # 6. Восстановление из архива
        restore_res = await self.client.patch(
            f"/api/manager/clients/{cid}",
            headers=self.headers_a,
            json={"is_active": True},
        )
        self.assertEqual(restore_res.status_code, 200)
        self.assertTrue(restore_res.json()["is_active"])

        dash_after_restore = await self.client.get("/api/manager/clients", headers=self.headers_a)
        self.assertIn(cid, [c["id"] for c in dash_after_restore.json()["clients"]])

    async def test_02_workspace_hydration_and_edge_cases(self) -> None:
        """Проверка /workspace для клиента без подборки, с подборкой и со сбитыми тарифами/архивом."""
        # 1. Новый клиент без подборки и с пустым профилем -> selection=None, extracted_profile=None
        c_empty_res = await self.client.post(
            "/api/manager/clients",
            headers=self.headers_a,
            json={"company_name": "Клиент Без Подборки", "raw_manager_notes": "Заметка"},
        )
        self.assertEqual(c_empty_res.status_code, 201)
        c_empty_id = c_empty_res.json()["id"]
        self.created_client_ids.append(c_empty_id)

        ws_empty = await self.client.get(
            f"/api/manager/clients/{c_empty_id}/workspace",
            headers=self.headers_a,
        )
        self.assertEqual(ws_empty.status_code, 200, ws_empty.text)
        ws_empty_data = ws_empty.json()
        self.assertIsNone(ws_empty_data["extracted_profile"])
        self.assertIsNone(ws_empty_data["selection"])

        # 2. Клиент с валидным профилем и опубликованной подборкой, содержащей:
        #    - активное событие с удаленным recommended_tariff_id=None (проверка фолбэка)
        #    - архивированное событие (is_active=False, data_status="archived")
        #    - событие без тарифов в БД вообще
        pub_token = uuid4()
        async with async_session_maker() as s:
            c_full = Client(
                manager_id=self.mgr_a_id,
                company_name="Клиент С Историей",
                contact_person="Иван Иванов",
                raw_manager_notes="Нужен КРТ и спикерство в Москве",
                extracted_profile={
                    "cities": ["Москва"],
                    "include_online": True,
                    "total_budget_max": 250000.0,
                    "target_events_count": 3,
                    "preferred_formats": ["forum"],
                    "required_roles": ["speaker", "delegate"],
                    "min_speaker_events": 1,
                    "themes_keywords": ["КРТ"],
                    "semantic_search_query": "Форумы КРТ Москва",
                },
            )
            s.add(c_full)
            await s.flush()
            c_full_id = c_full.id
            self.created_client_ids.append(c_full_id)

            sel = Selection(
                client_id=c_full_id,
                magic_token=pub_token,
                status="published",
                generated_pitch_text="Согласованное КП для восстановления",
                total_budget_limit=160000.0,
            )
            s.add(sel)
            await s.flush()
            self.created_selection_ids.append(sel.id)

            s.add_all(
                [
                    SelectionItem(
                        selection_id=sel.id,
                        event_id=self.ev_active_id,
                        recommended_tariff_id=None,  # Сброшен при обновлении тарифов
                        bundle_group=1,
                        ai_rationale="Рекомендуется выступление спикером по КРТ",
                    ),
                    SelectionItem(
                        selection_id=sel.id,
                        event_id=self.ev_archived_id,
                        recommended_tariff_id=self.tar_arch_id,
                        bundle_group=1,
                        ai_rationale="Архивное событие в опубликованном пакете",
                    ),
                    SelectionItem(
                        selection_id=sel.id,
                        event_id=self.ev_no_tariffs_id,
                        recommended_tariff_id=None,
                        bundle_group=1,
                        ai_rationale="Событие без тарифов в таблице event_tariffs",
                    ),
                ]
            )
            await s.commit()

        ws_full = await self.client.get(
            f"/api/manager/clients/{c_full_id}/workspace",
            headers=self.headers_a,
        )
        self.assertEqual(ws_full.status_code, 200, ws_full.text)
        data = ws_full.json()
        self.assertIsNotNone(data["extracted_profile"])
        self.assertEqual(data["extracted_profile"]["cities"], ["Москва"])
        self.assertIsNotNone(data["selection"])
        sel_data = data["selection"]
        self.assertEqual(sel_data["status"], "published")
        self.assertEqual(sel_data["magic_token"], str(pub_token))
        self.assertEqual(sel_data["generated_pitch_text"], "Согласованное КП для восстановления")
        self.assertEqual(len(sel_data["bundle_variants"]), 1)

        v1 = sel_data["bundle_variants"][0]
        self.assertEqual(len(v1["items"]), 3)
        by_ev = {it["event_id"]: it for it in v1["items"]}

        # Фолбэк по "спикер" в ai_rationale должен выбрать Пакет Спикер (120 000 ₽)
        self.assertEqual(by_ev[self.ev_active_id]["recommended_tariff"]["tariff_id"], self.tar_spk_id)
        self.assertEqual(len(by_ev[self.ev_active_id]["available_tariffs"]), 2)

        # Архивированное событие не вызывает 500 и сохраняет data_status='archived'
        self.assertEqual(by_ev[self.ev_archived_id]["data_status"], "archived")
        self.assertEqual(by_ev[self.ev_archived_id]["recommended_tariff"]["tariff_id"], self.tar_arch_id)

        # Событие без тарифов возвращает безопасный фолбэк-тариф (tariff_id=0)
        self.assertEqual(by_ev[self.ev_no_tariffs_id]["recommended_tariff"]["tariff_id"], 0)
        self.assertEqual(len(by_ev[self.ev_no_tariffs_id]["available_tariffs"]), 1)

        # Суммы: 120 000 (EB) + 40 000 + 0 = 160 000, экономия 30 000
        self.assertEqual(v1["total_actual_price"], 160000.0)
        self.assertEqual(v1["total_base_price"], 190000.0)
        self.assertEqual(v1["total_savings"], 30000.0)

    async def test_03_reply_to_message_id_resolved_questions_and_showcase_email(self) -> None:
        """Проверка строгой привязки reply_to_message_id, resolved_questions, IDOR и manager_email."""
        pub_token = uuid4()
        now = datetime.datetime(2026, 11, 16, 10, 0, tzinfo=datetime.UTC)

        async with async_session_maker() as s:
            cli = Client(
                manager_id=self.mgr_a_id,
                company_name="Клиент Чат-История",
                raw_manager_notes="Тест чата",
            )
            s.add(cli)
            await s.flush()
            self.created_client_ids.append(cli.id)

            sel = Selection(
                client_id=cli.id,
                magic_token=pub_token,
                status="published",
                generated_pitch_text="Письмо",
                total_budget_limit=150000.0,
            )
            s.add(sel)
            await s.flush()
            self.created_selection_ids.append(sel.id)
            sel_id = sel.id

            s.add(
                SelectionItem(
                    selection_id=sel_id,
                    event_id=self.ev_active_id,
                    recommended_tariff_id=self.tar_spk_id,
                    bundle_group=1,
                    ai_rationale="Спикерство",
                )
            )

            # Два открытых вопроса по одному и тому же событию + ответ ИИ + legacy ответ менеджера
            q_legacy = ChatMessage(
                selection_id=sel_id,
                event_id=self.ev_active_id,
                sender_role="client",
                message_text="Старый вопрос до миграции",
                needs_manager_attention=False,
                created_at=now,
            )
            m_legacy = ChatMessage(
                selection_id=sel_id,
                event_id=self.ev_active_id,
                reply_to_message_id=None,
                sender_role="manager",
                message_text="Старый ответ без reply_to_message_id",
                needs_manager_attention=False,
                created_at=now + datetime.timedelta(minutes=1),
            )
            q1 = ChatMessage(
                selection_id=sel_id,
                event_id=self.ev_active_id,
                sender_role="client",
                message_text="Первый вопрос: можно ли заменить спикера за день до форума?",
                needs_manager_attention=True,
                created_at=now + datetime.timedelta(minutes=2),
            )
            ai_1 = ChatMessage(
                selection_id=sel_id,
                event_id=self.ev_active_id,
                sender_role="ai_assistant",
                message_text="Точных данных по замене спикера нет в регламенте.",
                needs_manager_attention=False,
                created_at=now + datetime.timedelta(minutes=2, seconds=1),
            )
            q2 = ChatMessage(
                selection_id=sel_id,
                event_id=self.ev_active_id,
                sender_role="client",
                message_text="Второй вопрос: предоставляется ли парковка?",
                needs_manager_attention=True,
                created_at=now + datetime.timedelta(minutes=3),
            )
            s.add_all([q_legacy, m_legacy, q1, ai_1, q2])
            await s.commit()
            q1_id = q1.id
            ai_1_id = ai_1.id
            q2_id = q2.id

        # 1. IDOR: чужой менеджер B получает 404 на /activity и /reply
        idor_act = await self.client.get(
            f"/api/manager/selections/{sel_id}/activity",
            headers=self.headers_b,
        )
        self.assertEqual(idor_act.status_code, 404)

        idor_reply = await self.client.post(
            f"/api/manager/selections/{sel_id}/reply",
            headers=self.headers_b,
            json={"message_id": q1_id, "reply_text": "Попытка ответа чужим менеджером"},
        )
        self.assertEqual(idor_reply.status_code, 404)

        # 2. Попытка ответить на сообщение ai_assistant -> 400
        bad_role_reply = await self.client.post(
            f"/api/manager/selections/{sel_id}/reply",
            headers=self.headers_a,
            json={"message_id": ai_1_id, "reply_text": "Ответ на ИИ"},
        )
        self.assertEqual(bad_role_reply.status_code, 400)

        # 3. Менеджер отвечает именно на q1 (при том что q2 новее!)
        ok_reply = await self.client.post(
            f"/api/manager/selections/{sel_id}/reply",
            headers=self.headers_a,
            json={
                "message_id": q1_id,
                "reply_text": "Да, замена спикера возможна за 24 часа по заявке куратору.",
            },
        )
        self.assertEqual(ok_reply.status_code, 200, ok_reply.text)
        reply_msg_id = ok_reply.json()["reply_message_id"]

        # Проверяем в БД, что reply_to_message_id == q1_id
        async with async_session_maker() as s:
            saved_reply = await s.get(ChatMessage, reply_msg_id)
            self.assertIsNotNone(saved_reply)
            self.assertEqual(saved_reply.reply_to_message_id, q1_id)

        # 4. Проверяем /activity: в pending остался только q2, в resolved — q1 и legacy
        act_res = await self.client.get(
            f"/api/manager/selections/{sel_id}/activity",
            headers=self.headers_a,
        )
        self.assertEqual(act_res.status_code, 200, act_res.text)
        act_data = act_res.json()
        self.assertEqual([q["message_id"] for q in act_data["pending_questions"]], [q2_id])

        resolved_by_id = {r["message_id"]: r for r in act_data["resolved_questions"]}
        self.assertIn(q1_id, resolved_by_id)
        self.assertEqual(
            resolved_by_id[q1_id]["question_text"],
            "Первый вопрос: можно ли заменить спикера за день до форума?",
        )
        self.assertEqual(
            resolved_by_id[q1_id]["latest_reply_text"],
            "Да, замена спикера возможна за 24 часа по заявке куратору.",
        )
        self.assertEqual(len(resolved_by_id[q1_id]["replies"]), 1)

        # 5. Проверяем публичную витрину: manager_email и reply_to_message_id в chat_messages
        show_res = await self.client.get(f"/api/public/s/{pub_token}")
        self.assertEqual(show_res.status_code, 200, show_res.text)
        show_data = show_res.json()
        self.assertEqual(show_data["manager_email"], self.mgr_a_email)

        chat_msgs = show_data["items"][0]["chat_messages"]
        msg_by_id = {m["id"]: m for m in chat_msgs}
        self.assertEqual(msg_by_id[reply_msg_id]["reply_to_message_id"], q1_id)
        self.assertIsNone(msg_by_id[q1_id]["reply_to_message_id"])


if __name__ == "__main__":
    unittest.main()
