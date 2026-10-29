import hashlib
import json
import logging
from typing import Optional
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Event, EventTariff, LLMCache, ChatMessage, SelectionItem
from app.schemas.showcase import AskRegulationQuestionOut
from app.services.ai_client import structured_llm_client
from app.core.config import settings

logger = logging.getLogger(__name__)

# Строгая схема ответа от LLM (Zero-Hallucination)
class RAGResponse(BaseModel):
    is_answer_found: bool = Field(
        ..., description="True, если в предоставленных фрагментах регламента есть точный ответ на вопрос. False, если информации нет или нужно додумывать."
    )
    answer_text: str = Field(
        ..., description="Вежливый и точный ответ клиенту по тексту регламента. Если is_answer_found=False, напиши: 'Точных данных по этому вопросу нет в открытом регламенте. Я уже передал ваш вопрос персональному менеджеру, мы уточним детали у организаторов и вернемся с ответом.'"
    )
    source_quote: Optional[str] = Field(None, description="Точная цитата из документа, на которой основан ответ.")

async def ask_regulation_question(
    session: AsyncSession,
    selection_id: int,
    event_id: int,
    question_text: str
) -> AskRegulationQuestionOut:
    """
    Изолированный RAG-ответ клиенту по регламенту конкретного события.
    1. Проверяет точный кэш (llm_cache) по SHA-256.
    2. Если кэша нет — достает регламент и делает Context Stuffing.
    3. Логирует вопрос в chat_messages и возвращает ответ.
    """
    question_clean = question_text.strip()
    question_lower = question_clean.lower()

    # 1. Получаем контекст из БД (Мероприятие, Тариф из подборки клиента)
    item_stmt = select(SelectionItem).where(
        SelectionItem.selection_id == selection_id,
        SelectionItem.event_id == event_id
    )
    item_res = await session.execute(item_stmt)
    selection_item = item_res.scalar_one_or_none()
    
    tariff_id = selection_item.recommended_tariff_id if selection_item else 0
    
    event = await session.get(Event, event_id)
    if not event:
        raise ValueError("Мероприятие не найдено")

    tariff = await session.get(EventTariff, tariff_id) if tariff_id else None

    # 2. Проверяем точный кэш
    cache_key = hashlib.sha256(f"{event_id}:{tariff_id}:{question_lower}".encode("utf-8")).hexdigest()
    cache_stmt = select(LLMCache).where(LLMCache.cache_key == cache_key)
    cache_res = await session.execute(cache_stmt)
    cached_entry = cache_res.scalar_one_or_none()

    if cached_entry:
        cached_data = json.loads(cached_entry.response_text)
        # Записываем в историю чата
        await _save_chat_message(session, selection_id, event_id, question_clean, cached_data["answer_text"], not cached_data["is_answer_found"])
        
        return AskRegulationQuestionOut(
            event_id=event_id,
            question_text=question_clean,
            is_answer_found=cached_data["is_answer_found"],
            answer_text=cached_data["answer_text"],
            source_quote=cached_data.get("source_quote"),
            from_cache=True,
            escalated_to_telegram=not cached_data["is_answer_found"]
        )

    # 3. Если кэша нет — формируем контекст (Context Stuffing)
    regulation_text = event.full_regulation_markdown or ""
    
    # Защита от переполнения контекста (хотя для P-03 это будет чанкинг)
    if len(regulation_text) > 35000:
        regulation_text = regulation_text[:35000] + "\n...[Текст обрезан]..."

    tariff_context = "Тариф не выбран."
    if tariff:
        tariff_context = f"Тариф: {tariff.tariff_name}. Условия: {tariff.included_benefits}."

    system_prompt = f"""Ты — экспертный ИИ-ассистент B2B-агентства «СКАРТ».
Твоя задача — ответить на вопрос клиента СТРОГО на основе предоставленного текста регламента мероприятия.

ПРАВИЛА:
1. Если ответа нет в тексте, верни `is_answer_found=False` и вежливо сообщи, что передал вопрос менеджеру.
2. Никогда не выдумывай цифры, даты и условия, которых нет в тексте.
3. В поле `source_quote` приведи точную цитату из текста, на которой основан ответ.

Контекст клиента:
Мероприятие: {event.canonical_title}
{tariff_context}
"""

    user_prompt = f"""Текст регламента:
{regulation_text}

Вопрос клиента: {question_clean}"""

    try:
        llm_res: RAGResponse = await structured_llm_client.chat.completions.create(
            model=settings.LLM_MODEL,
            response_model=RAGResponse,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            max_retries=2,
            timeout=20.0
        )
    except Exception as e:
        logger.error(f"Ошибка RAG LLM: {e}")
        # Фолбэк при сбое сети
        llm_res = RAGResponse(
            is_answer_found=False,
            answer_text="Извините, произошла техническая ошибка при обработке вопроса. Я передал его менеджеру.",
            source_quote=None
        )

    # 4. Сохраняем результат в кэш (только если ответ найден, чтобы не кэшировать ошибки)
    if llm_res.is_answer_found:
        new_cache = LLMCache(
            cache_key=cache_key,
            event_id=event_id,
            response_text=json.dumps({
                "is_answer_found": llm_res.is_answer_found,
                "answer_text": llm_res.answer_text,
                "source_quote": llm_res.source_quote
            }, ensure_ascii=False)
        )
        session.add(new_cache)

    # 5. Логируем в чат и сохраняем БД
    await _save_chat_message(session, selection_id, event_id, question_clean, llm_res.answer_text, not llm_res.is_answer_found)
    await session.commit()

    return AskRegulationQuestionOut(
        event_id=event_id,
        question_text=question_clean,
        is_answer_found=llm_res.is_answer_found,
        answer_text=llm_res.answer_text,
        source_quote=llm_res.source_quote,
        from_cache=False,
        escalated_to_telegram=not llm_res.is_answer_found
    )


async def _save_chat_message(session: AsyncSession, selection_id: int, event_id: int, question: str, answer: str, needs_attention: bool):
    """Вспомогательная функция для записи диалога в chat_messages."""
    # Запись вопроса клиента
    session.add(ChatMessage(
        selection_id=selection_id, event_id=event_id, sender_role="client",
        message_text=question, needs_manager_attention=False
    ))
    # Запись ответа ИИ
    session.add(ChatMessage(
        selection_id=selection_id, event_id=event_id, sender_role="ai_assistant",
        message_text=answer, needs_manager_attention=needs_attention
    ))