import asyncio
import datetime
import hashlib
import json
import logging
from typing import Optional
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
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
from app.schemas.showcase import AskRegulationQuestionOut
from app.services.ai_client import structured_llm_client
from app.services.telegram import format_escalation_alert, send_manager_alert

logger = logging.getLogger(__name__)

POLITE_FALLBACK_TEXT = (
    "Точных данных по этому вопросу нет в открытом регламенте мероприятия. "
    "Я уже передал ваш вопрос персональному менеджеру — мы оперативно уточним детали "
    "у организаторов и вернемся к вам с ответом."
)


class RAGResponse(BaseModel):
    """Строгая схема ответа ИИ по регламенту (Zero-Hallucination)."""

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
            "и вопрос уже передан персональному менеджеру для уточнения у организаторов."
        ),
    )
    source_quote: Optional[str] = Field(
        None,
        description="Дословная цитата из текста регламента, подтверждающая ответ (обязательна при is_answer_found=True, иначе None).",
    )


def build_rag_cache_key(event_id: int, tariff_id: int, question_text: str) -> str:
    """Вычисляет детерминированный SHA-256 ключ для таблицы llm_cache."""
    normalized_q = question_text.strip().lower()
    raw_key = f"{event_id}:{tariff_id}:{normalized_q}"
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


async def _resolve_selection_context(
    session: AsyncSession,
    selection_id: int,
) -> tuple[Selection | None, str, int | None]:
    """
    Возвращает (selection_obj, company_name, manager_telegram_chat_id) для логирования и алертов.
    """
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
    """Записывает вопрос клиента и ответ ИИ-ассистента в таблицу chat_messages."""
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


async def ask_regulation_question(
    session: AsyncSession,
    selection_id: int,
    event_id: int,
    question_text: str,
) -> AskRegulationQuestionOut:
    """
    Изолированный RAG-ответ клиенту по регламенту конкретного события (Задача D-09).
    1. Находит рекомендованный тариф в подборке (защищено от дублей между bundle_group=1 и 2).
    2. Проверяет точный кэш в таблице llm_cache по SHA-256.
    3. При промахе кэша передает регламент (Context Stuffing <= 35 000 символов) и параметры тарифа в LLM.
    4. Сохраняет диалог в chat_messages (с коммитом транзакции) и при is_answer_found=False отправляет пуш в Telegram.
    """
    question_clean = question_text.strip()

    # 1. Получаем мероприятие
    event = await session.get(Event, event_id)
    if not event:
        raise LookupError(f"Мероприятие с ID={event_id} не найдено")

    # Безопасная выборка элемента подборки (упорядочено по bundle_group=1, чтобы не падать с MultipleResultsFound)
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

    tariff_id = selection_item.recommended_tariff_id if (selection_item and selection_item.recommended_tariff_id) else 0
    tariff = await session.get(EventTariff, tariff_id) if tariff_id else None

    selection_obj, company_name, manager_chat_id = await _resolve_selection_context(session, selection_id)

    # 2. Проверяем точный кэш (сначала по конкретному tariff_id, затем по общему ключу события tariff_id=0)
    primary_cache_key = build_rag_cache_key(event_id, tariff_id, question_clean)
    cache_keys_to_check = [primary_cache_key]
    if tariff_id != 0:
        cache_keys_to_check.append(build_rag_cache_key(event_id, 0, question_clean))

    cached_entry: LLMCache | None = None
    for ck in cache_keys_to_check:
        res = await session.execute(select(LLMCache).where(LLMCache.cache_key == ck))
        cached_entry = res.scalar_one_or_none()
        if cached_entry is not None:
            break

    if cached_entry is not None:
        cached_data = json.loads(cached_entry.response_text)
        is_found = bool(cached_data.get("is_answer_found", True))
        ans_text = str(cached_data.get("answer_text") or POLITE_FALLBACK_TEXT)
        src_quote = cached_data.get("source_quote") if is_found else None

        if selection_obj is not None:
            await _save_chat_message(
                session=session,
                selection_id=selection_id,
                event_id=event_id,
                question=question_clean,
                answer=ans_text,
                needs_attention=not is_found,
            )
            await session.commit()

        escalated = False
        if not is_found:
            alert_html = format_escalation_alert(company_name, event.canonical_title, question_clean)
            await send_manager_alert(alert_html, chat_id=manager_chat_id)
            escalated = True

        return AskRegulationQuestionOut(
            event_id=event_id,
            question_text=question_clean,
            is_answer_found=is_found,
            answer_text=ans_text,
            source_quote=src_quote,
            from_cache=True,
            escalated_to_telegram=escalated,
        )

    # 3. Формируем изолированный контекст регламента (Context Stuffing <= 35 000 символов)
    regulation_text = (event.full_regulation_markdown or event.summary or "").strip()
    if len(regulation_text) > 35000:
        regulation_text = regulation_text[:35000] + "\n...[Текст регламента сокращен до 35 000 символов]..."

    today = datetime.date.today()
    if tariff is not None:
        base_val = float(tariff.base_price) if tariff.base_price is not None else None
        eb_val = float(tariff.early_bird_price) if tariff.early_bird_price is not None else None
        eb_dl = tariff.early_bird_deadline

        price_parts = []
        if base_val is None:
            price_parts.append("Базовая стоимость: По запросу")
        else:
            price_parts.append(f"Базовая стоимость: {int(base_val)} руб. (с НДС)")
        if eb_val is not None and eb_dl is not None:
            status_eb = "активна" if eb_dl >= today else "завершена"
            price_parts.append(f"Цена Early Bird: {int(eb_val)} руб. до {eb_dl.isoformat()} ({status_eb})")

        tariff_context = (
            f"Рекомендованный тариф: «{tariff.tariff_name}» (роль: {tariff.participation_role}). "
            f"{'; '.join(price_parts)}. "
            f"Включенные опции: {tariff.included_benefits or 'согласно общей программе'}."
        )
    else:
        tariff_context = "Рекомендованный тариф: не зафиксирован (общие условия участия)."

    location_str = "Онлайн" if event.is_online else (event.city or "Не указан")
    system_prompt = (
        "Ты — точный ИИ-консультант B2B-платформы сопровождения мероприятий «СКАРТ».\n"
        "Твоя задача — ответить на вопрос клиента ИСКЛЮЧИТЕЛЬНО на основе предоставленного ниже "
        "регламента конкретного мероприятия и параметров рекомендованного тарифа.\n\n"
        "ЖЕСТКИЕ ПРАВИЛА (ZERO-HALLUCINATION):\n"
        "1. Отвечай только по фактам из текста. Никогда не додумывай цены, скидки, трансферы, отели или технические условия.\n"
        "2. Если точного ответа в тексте регламента и описании тарифа НЕТ, обязательно верни `is_answer_found=False`, "
        "`source_quote=None` и вежливо напиши, что точных данных по этому вопросу нет в открытом регламенте, "
        "поэтому вопрос уже передан персональному менеджеру для уточнения у организаторов.\n"
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

    llm_call_succeeded = False
    try:
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
        llm_call_succeeded = True
    except Exception as exc:
        logger.error("Ошибка вызова LLM в RAG (event_id=%s): %s", event_id, exc)
        llm_res = RAGResponse(
            is_answer_found=False,
            answer_text=POLITE_FALLBACK_TEXT,
            source_quote=None,
        )

    # Нормализация полей ответа
    if not llm_res.is_answer_found:
        llm_res.source_quote = None
        if not llm_res.answer_text or not llm_res.answer_text.strip():
            llm_res.answer_text = POLITE_FALLBACK_TEXT

    # 4. Сохраняем успешный положительный ответ в llm_cache (защищено от дублирования PK)
    if llm_call_succeeded and llm_res.is_answer_found:
        existing_cache = await session.get(LLMCache, primary_cache_key)
        if existing_cache is None:
            session.add(
                LLMCache(
                    cache_key=primary_cache_key,
                    event_id=event_id,
                    response_text=json.dumps(
                        {
                            "is_answer_found": True,
                            "answer_text": llm_res.answer_text,
                            "source_quote": llm_res.source_quote,
                        },
                        ensure_ascii=False,
                    ),
                )
            )

    # 5. Записываем диалог в chat_messages и фиксируем транзакцию
    if selection_obj is not None:
        await _save_chat_message(
            session=session,
            selection_id=selection_id,
            event_id=event_id,
            question=question_clean,
            answer=llm_res.answer_text,
            needs_attention=not llm_res.is_answer_found,
        )
    await session.commit()

    # 6. При отсутствии ответа в регламенте эскалируем вопрос менеджеру в Telegram
    escalated = False
    if not llm_res.is_answer_found:
        alert_html = format_escalation_alert(company_name, event.canonical_title, question_clean)
        await send_manager_alert(alert_html, chat_id=manager_chat_id)
        escalated = True

    return AskRegulationQuestionOut(
        event_id=event_id,
        question_text=question_clean,
        is_answer_found=llm_res.is_answer_found,
        answer_text=llm_res.answer_text,
        source_quote=llm_res.source_quote,
        from_cache=False,
        escalated_to_telegram=escalated,
    )
