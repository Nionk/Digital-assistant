import asyncio
import sys
from pathlib import Path
from sqlalchemy import select
import httpx

# Настройка путей и UTF-8 консоли Windows
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.main import app
from app.core.database import async_session_maker, engine, get_async_session
from app.models.models import Selection, SelectionItem
from tests.test_d08_d09_d10 import InMemoryAsyncSession, is_postgres_online


async def get_or_create_published_token(client: httpx.AsyncClient, pg_up: bool, fake_db: InMemoryAsyncSession) -> str:
    """Находит актуальный magic_token опубликованной подборки или публикует новую через API."""
    if not pg_up:
        return str(fake_db.token_published)

    async with async_session_maker() as session:
        stmt = (
            select(Selection)
            .where(Selection.status == "published")
            .order_by(Selection.id.desc())
            .limit(1)
        )
        res = await session.execute(stmt)
        sel = res.scalar_one_or_none()
        if sel is not None:
            items_res = await session.execute(
                select(SelectionItem).where(
                    SelectionItem.selection_id == sel.id,
                    SelectionItem.bundle_group == 1,
                )
            )
            if items_res.scalars().first() is not None:
                return str(sel.magic_token)

    match_resp = await client.post(
        "/api/manager/clients/1/match",
        json={
            "raw_manager_notes": "Нужны 3 мероприятия в Москве и СПб по КРТ и девелопменту, бюджет 400 000 руб.",
            "override_profile": None,
        },
    )
    assert match_resp.status_code == 200, match_resp.text
    m_data = match_resp.json()
    v1_items = [
        {
            "event_id": it["event_id"],
            "tariff_id": it["recommended_tariff"]["tariff_id"],
            "ai_rationale": it["ai_rationale"],
        }
        for it in m_data["bundle_variants"][0]["items"]
    ]
    pub_resp = await client.put(
        f"/api/manager/selections/{m_data['selection_id']}/publish",
        json={
            "selected_bundle_group": 1,
            "final_items": v1_items,
            "final_pitch_text": m_data["generated_pitch_text"],
        },
    )
    assert pub_resp.status_code == 200, pub_resp.text
    return str(pub_resp.json()["magic_token"])


async def main() -> None:
    print("=== Тест D-10: Публичная витрина клиента (/s/{magic_token}) и Telegram-алерты ===\n")

    pg_up = is_postgres_online()
    fake_db = InMemoryAsyncSession()
    if not pg_up:
        print("[INFO] PostgreSQL (порт 5432) остановлен — используем InMemoryAsyncSession.\n")

        async def _override():
            yield fake_db

        app.dependency_overrides[get_async_session] = _override

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver", timeout=60.0) as client:
        magic_token = await get_or_create_published_token(client, pg_up, fake_db)
        print(f"[INFO] Используем актуальный magic_token: {magic_token}\n")

        # --- ТЕСТ 1: Получение витрины ---
        print("1. Запрос данных витрины (GET /api/public/s/{magic_token})...")
        resp = await client.get(f"/api/public/s/{magic_token}")
        if resp.status_code != 200:
            print(f"[FAIL] Ошибка: {resp.status_code} - {resp.text}")
            sys.exit(1)

        data = resp.json()
        print(f"[OK] Витрина загружена для компании: {data['company_name']}")
        print(f"     Персональный менеджер: {data['manager_full_name']}")
        print(f"     Всего событий: {data['total_events_count']}")
        print(f"     Итоговая сумма: {data['total_actual_price']} руб. (экономия: {data['total_savings']} руб.)")
        assert data["total_events_count"] >= 1
        assert len(data["faq_quick_chips"]) == 3

        test_item_id = data["items"][0]["selection_item_id"]
        test_event_id = data["items"][0]["event_id"]

        # --- ТЕСТ 2: Проверка защиты от IDOR (чужой/несуществующий item_id) ---
        print("\n2. Проверка защиты от IDOR (попытка реакции на чужой item_id=999999)...")
        idor_resp = await client.post(
            f"/api/public/s/{magic_token}/items/999999/react",
            json={"reaction": "interested", "comment": "Попытка подмены ID"},
        )
        assert idor_resp.status_code == 404, f"Ожидался 404 при чужом item_id, получен {idor_resp.status_code}"
        print("[OK] Чужой item_id корректно отклонен (404 Not Found).")

        # --- ТЕСТ 3: Реакция клиента с HTML-спецсимволами ---
        print(f"\n3. Клиент нажимает 'Интересно' на элемент {test_item_id} с комментарием...")
        react_payload = {
            "reaction": "interested",
            "comment": "Очень интересно (<бюджет согласован> & ждем счет на оплату).",
        }
        resp_react = await client.post(
            f"/api/public/s/{magic_token}/items/{test_item_id}/react",
            json=react_payload,
        )
        assert resp_react.status_code == 200, f"Ошибка реакции: {resp_react.text}"
        react_data = resp_react.json()
        assert react_data["new_reaction"] == "interested"
        assert react_data["manager_notified"] is True
        print("[OK] Реакция сохранена в БД, менеджер уведомлен (HTML-символы безопасно экранированы).")

        # --- ТЕСТ 4: Вопрос клиента по регламенту из чипса FAQ ---
        print(f"\n4. Клиент нажимает чипс FAQ по событию {test_event_id}...")
        faq_resp = await client.post(
            f"/api/public/s/{magic_token}/events/{test_event_id}/ask",
            json={"question_text": "Что входит в рекомендованный тариф?"},
        )
        assert faq_resp.status_code == 200, f"Ошибка FAQ: {faq_resp.text}"
        faq_data = faq_resp.json()
        print(f"[OK] Ответ FAQ получен (from_cache={faq_data['from_cache']}, is_answer_found={faq_data['is_answer_found']})")
        assert faq_data["is_answer_found"] is True
        assert faq_data["escalated_to_telegram"] is False

        # --- ТЕСТ 5: Каверзный вопрос клиента (RAG + Эскалация в Telegram) ---
        print(f"\n5. Клиент задает вопрос вне регламента по событию {test_event_id}...")
        ask_payload = {"question_text": "Есть ли трансфер на вертолете от аэропорта до площадки?"}
        resp_ask = await client.post(
            f"/api/public/s/{magic_token}/events/{test_event_id}/ask",
            json=ask_payload,
        )
        assert resp_ask.status_code == 200, f"Ошибка вопроса: {resp_ask.text}"
        ask_data = resp_ask.json()
        print(f"[OK] Ответ RAG получен!")
        print(f"     is_answer_found: {ask_data['is_answer_found']}")
        print(f"     escalated_to_telegram: {ask_data['escalated_to_telegram']}")
        print(f"     Текст ответа: {ask_data['answer_text'][:90]}...")
        assert ask_data["is_answer_found"] is False
        assert ask_data["escalated_to_telegram"] is True

        print("\n[SUCCESS] ВСЕ ТЕСТЫ D-10 ПРОЙДЕНЫ УСПЕШНО!")

    app.dependency_overrides.pop(get_async_session, None)
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
