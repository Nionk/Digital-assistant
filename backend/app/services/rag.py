import asyncio
import datetime
import hashlib
import logging

import httpx
from openai import APIError
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.models import (
    ChatMessage,
    Client,
    Event,
    EventChunk,
    EventTariff,
    LLMCache,
    Selection,
    SelectionItem,
    User,
)
from app.schemas.showcase import AskRegulationQuestionOut
from app.services.ai_client import LLM_SEMAPHORE, get_embedding, structured_llm_client
from app.services.telegram import format_escalation_alert, send_manager_alert

logger = logging.getLogger(__name__)

POLITE_FALLBACK_TEXT = (
    "Точных данных по этому вопросу нет в открытом регламенте мероприятия (как правило, такие детали "
    "согласовываются с оргкомитетом в индивидуальном порядке). "
    "Вы можете передать вопрос персональному менеджеру для уточнения у организаторов."
)


class RAGResponse(BaseModel):
    """Строгая схема ответа ИИ по регламенту мероприятия (Zero-Hallucination контракт)."""

    is_answer_found: bool = Field(
        ...,
        description=(
            "True, если в предоставленном тексте регламента или параметрах тарифа есть точный ответ на вопрос. "
            "False, если информации нет в тексте или требуется додумывать."
        ),
    )
    answer_text: str = Field(
        ...,
        description=(
            "Вежливый и точный ответ клиенту строго по фактам регламента. "
            "Если is_answer_found=False, напиши вежливое сообщение о том, что точных данных нет в открытом регламенте "
            "мероприятия и клиент может передать вопрос персональному менеджеру для уточнения у организаторов."
        ),
    )
    source_quote: str | None = Field(
        None,
        description="Дословная цитата из текста регламента, подтверждающая ответ (обязательна при is_answer_found=True, иначе None).",
    )


def build_rag_cache_key(event_id: int, tariff_id: int, question_text: str) -> str:
    """Вычисляет детерминированный SHA-256 ключ для таблицы llm_cache с изоляцией по тарифу."""
    normalized_q = question_text.strip().lower()
    raw_key = f"{event_id}:{tariff_id}:{normalized_q}"
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


async def invalidate_rag_cache(session: AsyncSession, event_id: int) -> int:
    """
    Инвалидация кэша ответов RAG при обновлении мероприятия или его тарифов (Раздел 12.8 artifact.md).
    DELETE FROM llm_cache WHERE event_id = :event_id RETURNING cache_key
    """
    stmt = (
        delete(LLMCache)
        .where(LLMCache.event_id == event_id)
        .returning(LLMCache.cache_key)
    )
    result = await session.execute(stmt)
    deleted_keys = result.scalars().all()
    await session.commit()
    return len(deleted_keys)


async def _resolve_selection_context(
    session: AsyncSession,
    selection_id: int,
) -> tuple[Selection | None, str, int | None]:
    """Возвращает (selection, company_name, manager_chat_id) для логирования и алертов."""
    selection = await session.get(Selection, selection_id)
    if not selection:
        return None, "Клиент", None

    client = await session.get(Client, selection.client_id) if selection.client_id else None
    company_name = client.company_name if client else f"Клиент #{selection.client_id}"

    manager_chat_id: int | None = None
    if client and client.manager_id:
        manager = await session.get(User, client.manager_id)
        if manager and manager.telegram_chat_id:
            manager_chat_id = manager.telegram_chat_id

    return selection, company_name, manager_chat_id


async def _save_chat_message(
    session: AsyncSession,
    selection_id: int,
    event_id: int,
    question: str,
    answer: str,
    needs_attention: bool,
) -> None:
    """Записывает вопрос клиента и ответ ИИ в таблицу chat_messages."""
    session.add(
        ChatMessage(
            selection_id=selection_id,
            event_id=event_id,
            sender_role="client",
            message_text=question,
            needs_manager_attention=False,
        )
    )
    session.add(
        ChatMessage(
            selection_id=selection_id,
            event_id=event_id,
            sender_role="ai_assistant",
            message_text=answer,
            needs_manager_attention=needs_attention,
        )
    )


async def _retrieve_regulation_chunks(
    session: AsyncSession,
    event_id: int,
    question: str,
    fallback_text: str,
) -> str:
    """
    Фолбэк-режим (Chunk Hybrid RAG): извлечение Топ-5 чанков из event_chunks со строгим WHERE event_id = :event_id.
    Используется, если регламент превышает 35 000 символов (Раздел 10.4 artifact.md).
    """
    q_vec: list[float] | None = None
    if settings.EMBEDDING_API_KEY:
        try:
            q_vec = await get_embedding(question)
        except (RuntimeError, APIError, httpx.HTTPError) as exc:
            logger.warning(
                "Не удалось получить вектор вопроса для поиска по чанкам: %s",
                exc,
                exc_info=True,
            )

    if q_vec is not None:
        stmt = (
            select(EventChunk)
            .where(EventChunk.event_id == event_id)
            .order_by(EventChunk.embedding.cosine_distance(q_vec))
            .limit(5)
        )
    else:
        stmt = (
            select(EventChunk)
            .where(EventChunk.event_id == event_id)
            .order_by(EventChunk.chunk_index.asc())
            .limit(5)
        )

    res = await session.execute(stmt)
    chunks = res.scalars().all()
    if chunks:
        return "\n\n---\n\n".join(ch.content for ch in chunks)

    logger.warning("Чанки для event_id=%s не найдены в БД. Используется начало регламента.", event_id)
    return fallback_text[:35000]


def _build_tariff_context(tariff: EventTariff | None, today: datetime.date) -> str:
    """Формирует текстовый контекст параметров рекомендованного тарифа для системного промпта."""
    if tariff is None:
        return "Рекомендованный тариф: не зафиксирован (общие условия участия)."

    base_val = float(tariff.base_price) if tariff.base_price is not None else None
    eb_val = float(tariff.early_bird_price) if tariff.early_bird_price is not None else None
    eb_dl = tariff.early_bird_deadline

    price_parts: list[str] = []
    if base_val is None:
        price_parts.append("Базовая стоимость: По запросу")
    else:
        price_parts.append(f"Базовая стоимость: {int(base_val)} руб. (с НДС)")

    if eb_val is not None and eb_dl is not None:
        status_eb = "активна" if eb_dl >= today else "завершена"
        price_parts.append(f"Цена Early Bird: {int(eb_val)} руб. до {eb_dl.isoformat()} ({status_eb})")

    return (
        f"Рекомендованный тариф: «{tariff.tariff_name}» (роль: {tariff.participation_role}). "
        f"{'; '.join(price_parts)}. "
        f"Включенные опции: {tariff.included_benefits or 'согласно общей программе'}."
    )


async def _find_recommended_tariff(
    session: AsyncSession,
    selection_id: int,
    event_id: int,
) -> tuple[int, EventTariff | None]:
    """Извлекает ID и ORM-объект рекомендованного тарифа для мероприятия в рамках подборки."""
    item_stmt = (
        select(SelectionItem)
        .where(
            SelectionItem.selection_id == selection_id,
            SelectionItem.event_id == event_id,
        )
        .order_by(SelectionItem.bundle_group.asc(), SelectionItem.id.asc())
        .limit(1)
    )
    item_res = await session.execute(item_stmt)
    selection_item = item_res.scalars().first()
    tariff_id = (
        selection_item.recommended_tariff_id
        if (selection_item and selection_item.recommended_tariff_id)
        else 0
    )
    tariff = await session.get(EventTariff, tariff_id) if tariff_id else None
    return tariff_id, tariff


async def _try_load_cached_rag_response(
    session: AsyncSession,
    cache_key: str,
) -> RAGResponse | None:
    """Проверяет таблицу llm_cache и валидирует JSON через строгую схему RAGResponse."""
    cache_res = await session.execute(select(LLMCache).where(LLMCache.cache_key == cache_key))
    cached_entry = cache_res.scalar_one_or_none()
    if cached_entry is None:
        return None
    try:
        parsed = RAGResponse.model_validate_json(cached_entry.response_text)
        if not parsed.is_answer_found:
            parsed.source_quote = None
        if not parsed.answer_text.strip():
            parsed.answer_text = POLITE_FALLBACK_TEXT
        return parsed
    except (ValidationError, ValueError) as val_err:
        logger.warning(
            "Поврежденная запись в llm_cache (key=%s): %s. Переход к генерации.",
            cache_key,
            val_err,
            exc_info=True,
        )
        return None


def _build_rag_prompts(
    event: Event,
    tariff: EventTariff | None,
    regulation_text: str,
    question_clean: str,
    today: datetime.date,
) -> tuple[str, str]:
    """Формирует системный и пользовательский промпты для изолированного RAG."""
    tariff_context = _build_tariff_context(tariff, today)
    location_str = "Онлайн" if event.is_online else (event.city or "Не указан")
    system_prompt = (
        "Ты — точный консультант по регламентам и условиям участия деловых мероприятий.\n"
        "Твоя задача — ответить на вопрос клиента ИСКЛЮЧИТЕЛЬНО на основе предоставленного ниже "
        "регламента конкретного мероприятия и параметров рекомендованного тарифа.\n\n"
        "ЖЕСТКИЕ ПРАВИЛА (ZERO-HALLUCINATION):\n"
        "1. Отвечай только по фактам из текста. Никогда не додумывай цены, скидки, трансферы, отели или технические условия.\n"
        "2. Если точного ответа в тексте регламента и описании тарифа НЕТ, обязательно верни `is_answer_found=False`, "
        "`source_quote=None` и вежливо напиши: 'Точных данных по этому вопросу нет в открытом регламенте мероприятия "
        "(как правило, такие детали согласовываются с оргкомитетом в индивидуальном порядке). "
        "Вы можете передать вопрос персональному менеджеру для уточнения у организаторов.'\n"
        "3. Если ответ найден (`is_answer_found=True`), приведи в `source_quote` точную подтверждающую цитату из текста.\n\n"
        f"Контекст карточки мероприятия:\n"
        f"- Название: {event.canonical_title}\n"
        f"- Локация и площадка: {location_str}, {event.venue or 'уточняется'}\n"
        f"- Даты проведения: {event.start_date.isoformat()} — {event.end_date.isoformat()}\n"
        f"- {tariff_context}"
    )
    user_prompt = (
        f"Официальный регламент и программа мероприятия:\n"
        f"---\n{regulation_text}\n---\n\n"
        f"Вопрос клиента: {question_clean}"
    )
    return system_prompt, user_prompt


async def _query_rag_llm(
    event_id: int,
    system_prompt: str,
    user_prompt: str,
) -> RAGResponse:
    """Выполняет защищенный LLM_SEMAPHORE запрос к LLM со схемой RAGResponse."""
    try:
        async with LLM_SEMAPHORE:
            llm_res: RAGResponse = await asyncio.wait_for(
                structured_llm_client.chat.completions.create(
                    model=settings.LLM_MODEL,
                    response_model=RAGResponse,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    max_retries=2,
                ),
                timeout=25.0,
            )
    except (TimeoutError, APIError, httpx.HTTPError) as exc:
        logger.exception(
            "Сетевой сбой при обращении к LLM в RAG (event_id=%s)",
            event_id,
        )
        raise RuntimeError(f"Сервис RAG временно недоступен: {exc}") from exc

    if not llm_res.is_answer_found:
        llm_res.source_quote = None
        if not llm_res.answer_text or not llm_res.answer_text.strip():
            llm_res.answer_text = POLITE_FALLBACK_TEXT
    return llm_res


async def _persist_and_escalate_rag_result(
    session: AsyncSession,
    selection_id: int,
    event: Event,
    question_clean: str,
    primary_cache_key: str,
    llm_res: RAGResponse,
    auto_escalate: bool,
) -> AskRegulationQuestionOut:
    """Сохраняет ответ LLM в кэш/историю чата и при необходимости эскалирует вопрос менеджеру в Telegram."""
    if llm_res.is_answer_found:
        session.add(
            LLMCache(
                cache_key=primary_cache_key,
                event_id=event.id,
                response_text=llm_res.model_dump_json(),
            )
        )

    selection_obj, company_name, manager_chat_id = await _resolve_selection_context(session, selection_id)
    escalated = False
    if not llm_res.is_answer_found and auto_escalate:
        alert_text = format_escalation_alert(
            company_name=company_name,
            event_title=event.canonical_title,
            question_text=question_clean,
        )
        escalated = await send_manager_alert(alert_text, chat_id=manager_chat_id)

    if selection_obj is not None:
        await _save_chat_message(
            session=session,
            selection_id=selection_id,
            event_id=event.id,
            question=question_clean,
            answer=llm_res.answer_text,
            needs_attention=not llm_res.is_answer_found,
        )
    await session.commit()

    return AskRegulationQuestionOut(
        event_id=event.id,
        question_text=question_clean,
        is_answer_found=llm_res.is_answer_found,
        answer_text=llm_res.answer_text,
        source_quote=llm_res.source_quote,
        from_cache=False,
        escalated_to_telegram=escalated,
    )


async def _build_cached_rag_out(
    session: AsyncSession,
    selection_id: int,
    event_id: int,
    question_clean: str,
    cached_rag: RAGResponse,
) -> AskRegulationQuestionOut:
    """Формирует ответ из кэша RAG и фиксирует вопрос/ответ в истории чата подборки."""
    selection_obj, _, _ = await _resolve_selection_context(session, selection_id)
    if selection_obj is not None:
        await _save_chat_message(
            session=session,
            selection_id=selection_id,
            event_id=event_id,
            question=question_clean,
            answer=cached_rag.answer_text,
            needs_attention=False,
        )
        await session.commit()
    return AskRegulationQuestionOut(
        event_id=event_id,
        question_text=question_clean,
        is_answer_found=cached_rag.is_answer_found,
        answer_text=cached_rag.answer_text,
        source_quote=cached_rag.source_quote,
        from_cache=True,
        escalated_to_telegram=False,
    )


async def ask_regulation_question(
    session: AsyncSession,
    selection_id: int,
    event_id: int,
    question_text: str,
    auto_escalate: bool = False,
) -> AskRegulationQuestionOut:
    """
    Изолированный RAG-ответ клиенту по регламенту конкретного события (Раздел 10.4 artifact.md).
    """
    question_clean = question_text.strip()
    event = await session.get(Event, event_id)
    if not event:
        raise LookupError(f"Мероприятие с ID={event_id} не найдено")

    tariff_id, tariff = await _find_recommended_tariff(session, selection_id, event_id)
    primary_cache_key = build_rag_cache_key(event_id, tariff_id, question_clean)

    cached_rag = await _try_load_cached_rag_response(session, primary_cache_key)
    if cached_rag is not None:
        return await _build_cached_rag_out(session, selection_id, event_id, question_clean, cached_rag)

    regulation_text = (event.full_regulation_markdown or event.summary or "").strip()
    if len(regulation_text) > 35000:
        regulation_text = await _retrieve_regulation_chunks(
            session=session,
            event_id=event_id,
            question=question_clean,
            fallback_text=regulation_text,
        )

    system_prompt, user_prompt = _build_rag_prompts(
        event=event,
        tariff=tariff,
        regulation_text=regulation_text,
        question_clean=question_clean,
        today=datetime.date.today(),
    )
    llm_res = await _query_rag_llm(event_id, system_prompt, user_prompt)
    return await _persist_and_escalate_rag_result(
        session=session,
        selection_id=selection_id,
        event=event,
        question_clean=question_clean,
        primary_cache_key=primary_cache_key,
        llm_res=llm_res,
        auto_escalate=auto_escalate,
    )
