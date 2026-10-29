import asyncio
import sys
from pathlib import Path
import httpx

# Настройка путей и UTF-8 консоли Windows
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.main import app
from app.core.database import engine, get_async_session
from tests.test_d08_d09_d10 import InMemoryAsyncSession, is_postgres_online


async def main() -> None:
    print("=== Тест D-08: Бизнес-эндпоинты менеджера (/clients, /match, /publish) ===\n")

    pg_up = is_postgres_online()
    fake_db = InMemoryAsyncSession()
    if not pg_up:
        print("[INFO] PostgreSQL (порт 5432) остановлен — используем InMemoryAsyncSession для проверки бизнес-логики.\n")

        async def _override():
            yield fake_db

        app.dependency_overrides[get_async_session] = _override

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver", timeout=60.0) as client:
        # --- ШАГ 0: GET /api/manager/clients ---
        print("0. Проверяем дашборд менеджера (GET /api/manager/clients)...")
        resp_clients = await client.get("/api/manager/clients")
        assert resp_clients.status_code == 200, f"Ошибка /clients: {resp_clients.status_code} - {resp_clients.text}"
        dash_data = resp_clients.json()
        print(
            f"[OK] Клиентов: {len(dash_data['clients'])}, "
            f"горящих дедлайнов Early Bird: {len(dash_data['burning_deadlines'])}\n"
        )
        assert len(dash_data["clients"]) >= 1
        assert len(dash_data["burning_deadlines"]) >= 1

        # --- ШАГ 1: POST /api/manager/clients/1/match ---
        print("1. Отправляем заметку менеджера на эндпоинт POST /api/manager/clients/1/match...")
        match_payload = {
            "raw_manager_notes": (
                "Созвонились с Пионером. Нужны 3 мероприятия в Москве или СПб на ноябрь-декабрь по КРТ. "
                "Бюджет 400 тысяч. Хотя бы на одном хотим быть спикером."
            ),
            "override_profile": None,
        }

        resp = await client.post("/api/manager/clients/1/match", json=match_payload)
        if resp.status_code != 200:
            print(f"[FAIL] Ошибка Match: {resp.status_code} - {resp.text}")
            sys.exit(1)

        match_data = resp.json()
        selection_id = match_data["selection_id"] if pg_up else 1
        variants = match_data["bundle_variants"]

        print(f"[OK] Черновик подборки создан! selection_id={selection_id}")
        print(f"Получено вариантов пакетов: {len(variants)}")
        for v in variants:
            print(f"  - {v['bundle_title']}: {v['total_actual_price']} руб. (экономия: {v['total_savings']} руб.)")
        print(f"Черновик письма (первые 100 символов): {match_data['generated_pitch_text'][:100]}...\n")
        assert len(variants) >= 1

        # --- ШАГ 2: ПРОВЕРКА ЗАЩИТЫ ОТ НЕВАЛИДНОЙ ПУБЛИКАЦИИ ---
        print("2. Проверяем защиту от пустого списка и чужого тарифа при публикации...")
        empty_pub = await client.put(
            f"/api/manager/selections/{selection_id}/publish",
            json={"selected_bundle_group": 1, "final_items": [], "final_pitch_text": "Тест"},
        )
        assert empty_pub.status_code == 400
        print("[OK] Пустой список final_items корректно отклонен (400 Bad Request).\n")

        # --- ШАГ 3: PUT /api/manager/selections/{selection_id}/publish ---
        print("3. Публикуем Вариант №1 (Утверждаем пакет)...")
        if pg_up:
            chosen_variant = variants[0]
            final_items = [
                {
                    "event_id": item["event_id"],
                    "tariff_id": item["recommended_tariff"]["tariff_id"],
                    "ai_rationale": item["ai_rationale"],
                }
                for item in chosen_variant["items"]
            ]
        else:
            final_items = [
                {"event_id": 1, "tariff_id": 11, "ai_rationale": "Спикер КРТ"},
                {"event_id": 2, "tariff_id": 21, "ai_rationale": "Делегат СПб"},
            ]

        publish_payload = {
            "selected_bundle_group": 1,
            "final_items": final_items,
            "final_pitch_text": match_data["generated_pitch_text"] + "\n\n[Согласовано руководителем направления]",
        }

        resp_pub = await client.put(f"/api/manager/selections/{selection_id}/publish", json=publish_payload)
        if resp_pub.status_code != 200:
            print(f"[FAIL] Ошибка Publish: {resp_pub.status_code} - {resp_pub.text}")
            sys.exit(1)

        pub_data = resp_pub.json()
        print(f"[OK] Подборка ID={selection_id} успешно опубликована!")
        print(f"  - Magic Link: {pub_data['public_showcase_url']}")
        print(f"  - Итоговая сумма: {pub_data['total_package_price']} руб.")
        print(f"  - Суммарная экономия: {pub_data['total_package_savings']} руб.")

        assert pub_data["status"] == "published"
        assert pub_data["total_package_price"] > 0
        assert pub_data["magic_token"] is not None

        print("\n[SUCCESS] ВСЕ ТЕСТЫ D-08 ПРОЙДЕНЫ УСПЕШНО!")

    app.dependency_overrides.pop(get_async_session, None)
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
