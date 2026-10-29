import asyncio
import sys
from pathlib import Path
import httpx

# Настройка путей для запуска из корня
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

BASE_URL = "http://backend:8000" # Обращаемся к бэкенду внутри Docker-сети

async def main():
    print("=== Тест D-08: Сквозной сценарий (Match -> Publish) ===\n")
    
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=60.0) as client:
        # --- ШАГ 1: MATCH ---
        print("1. Отправляем заметку менеджера на эндпоинт /match...")
        match_payload = {
            "raw_manager_notes": "Созвонились с Пионером. Нужны 3 мероприятия в Москве или СПб на ноябрь-декабрь по КРТ. Бюджет 400 тысяч. Хотя бы на одном хотим быть спикером.",
            "override_profile": None
        }
        
        resp = await client.post("/api/manager/clients/1/match", json=match_payload)
        if resp.status_code != 200:
            print(f"[FAIL] Ошибка Match: {resp.status_code} - {resp.text}")
            return
            
        match_data = resp.json()
        selection_id = match_data["selection_id"]
        variants = match_data["bundle_variants"]
        
        print(f"[OK] Подборка создана! ID: {selection_id}")
        print(f"Получено вариантов пакетов: {len(variants)}")
        for v in variants:
            print(f"  - {v['bundle_title']}: {v['total_actual_price']} ₽ (экономия: {v['total_savings']} ₽)")
        print(f"Черновик письма (первые 100 символов): {match_data['generated_pitch_text'][:100]}...\n")

        # --- ШАГ 2: PUBLISH ---
        print("2. Публикуем Вариант №1 (Утверждаем пакет)...")
        
        # Формируем финальный список элементов для публикации
        chosen_variant = variants[0]
        final_items = [
            {
                "event_id": item["event_id"],
                "tariff_id": item["recommended_tariff"]["tariff_id"],
                "ai_rationale": item["ai_rationale"]
            }
            for item in chosen_variant["items"]
        ]

        publish_payload = {
            "selected_bundle_group": 1,
            "final_items": final_items,
            "final_pitch_text": match_data["generated_pitch_text"] + "\n\n[Отредактировано менеджером]"
        }

        resp_pub = await client.put(f"/api/manager/selections/{selection_id}/publish", json=publish_payload)
        if resp_pub.status_code != 200:
            print(f"[FAIL] Ошибка Publish: {resp_pub.status_code} - {resp_pub.text}")
            return

        pub_data = resp_pub.json()
        print(f"[OK] Подборка опубликована!")
        print(f"  - Magic Link: {pub_data['public_showcase_url']}")
        print(f"  - Итоговая сумма: {pub_data['total_package_price']} ₽")
        print(f"  - Суммарная экономия: {pub_data['total_package_savings']} ₽")
        
        # Проверки
        assert pub_data["status"] == "published"
        assert pub_data["total_package_price"] > 0
        assert pub_data["magic_token"] is not None
        
        print("\n✅ ВСЕ ТЕСТЫ D-08 ПРОЙДЕНЫ УСПЕШНО!")

if __name__ == "__main__":
    asyncio.run(main())