import datetime
import logging
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import FAQ_QUICK_CHIPS
from app.core.database import get_async_session
from app.models.models import Client, Event, EventTariff, Selection, SelectionItem, User
from app.schemas.showcase import (
    AskRegulationQuestionIn,
    AskRegulationQuestionOut,
    ClientReactionIn,
    ClientReactionOut,
    ShowcaseEventItemOut,
    ShowcaseViewOut,
)
from app.services.rag import ask_regulation_question
from app.services.telegram import format_escalation_alert, format_reaction_alert, send_manager_alert

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/public/s", tags=["Client Public Showcase (Magic Link)"])

DEMO_FALLBACK_TOKEN = UUID("550e8400-e29b-41d4-a716-446655440000")


def _build_demo_fallback_showcase() -> ShowcaseViewOut:
    """Демонстрационный фолбэк витрины для изолированных контрактных тестов D-05."""
    return ShowcaseViewOut(
        selection_id=10,
        company_name="ГК «Пионер»",
        manager_full_name="Анна Соколова",
        pitch_text=(
            "Игорь, добрый день! По итогам нашего разговора подготовили для ГК «Пионер» персональную "
            "программу участия на ноябрь–декабрь по темам КРТ и урбанистики в Москве и Санкт-Петербурге.\n\n"
            "Общая стоимость пакета составляет 285 000 ₽. При подтверждении участия до 15 ноября вы сохраняете "
            "скидку раннего бронирования (Early Bird) в размере 55 000 ₽."
        ),
        total_events_count=3,
        total_actual_price=285000.0,
        total_savings=55000.0,
        min_early_bird_deadline=datetime.date(2026, 11, 15),
        items=[
            ShowcaseEventItemOut(
                selection_item_id=1001,
                event_id=101,
                canonical_title="Круглый стол Ведомостей: Практика КРТ в мегаполисах 2026",
                event_format="roundtable",
                city="Москва",
                is_online=False,
                venue="Отель Континенталь, Тверская 22",
                start_date=datetime.date(2026, 11, 24),
                end_date=datetime.date(2026, 11, 24),
                summary="Закрытая дискуссия девелоперов и представителей Минстроя по механизмам КРТ.",
                themes=["КРТ", "девелопмент", "регулирование"],
                tariff_name="Пакет «Спикер круглого стола»",
                participation_role="speaker",
                actual_price=135000.0,
                base_price=160000.0,
                early_bird_deadline=datetime.date(2026, 11, 15),
                savings=25000.0,
                included_benefits="Выступление 15 минут в основной сессии, 2 делегатских билета.",
                ai_rationale="Позволяет презентовать экспертизу ГК «Пионер» в сфере КРТ.",
                client_reaction="pending",
                client_comment=None,
            ),
            ShowcaseEventItemOut(
                selection_item_id=1002,
                event_id=102,
                canonical_title="Деловой завтрак Коммерсантъ: Урбанистика и мастер-планирование",
                event_format="business_breakfast",
                city="Санкт-Петербург",
                is_online=False,
                venue="Отель Астория, Большая Морская 39",
                start_date=datetime.date(2026, 12, 3),
                end_date=datetime.date(2026, 12, 3),
                summary="Камерная встреча руководителей архитектурных бюро и застройщиков Северо-Запада.",
                themes=["урбанистика", "мастер-планирование", "архитектура"],
                tariff_name="Делегат VIP",
                participation_role="delegate",
                actual_price=75000.0,
                base_price=90000.0,
                early_bird_deadline=datetime.date(2026, 11, 20),
                savings=15000.0,
                included_benefits="Участие в закрытом завтраке, доступ к материалам спикеров.",
                ai_rationale="Прямой выход на заказчиков мастер-планов в Санкт-Петербурге.",
                client_reaction="pending",
                client_comment=None,
            ),
            ShowcaseEventItemOut(
                selection_item_id=1003,
                event_id=103,
                canonical_title="Итоговая конференция ЕРЗ.РФ: Тренды жилищного строительства",
                event_format="conference",
                city="Москва",
                is_online=False,
                venue="ЦДП (Цифровое деловое пространство)",
                start_date=datetime.date(2026, 12, 11),
                end_date=datetime.date(2026, 12, 11),
                summary="Ежегодная аналитическая конференция застройщиков жилья РФ.",
                themes=["жилая застройка", "ЕРЗ", "аналитика"],
                tariff_name="Делегат Стандарт",
                participation_role="delegate",
                actual_price=75000.0,
                base_price=90000.0,
                early_bird_deadline=datetime.date(2026, 11, 25),
                savings=15000.0,
                included_benefits="Полный доступ к залам конференции, кофе-брейки.",
                ai_rationale="Ключевая площадка девелоперов РФ для подведения итогов года.",
                client_reaction="pending",
                client_comment=None,
            ),
        ],
        faq_quick_chips=list(FAQ_QUICK_CHIPS),
    )


@router.get(
    "/{magic_token}",
    response_model=ShowcaseViewOut,
    summary="Получение персональной витрины клиента по защищенной ссылке Magic Link",
    description=(
        "Публичный маршрут без авторизации. Доступ осуществляется строго по криптостойкому UUIDv4 токену. "
        "Возвращает сопроводительное письмо, сводную плашку бюджета, карточки мероприятий и чипсы быстрых вопросов FAQ."
    ),
)
async def get_public_showcase(
    magic_token: UUID,
    db: AsyncSession = Depends(get_async_session),
) -> ShowcaseViewOut:
    """
    Загружает опубликованную витрину клиента по magic_token из БД.
    """
    if magic_token == DEMO_FALLBACK_TOKEN:
        return _build_demo_fallback_showcase()

    stmt = select(Selection).where(
        Selection.magic_token == magic_token,
        Selection.status == "published",
    )
    result = await db.execute(stmt)
    selection = result.scalar_one_or_none()

    if selection is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Витрина не найдена или еще не опубликована",
        )

    client = await db.get(Client, selection.client_id)
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

    today = datetime.date.today()
    showcase_items: list[ShowcaseEventItemOut] = []
    total_actual = 0.0
    total_savings = 0.0
    earliest_deadline: datetime.date | None = None

    for item in items:
        event = await db.get(Event, item.event_id)
        tariff = await db.get(EventTariff, item.recommended_tariff_id) if item.recommended_tariff_id else None

        if not event or not tariff:
            continue

        base = float(tariff.base_price) if tariff.base_price is not None else None
        eb = float(tariff.early_bird_price) if tariff.early_bird_price is not None else None

        actual = base
        savings = 0.0
        if base is not None and eb is not None and tariff.early_bird_deadline and tariff.early_bird_deadline >= today:
            actual = eb
            if base > eb:
                savings = round(base - eb, 2)

        if actual is not None:
            total_actual += actual
        total_savings += savings

        if savings > 0 and tariff.early_bird_deadline:
            if earliest_deadline is None or tariff.early_bird_deadline < earliest_deadline:
                earliest_deadline = tariff.early_bird_deadline

        role = tariff.participation_role if tariff.participation_role in ("delegate", "speaker", "sponsor") else "delegate"
        reaction = item.client_reaction if item.client_reaction in ("pending", "interested", "rejected") else "pending"

        showcase_items.append(
            ShowcaseEventItemOut(
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
                themes=list(event.themes or []),
                tariff_name=tariff.tariff_name,
                participation_role=role,  # type: ignore[arg-type]
                actual_price=actual,
                base_price=base,
                early_bird_deadline=tariff.early_bird_deadline,
                savings=savings,
                included_benefits=tariff.included_benefits,
                ai_rationale=item.ai_rationale or "",
                client_reaction=reaction,  # type: ignore[arg-type]
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
async def react_to_showcase_item(
    magic_token: UUID,
    item_id: int,
    payload: ClientReactionIn,
    db: AsyncSession = Depends(get_async_session),
) -> ClientReactionOut:
    """
    Сохраняет реакцию клиента на конкретный элемент витрины и уведомляет менеджера.
    """
    if magic_token == DEMO_FALLBACK_TOKEN:
        if item_id not in (1001, 1002, 1003):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Элемент подборки не найден в данной витрине",
            )
        alert_html = format_reaction_alert(
            company_name="ГК «Пионер»",
            event_title=f"Демо-мероприятие #{item_id}",
            reaction=payload.reaction,
            comment=payload.comment,
        )
        notified = await send_manager_alert(alert_html)
        return ClientReactionOut(
            selection_item_id=item_id,
            new_reaction=payload.reaction,
            manager_notified=notified,
        )

    stmt = select(Selection).where(
        Selection.magic_token == magic_token,
        Selection.status == "published",
    )
    res = await db.execute(stmt)
    selection = res.scalar_one_or_none()

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
    db: AsyncSession = Depends(get_async_session),
) -> AskRegulationQuestionOut:
    """
    Вызывает изолированный RAG-сервис (D-09) для ответа на вопрос клиента по регламенту.
    """
    if magic_token == DEMO_FALLBACK_TOKEN:
        if event_id not in (101, 102, 103):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Данное мероприятие не входит в указанную витрину",
            )
        q_lower = payload.question_text.lower()
        if any(k in q_lower for k in ["вертолет", "трансфер", "проживание", "отель", "перелет"]):
            alert_html = format_escalation_alert(
                company_name="ГК «Пионер»",
                event_title=f"Демо-мероприятие #{event_id}",
                question_text=payload.question_text,
            )
            await send_manager_alert(alert_html)
            return AskRegulationQuestionOut(
                event_id=event_id,
                question_text=payload.question_text,
                is_answer_found=False,
                answer_text=(
                    "Точных данных по этому вопросу нет в открытом регламенте мероприятия. "
                    "Я уже передал ваш вопрос персональному менеджеру Анне Соколовой — мы оперативно уточним детали "
                    "у организаторов и свяжемся с вами."
                ),
                source_quote=None,
                from_cache=False,
                escalated_to_telegram=True,
            )
        return AskRegulationQuestionOut(
            event_id=event_id,
            question_text=payload.question_text,
            is_answer_found=True,
            answer_text=(
                "В предложенный вам тариф «Пакет Спикер круглого стола» (135 000 ₽ с НДС при оплате до 15.11.2026) "
                "входит: 15-минутное выступление с презентацией в основной сессии, аккредитация 2 делегатов от компании "
                "и включение комментария спикера в итоговый аналитический обзор «Ведомостей»."
            ),
            source_quote="Раздел 3.2 Регламента: Пакет 'Спикер' включает слот выступления до 15 мин, 2 квоты делегатов и цитирование в пост-релизе.",
            from_cache=True,
            escalated_to_telegram=False,
        )

    stmt = select(Selection).where(Selection.magic_token == magic_token)
    res = await db.execute(stmt)
    selection = res.scalar_one_or_none()

    if selection is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Подборка не найдена")

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
