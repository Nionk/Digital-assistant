import datetime
import logging
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import FAQ_QUICK_CHIPS
from app.core.database import get_async_session
from app.core.timeutils import today_local
from app.models.models import (
    ChatMessage,
    Client,
    Event,
    EventTariff,
    Selection,
    SelectionItem,
    User,
)
from app.schemas.showcase import (
    AskRegulationQuestionIn,
    AskRegulationQuestionOut,
    ClientReactionIn,
    ClientReactionOut,
    EscalateQuestionIn,
    EscalateQuestionOut,
    ShowcaseEventItemOut,
    ShowcaseViewOut,
)
from app.services.rag import RAGUnavailableError, ask_regulation_question
from app.services.telegram import (
    format_escalation_alert,
    format_reaction_alert,
    send_manager_alert,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/public/s", tags=["Client Public Showcase (Magic Link)"])

AsyncSessionDep = Annotated[AsyncSession, Depends(get_async_session)]
ShowcaseEventFormat = Literal[
    "roundtable", "business_breakfast", "forum", "conference", "session"
]
ShowcaseRole = Literal["delegate", "speaker", "sponsor"]
ShowcaseReaction = Literal["pending", "interested", "rejected"]


def _normalize_event_format(fmt: str | None) -> ShowcaseEventFormat:
    if fmt == "roundtable":
        return "roundtable"
    if fmt == "business_breakfast":
        return "business_breakfast"
    if fmt == "forum":
        return "forum"
    if fmt == "session":
        return "session"
    return "conference"


def _normalize_role(role: str | None) -> ShowcaseRole:
    if role == "speaker":
        return "speaker"
    if role == "sponsor":
        return "sponsor"
    return "delegate"


def _normalize_reaction(reaction: str | None) -> ShowcaseReaction:
    if reaction == "interested":
        return "interested"
    if reaction == "rejected":
        return "rejected"
    return "pending"


@router.get(
    "/{magic_token}",
    response_model=ShowcaseViewOut,
    summary="Получение персональной витрины клиента по защищенной ссылке Magic Link",
    description=(
        "Публичный маршрут без авторизации. Доступ осуществляется строго по криптостойкому UUIDv4 токену. "
        "Возвращает сопроводительное письмо, сводную плашку бюджета, карточки мероприятий и чипсы быстрых вопросов FAQ."
    ),
)
# [AUDIT-CRUTCH]: Высокая цикломатическая сложность (ранг D в complexity_report.txt).
async def get_public_showcase(
    magic_token: UUID,
    db: AsyncSessionDep,
) -> ShowcaseViewOut:
    """
    Загружает опубликованную витрину клиента по magic_token из БД.
    """
    stmt = select(Selection).where(
        Selection.magic_token == magic_token,
        Selection.status == "published",
    )
    selection = None
    try:
        result = await db.execute(stmt)
        selection = result.scalar_one_or_none()
    except (SQLAlchemyError, OSError) as exc:
        logger.error("Ошибка БД при получении витрины %s: %s", magic_token, exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="База данных временно недоступна",
        ) from exc

    if selection is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Витрина не найдена или еще не опубликована",
        )

    client = selection.client or await db.get(Client, selection.client_id)
    manager = await db.get(User, client.manager_id) if (client and client.manager_id) else None

    items_stmt = (
        select(SelectionItem)
        .where(
            SelectionItem.selection_id == selection.id,
            SelectionItem.bundle_group == 1,
        )
        .order_by(SelectionItem.id.asc())
    )
    items_res = await db.execute(items_stmt)
    items = items_res.scalars().all()

    today = today_local()
    showcase_items: list[ShowcaseEventItemOut] = []
    total_actual = 0.0
    total_savings = 0.0
    earliest_deadline: datetime.date | None = None

    # Пакетная загрузка связанных Event и EventTariff для устранения N+1 запросов
    ev_ids_to_fetch = {item.event_id for item in items if not item.event}
    tar_ids_to_fetch = {
        item.recommended_tariff_id
        for item in items
        if item.recommended_tariff_id and not item.recommended_tariff
    }

    events_map: dict[int, Event] = {}
    if ev_ids_to_fetch:
        ev_res = await db.execute(select(Event).where(Event.id.in_(ev_ids_to_fetch)))
        events_map = {e.id: e for e in ev_res.scalars().all()}

    tariffs_map: dict[int, EventTariff] = {}
    if tar_ids_to_fetch:
        tar_res = await db.execute(select(EventTariff).where(EventTariff.id.in_(tar_ids_to_fetch)))
        tariffs_map = {t.id: t for t in tar_res.scalars().all()}

    for item in items:
        event = item.event or events_map.get(item.event_id)
        if not event:
            continue

        tariff = item.recommended_tariff or (
            tariffs_map.get(item.recommended_tariff_id) if item.recommended_tariff_id else None
        )

        # Фолбэк, если recommended_tariff_id сброшен в NULL (например, после обновления тарифов скрейпером)
        if tariff is None and event.tariffs:
            low_rationale = (item.ai_rationale or "").lower()
            if "спикер" in low_rationale or "выступлен" in low_rationale:
                tariff = next((t for t in event.tariffs if t.participation_role == "speaker"), None)
            if tariff is None:
                priced_tariffs = [t for t in event.tariffs if t.base_price is not None]
                tariff = (
                    min(priced_tariffs, key=lambda t: float(t.base_price or 0.0))
                    if priced_tariffs
                    else event.tariffs[0]
                )

        if tariff is not None:
            base = float(tariff.base_price) if tariff.base_price is not None else None
            eb = float(tariff.early_bird_price) if tariff.early_bird_price is not None else None
            actual = base
            savings = 0.0
            if base is not None and eb is not None and tariff.early_bird_deadline and tariff.early_bird_deadline >= today:
                actual = eb
                if base > eb:
                    savings = round(base - eb, 2)

            if (
                savings > 0
                and tariff.early_bird_deadline
                and (earliest_deadline is None or tariff.early_bird_deadline < earliest_deadline)
            ):
                earliest_deadline = tariff.early_bird_deadline

            tariff_name = tariff.tariff_name
            role = _normalize_role(tariff.participation_role)
            included_benefits = tariff.included_benefits
            eb_deadline = tariff.early_bird_deadline
        else:
            base = None
            actual = None
            savings = 0.0
            tariff_name = "Базовый пакет участия (уточняется)"
            role = "delegate"
            included_benefits = "Условия участия уточняются у персонального менеджера."
            eb_deadline = None

        if actual is not None:
            total_actual += actual
        total_savings += savings

        ev_fmt = _normalize_event_format(event.event_format)
        reaction = _normalize_reaction(item.client_reaction)

        showcase_items.append(
            ShowcaseEventItemOut(
                selection_item_id=item.id,
                event_id=event.id,
                canonical_title=event.canonical_title,
                event_format=ev_fmt,
                city=event.city,
                is_online=event.is_online,
                venue=event.venue,
                start_date=event.start_date,
                end_date=event.end_date,
                summary=event.summary,
                themes=list(event.themes or []),
                tariff_name=tariff_name,
                participation_role=role,
                actual_price=actual,
                base_price=base,
                early_bird_deadline=eb_deadline,
                savings=savings,
                included_benefits=included_benefits,
                ai_rationale=item.ai_rationale or "",
                client_reaction=reaction,
                client_comment=item.client_comment,
            )
        )

    return ShowcaseViewOut(
        selection_id=selection.id,
        company_name=client.company_name if client else "Уважаемый клиент",
        manager_full_name=manager.full_name if manager else "Персональный менеджер сопровождения",
        pitch_text=selection.generated_pitch_text or "Здравствуйте! Направляем вашу персональную подборку мероприятий.",
        total_events_count=len(showcase_items),
        total_actual_price=round(total_actual, 2),
        total_savings=round(total_savings, 2),
        min_early_bird_deadline=earliest_deadline,
        items=showcase_items,
        faq_quick_chips=list(FAQ_QUICK_CHIPS),
    )

@router.post(
    "/{magic_token}/items/{item_id}/react",
    response_model=ClientReactionOut,
    summary="Фиксация реакции клиента на карточку события и мгновенный пуш менеджеру в Telegram",
    description=(
        "Сохраняет реакцию клиента ('interested' 👍 или 'rejected' 👎) и опциональный комментарий, "
        "проверяя принадлежность карточки указанному magic_token (защита от IDOR), "
        "и отправляет уведомление персональному менеджеру в Telegram."
    ),
)
# [AUDIT-CRUTCH]: Повышенная цикломатическая сложность (ранг C в complexity_report.txt).
async def react_to_showcase_item(
    magic_token: UUID,
    item_id: int,
    payload: ClientReactionIn,
    db: AsyncSessionDep,
) -> ClientReactionOut:
    """
    Сохраняет реакцию клиента на конкретный элемент витрины и уведомляет менеджера.
    """
    stmt = select(Selection).where(
        Selection.magic_token == magic_token,
        Selection.status == "published",
    )
    selection = None
    try:
        res = await db.execute(stmt)
        selection = res.scalar_one_or_none()
    except (SQLAlchemyError, OSError) as exc:
        logger.error("Ошибка БД при реакции на витрину %s: %s", magic_token, exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="База данных временно недоступна",
        ) from exc

    if selection is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Витрина не найдена или еще не опубликована",
        )

    # Строгая проверка принадлежности item_id к данной подборке (защита от IDOR)
    item_stmt = select(SelectionItem).where(
        SelectionItem.id == item_id,
        SelectionItem.selection_id == selection.id,
    )
    item_res = await db.execute(item_stmt)
    item = item_res.scalar_one_or_none()

    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Элемент подборки не найден в данной витрине",
        )

    item.client_reaction = payload.reaction
    item.client_comment = payload.comment
    await db.commit()

    client = await db.get(Client, selection.client_id) if selection.client_id else None
    company_name = client.company_name if client else "Клиент"
    manager_chat_id: int | None = None
    if client and client.manager_id:
        manager = await db.get(User, client.manager_id)
        if manager and manager.telegram_chat_id:
            manager_chat_id = manager.telegram_chat_id

    event = await db.get(Event, item.event_id)
    event_title = event.canonical_title if event else f"Мероприятие #{item.event_id}"

    alert_html = format_reaction_alert(
        company_name=company_name,
        event_title=event_title,
        reaction=payload.reaction,
        comment=payload.comment,
    )
    notified = await send_manager_alert(alert_html, chat_id=manager_chat_id)

    return ClientReactionOut(
        selection_item_id=item_id,
        new_reaction=payload.reaction,
        manager_notified=notified,
    )

@router.post(
    "/{magic_token}/events/{event_id}/ask",
    response_model=AskRegulationQuestionOut,
    summary="Изолированный RAG-ответ клиенту по регламенту конкретного события или эскалация в Telegram",
    description=(
        "Принимает вопрос клиента по конкретному мероприятию пакета. Если ответ присутствует в регламенте, "
        "возвращает подтвержденный факт с цитатой. Если данных нет, фиксирует обращение в chat_messages "
        "и эскалирует вопрос в Telegram персональному менеджеру."
    ),
)
async def ask_event_regulation_question(
    magic_token: UUID,
    event_id: int,
    payload: AskRegulationQuestionIn,
    db: AsyncSessionDep,
) -> AskRegulationQuestionOut:
    """
    Вызывает изолированный RAG-сервис (D-09) для ответа на вопрос клиента по регламенту.
    """
    stmt = select(Selection).where(
        Selection.magic_token == magic_token,
        Selection.status == "published",
    )
    selection = None
    try:
        res = await db.execute(stmt)
        selection = res.scalar_one_or_none()
    except (SQLAlchemyError, OSError) as exc:
        logger.error("Ошибка БД при вопросе по витрине %s: %s", magic_token, exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="База данных временно недоступна",
        ) from exc

    if selection is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Витрина не найдена или еще не опубликована",
        )

    # Проверяем принадлежность мероприятия данной подборке
    item_stmt = (
        select(SelectionItem)
        .where(
            SelectionItem.selection_id == selection.id,
            SelectionItem.event_id == event_id,
        )
        .limit(1)
    )
    item_res = await db.execute(item_stmt)
    if item_res.scalars().first() is None:
        event_exists = await db.get(Event, event_id)
        if not event_exists:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Мероприятие не найдено")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Данное мероприятие не входит в указанную витрину",
        )

    try:
        return await ask_regulation_question(
            session=db,
            selection_id=selection.id,
            event_id=event_id,
            question_text=payload.question_text,
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except RAGUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Сервис ответов по регламенту временно недоступен. Попробуйте повторить запрос позже.",
        ) from exc

@router.post(
    "/{magic_token}/events/{event_id}/escalate-question",
    response_model=EscalateQuestionOut,
    summary="Осознанная эскалация неотвеченного вопроса клиента персональному куратору в Telegram",
    description=(
        "Клиент явно подтверждает желание передать вопрос персональному куратору. "
        "Сервис формирует Telegram-уведомление менеджеру, помечает сообщение в БД флагом needs_attention "
        "и возвращает статус успешной отправки."
    ),
)
async def escalate_question_to_manager(
    magic_token: UUID,
    event_id: int,
    payload: EscalateQuestionIn,
    db: AsyncSessionDep,
) -> EscalateQuestionOut:
    stmt = (
        select(Selection, Client, User)
        .join(Client, Selection.client_id == Client.id)
        .outerjoin(User, Client.manager_id == User.id)
        .where(
            Selection.magic_token == magic_token,
            Selection.status == "published",
        )
    )
    row = None
    try:
        res = await db.execute(stmt)
        row = res.first()
    except (SQLAlchemyError, OSError) as exc:
        logger.error("Ошибка БД при эскалации вопроса по витрине %s: %s", magic_token, exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="База данных временно недоступна",
        ) from exc

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Витрина не найдена или еще не опубликована",
        )

    selection, client, manager = row

    # Проверяем принадлежность мероприятия данной подборке (защита от IDOR)
    item_stmt = (
        select(SelectionItem)
        .where(
            SelectionItem.selection_id == selection.id,
            SelectionItem.event_id == event_id,
        )
        .limit(1)
    )
    item_res = await db.execute(item_stmt)
    if item_res.scalars().first() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Данное мероприятие не входит в указанную витрину",
        )

    event = await db.get(Event, event_id)
    if event is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Мероприятие не найдено")

    manager_chat_id = manager.telegram_chat_id if manager else None
    alert_html = format_escalation_alert(
        company_name=client.company_name,
        event_title=event.canonical_title,
        question_text=payload.question_text,
    )
    notified = await send_manager_alert(alert_html, chat_id=manager_chat_id)

    try:
        msg_stmt = (
            select(ChatMessage)
            .where(
                ChatMessage.selection_id == selection.id,
                ChatMessage.event_id == event_id,
                ChatMessage.sender_role == "client",
                ChatMessage.message_text == payload.question_text.strip(),
            )
            .order_by(ChatMessage.id.desc())
            .limit(1)
        )
        msg_res = await db.execute(msg_stmt)
        chat_msg = msg_res.scalar_one_or_none()
        if chat_msg is not None:
            chat_msg.needs_manager_attention = True
        else:
            chat_msg = ChatMessage(
                selection_id=selection.id,
                event_id=event_id,
                message_text=payload.question_text.strip(),
                sender_role="client",
                needs_manager_attention=True,
            )
            db.add(chat_msg)
        await db.commit()
    except (SQLAlchemyError, OSError) as exc:
        logger.warning("Не удалось обновить статус сообщения в chat_messages: %s", exc)

    return EscalateQuestionOut(
        event_id=event_id,
        question_text=payload.question_text,
        success=notified,
        message="Вопрос успешно передан персональному куратору.",
    )

