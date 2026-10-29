from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_async_session
from app.models.models import Selection, SelectionItem, Client, User, Event, EventTariff
from app.schemas.showcase import (
    ShowcaseViewOut, ShowcaseEventItemOut,
    ClientReactionIn, ClientReactionOut,
    AskRegulationQuestionIn, AskRegulationQuestionOut
)
from app.services.rag import ask_regulation_question
from app.services.telegram import send_manager_alert

router = APIRouter(prefix="/api/public/s", tags=["Client Public Showcase"])

@router.get("/{magic_token}", response_model=ShowcaseViewOut)
async def get_public_showcase(magic_token: UUID, db: AsyncSession = Depends(get_async_session)):
    # 1. Ищем опубликованную подборку
    stmt = select(Selection).where(Selection.magic_token == magic_token, Selection.status == "published")
    result = await db.execute(stmt)
    selection = result.scalar_one_or_none()
    if not selection:
        raise HTTPException(status_code=404, detail="Витрина не найдена или еще не опубликована")

    # 2. Достаем клиента и менеджера
    client = await db.get(Client, selection.client_id)
    manager = await db.get(User, client.manager_id) if client else None

    # 3. Достаем утвержденные мероприятия (bundle_group=1)
    items_stmt = select(SelectionItem).where(SelectionItem.selection_id == selection.id)
    items_res = await db.execute(items_stmt)
    items = items_res.scalars().all()

    showcase_items = []
    total_actual = 0.0
    total_savings = 0.0
    earliest_deadline = None

    for item in items:
        event = await db.get(Event, item.event_id)
        tariff = await db.get(EventTariff, item.recommended_tariff_id)
        
        if not event or not tariff:
            continue

        # Пересчитываем актуальную цену для отображения
        base = float(tariff.base_price) if tariff.base_price is not None else None
        eb = float(tariff.early_bird_price) if tariff.early_bird_price is not None else None
        import datetime
        today = datetime.date.today()
        
        actual = base
        savings = 0.0
        if base is not None and eb is not None and tariff.early_bird_deadline and tariff.early_bird_deadline >= today:
            actual = eb
            savings = base - eb

        if actual:
            total_actual += actual
        total_savings += savings
        if savings > 0 and tariff.early_bird_deadline:
            if not earliest_deadline or tariff.early_bird_deadline < earliest_deadline:
                earliest_deadline = tariff.early_bird_deadline

        showcase_items.append(ShowcaseEventItemOut(
            selection_item_id=item.id,
            event_id=event.id,
            canonical_title=event.canonical_title,
            event_format=event.event_format,
            city=event.city,
            is_online=event.is_online,
            venue=event.venue,
            start_date=event.start_date,
            end_date=event.end_date,
            summary=event.summary,
            themes=event.themes or [],
            tariff_name=tariff.tariff_name,
            participation_role=tariff.participation_role,
            actual_price=actual,
            base_price=base,
            early_bird_deadline=tariff.early_bird_deadline,
            savings=savings,
            included_benefits=tariff.included_benefits,
            ai_rationale=item.ai_rationale or "",
            client_reaction=item.client_reaction,
            client_comment=item.client_comment
        ))

    return ShowcaseViewOut(
        selection_id=selection.id,
        company_name=client.company_name if client else "Уважаемый клиент",
        manager_full_name=manager.full_name if manager else "Менеджер СКАРТ",
        pitch_text=selection.generated_pitch_text or "Здравствуйте! Вот ваша персональная подборка.",
        total_events_count=len(showcase_items),
        total_actual_price=total_actual,
        total_savings=total_savings,
        min_early_bird_deadline=earliest_deadline,
        items=showcase_items
    )


@router.post("/{magic_token}/items/{item_id}/react", response_model=ClientReactionOut)
async def react_to_showcase_item(
    magic_token: UUID, item_id: int, payload: ClientReactionIn, db: AsyncSession = Depends(get_async_session)
):
    item = await db.get(SelectionItem, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Элемент подборки не найден")

    item.client_reaction = payload.reaction
    item.client_comment = payload.comment
    await db.commit()

    emoji = "👍 Интересно" if payload.reaction == "interested" else "👎 Заменить"
    event = await db.get(Event, item.event_id)
    alert_text = f"🔔 Клиент нажал '{emoji}' на мероприятие: {event.canonical_title if event else item.event_id}"
    if payload.comment:
        alert_text += f"\n💬 Комментарий: {payload.comment}"
    
    await send_manager_alert(alert_text)

    return ClientReactionOut(
        selection_item_id=item_id,
        new_reaction=payload.reaction,
        manager_notified=True
    )


@router.post("/{magic_token}/events/{event_id}/ask", response_model=AskRegulationQuestionOut)
async def ask_event_regulation_question(
    magic_token: UUID, event_id: int, payload: AskRegulationQuestionIn, db: AsyncSession = Depends(get_async_session)
):
    # 1. Ищем подборку по токену
    stmt = select(Selection).where(Selection.magic_token == magic_token)
    res = await db.execute(stmt)
    selection = res.scalar_one_or_none()
    if not selection:
        raise HTTPException(status_code=404, detail="Подборка не найдена")

    # 2. Вызываем наш RAG-сервис из D-09
    rag_response = await ask_regulation_question(
        session=db,
        selection_id=selection.id,
        event_id=event_id,
        question_text=payload.question_text
    )

    # 3. Если ответ не найден, отправляем алерт менеджеру
    if rag_response.escalated_to_telegram:
        event = await db.get(Event, event_id)
        alert_text = (
            f"🔔 <b>Клиент задал вопрос, на который нет ответа в регламенте!</b>\n"
            f"Мероприятие: {event.canonical_title if event else event_id}\n"
            f"Вопрос: {payload.question_text}\n"
            f"Ответьте клиенту в кабинете или напишите ему напрямую."
        )
        await send_manager_alert(alert_text)

    return rag_response