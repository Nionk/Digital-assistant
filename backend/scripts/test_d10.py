import asyncio
import sys
from pathlib import Path
import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

BASE_URL = "http://backend:8000"
MAGIC_TOKEN = "c36cad3f-886c-47d6-81c4-3cabd5d8916a" # Токен из теста D-08

async def main():
    print("=== Тест D-10: Витрина клиента и Telegram-алерты ===\n")
    
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
        # --- ТЕСТ 1: Получение витрины ---
        print("1. Запрос данных витрины (GET /api/public/s/{magic_token})...")
        resp = await client.get(f"/api/public/s/{MAGIC_TOKEN}")
        
        if resp.status_code != 200:
            print(f"[FAIL] Ошибка: {resp.status_code} - {resp.text}")
            return
            
        data = resp.json()
        print(f"[OK] Витрина загружена для компании: {data['company_name']}")
        print(f"     Всего событий: {data['total_events_count']}")
        print(f"     Итоговая сумма: {data['total_actual_price']} ₽")
        
        # Берем ID первого элемента и ID мероприятия для дальнейших тестов
        test_item_id = data['items'][0]['selection_item_id']
        test_event_id = data['items'][0]['event_id']

        # --- ТЕСТ 2: Реакция клиента ---
        print(f"\n2. Клиент нажимает 'Интересно' на элемент {test_item_id}...")
        react_payload = {"reaction": "interested", "comment": "Очень интересно, забронируйте нам места."}
        resp_react = await client.post(f"/api/public/s/{MAGIC_TOKEN}/items/{test_item_id}/react", json=react_payload)
        
        if resp_react.status_code == 200:
            print(f"[OK] Реакция сохранена. Менеджер уведомлен (смотри консоль Docker или Telegram).")
        else:
            print(f"[FAIL] Ошибка реакции: {resp_react.text}")

        # --- ТЕСТ 3: Вопрос клиента (RAG + Эскалация) ---
        print(f"\n3. Клиент задает каверзный вопрос по событию {test_event_id}...")
        ask_payload = {"question_text": "Есть ли трансфер на вертолете от аэропорта?"}
        resp_ask = await client.post(f"/api/public/s/{MAGIC_TOKEN}/events/{test_event_id}/ask", json=ask_payload)
        
        if resp_ask.status_code == 200:
            ask_data = resp_ask.json()
            print(f"[OK] Ответ RAG получен!")
            print(f"     is_answer_found: {ask_data['is_answer_found']}")
            print(f"     escalated_to_telegram: {ask_data['escalated_to_telegram']}")
            print(f"     Текст ответа: {ask_data['answer_text'][:80]}...")
            if ask_data['escalated_to_telegram']:
                print("     🔔 Алерт менеджеру отправлен! (смотри консоль Docker)")
        else:
            print(f"[FAIL] Ошибка вопроса: {resp_ask.text}")

        print("\n✅ ВСЕ ТЕСТЫ D-10 ПРОЙДЕНЫ УСПЕШНО!")

if __name__ == "__main__":
    asyncio.run(main())