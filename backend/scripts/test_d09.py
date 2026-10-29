import asyncio
import sys
from pathlib import Path
from sqlalchemy import select

# Настройка путей для запуска из корня
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.database import async_session_maker
from app.models.models import SelectionItem
from app.services.rag import ask_regulation_question

async def main():
    print("=== Тест D-09: Изолированный RAG и кэширование ===\n")
    
    async with async_session_maker() as session:
        # Найдем реальный event_id из нашей подборки (которую создали в D-08)
        stmt = select(SelectionItem).where(SelectionItem.selection_id == 2).limit(1)
        res = await session.execute(stmt)
        item = res.scalar_one_or_none()
        
        if not item:
            print("[SKIP] Подборка ID=2 не найдена. Сначала запустите test_d08.py")
            return
            
        event_id = item.event_id
        print(f"Тестируем на мероприятии event_id={event_id}\n")

        # --- ТЕСТ 1: Вопрос из кэша FAQ ---
        print("1. Тест кэша (вопрос 'Что входит в рекомендованный тариф?')")
        resp1 = await ask_regulation_question(session, selection_id=2, event_id=event_id, question_text="Что входит в рекомендованный тариф?")
        print(f"   [OK] Ответ из кэша: {resp1.from_cache}")
        print(f"   Текст ответа: {resp1.answer_text[:80]}...\n")
        assert resp1.from_cache is True, "Ошибка: вопрос из чипса должен браться из кэша!"

        # --- ТЕСТ 2: Вопрос, ответ на который есть в регламенте, но его нет в кэше ---
        print("2. Тест Context Stuffing (вопрос про детали мероприятия)")
        # Задаем вопрос, которого точно нет в 3 базовых чипсах
        resp2 = await ask_regulation_question(session, selection_id=2, event_id=event_id, question_text="Где будет проходить мероприятие и есть ли парковка?")
        print(f"   [OK] Ответ из кэша: {resp2.from_cache}")
        print(f"   is_answer_found: {resp2.is_answer_found}")
        print(f"   Текст ответа: {resp2.answer_text[:80]}...")
        print(f"   Цитата: {resp2.source_quote}")
        
        # --- ТЕСТ 3: Провокационный вопрос (проверка на галлюцинации) ---
        print("\n3. Тест Zero-Hallucination (вопрос-провокация)")
        resp3 = await ask_regulation_question(session, selection_id=2, event_id=event_id, question_text="Предоставляете ли вы бесплатный вертолет из аэропорта до отеля?")
        print(f"   [OK] is_answer_found: {resp3.is_answer_found}")
        print(f"   escalated_to_telegram: {resp3.escalated_to_telegram}")
        print(f"   Текст ответа: {resp3.answer_text[:100]}...\n")
        assert resp3.is_answer_found is False, "Ошибка: ИИ выдумал ответ на вопрос про вертолет!"
        assert resp3.escalated_to_telegram is True, "Ошибка: вопрос должен быть эскалирован!"

        print("✅ ВСЕ ТЕСТЫ D-09 ПРОЙДЕНЫ УСПЕШНО!")

if __name__ == "__main__":
    asyncio.run(main())