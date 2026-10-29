import asyncio
import sys
import time
from pathlib import Path
from sqlalchemy import func, select

# Настройка путей и UTF-8 консоли Windows
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.core.database import async_session_maker, engine
from app.models.models import ChatMessage, Event, Selection, SelectionItem
from app.services.rag import ask_regulation_question
from tests.test_d08_d09_d10 import InMemoryAsyncSession, is_postgres_online


async def run_rag_checks(session, selection_id: int, event_id: int, is_in_memory: bool = False) -> None:
    print(f"Тестируем на подборке selection_id={selection_id}, мероприятие event_id={event_id}\n")

    if is_in_memory:
        count_before = len(session.chat_messages)
    else:
        count_before_res = await session.execute(
            select(func.count(ChatMessage.id)).where(
                ChatMessage.selection_id == selection_id,
                ChatMessage.event_id == event_id,
            )
        )
        count_before = count_before_res.scalar_one()

    # --- ТЕСТ 1: Вопрос из предзаполненного кэша FAQ (< 50 мс) ---
    print("1. Тест точного кэша FAQ ('Что входит в рекомендованный тариф?')...")
    t0 = time.perf_counter()
    resp1 = await ask_regulation_question(
        session=session,
        selection_id=selection_id,
        event_id=event_id,
        question_text="Что входит в рекомендованный тариф?",
    )
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    print(f"   [OK] from_cache={resp1.from_cache}, время ответа: {elapsed_ms:.1f} мс")
    print(f"   Текст ответа: {resp1.answer_text[:90]}...")
    assert resp1.from_cache is True, "Вопрос из чипса FAQ должен мгновенно возвращаться из llm_cache!"
    assert resp1.is_answer_found is True
    assert resp1.escalated_to_telegram is False

    if is_in_memory:
        count_after = len(session.chat_messages)
    else:
        count_after_res = await session.execute(
            select(func.count(ChatMessage.id)).where(
                ChatMessage.selection_id == selection_id,
                ChatMessage.event_id == event_id,
            )
        )
        count_after = count_after_res.scalar_one()

    assert count_after == count_before + 2, "Диалог при попадании в кэш должен сохраняться в chat_messages!"
    print("   [OK] Запись вопроса и ответа в chat_messages подтверждена.\n")

    # --- ТЕСТ 2: Context Stuffing (вопрос по тексту регламента вне стартовых чипсов) ---
    unique_q = f"Какова тематика и место проведения данного мероприятия? (проверка #{int(time.time())})"
    print("2. Тест Context Stuffing (новый вопрос по тексту регламента)...")
    resp2 = await ask_regulation_question(
        session=session,
        selection_id=selection_id,
        event_id=event_id,
        question_text=unique_q,
    )
    print(f"   [OK] from_cache={resp2.from_cache}, is_answer_found={resp2.is_answer_found}")
    print(f"   Текст ответа: {resp2.answer_text[:90]}...")
    print(f"   Цитата из регламента: {resp2.source_quote}\n")
    assert resp2.from_cache is False
    assert resp2.is_answer_found is True

    # Повторный запрос того же вопроса должен прийти уже из кэша!
    resp2_cached = await ask_regulation_question(
        session=session,
        selection_id=selection_id,
        event_id=event_id,
        question_text=unique_q,
    )
    assert resp2_cached.from_cache is True, "Повторный вопрос должен возвращаться из llm_cache!"
    print("   [OK] Повторный вызов того же вопроса успешно взят из llm_cache.\n")

    # --- ТЕСТ 3: Zero-Hallucination (провокационный вопрос вне регламента) ---
    print("3. Тест Zero-Hallucination (провокационный вопрос про вертолетный трансфер)...")
    resp3 = await ask_regulation_question(
        session=session,
        selection_id=selection_id,
        event_id=event_id,
        question_text="Предоставляете ли вы бесплатный вертолет из аэропорта до отеля для участников?",
    )
    print(f"   [OK] is_answer_found={resp3.is_answer_found}, escalated_to_telegram={resp3.escalated_to_telegram}")
    print(f"   Текст ответа: {resp3.answer_text[:100]}...\n")
    assert resp3.is_answer_found is False, "ИИ не должен выдумывать несуществующие услуги!"
    assert resp3.source_quote is None
    assert resp3.escalated_to_telegram is True

    print("[SUCCESS] ВСЕ ТЕСТЫ D-09 ПРОЙДЕНЫ УСПЕШНО!")


async def main() -> None:
    print("=== Тест D-09: Изолированный RAG, Context Stuffing и PostgreSQL llm_cache ===\n")

    if not is_postgres_online():
        print("[INFO] PostgreSQL (порт 5432) остановлен — используем InMemoryAsyncSession.\n")
        fake_db = InMemoryAsyncSession()
        await run_rag_checks(fake_db, selection_id=1, event_id=1, is_in_memory=True)
        await engine.dispose()
        return

    async with async_session_maker() as session:
        stmt = (
            select(SelectionItem)
            .join(Selection, Selection.id == SelectionItem.selection_id)
            .order_by(Selection.id.desc(), SelectionItem.bundle_group.asc(), SelectionItem.id.asc())
            .limit(1)
        )
        res = await session.execute(stmt)
        item = res.scalar_one_or_none()

        if item is None:
            ev_res = await session.execute(select(Event).where(Event.is_active.is_(True)).order_by(Event.id.asc()).limit(1))
            first_ev = ev_res.scalar_one()
            first_tar_id = first_ev.tariffs[0].id if first_ev.tariffs else None
            sel = Selection(
                client_id=1,
                status="published",
                generated_pitch_text="Тестовая подборка D-09",
                total_budget_limit=300000.0,
            )
            session.add(sel)
            await session.flush()
            item = SelectionItem(
                selection_id=sel.id,
                event_id=first_ev.id,
                recommended_tariff_id=first_tar_id,
                bundle_group=1,
                ai_rationale="Тестовое обоснование",
            )
            session.add(item)
            await session.commit()

        await run_rag_checks(session, selection_id=item.selection_id, event_id=item.event_id, is_in_memory=False)

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
