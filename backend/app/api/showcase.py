from datetime import date
from uuid import UUID
from fastapi import APIRouter

from app.core.constants import FAQ_QUICK_CHIPS
from app.schemas.showcase import (
    ShowcaseViewOut,
    ShowcaseEventItemOut,
    ClientReactionIn,
    ClientReactionOut,
    AskRegulationQuestionIn,
    AskRegulationQuestionOut,
)

router = APIRouter(prefix="/api/public/s", tags=["Client Public Showcase (Magic Link)"])


@router.get(
    "/{magic_token}",
    response_model=ShowcaseViewOut,
    summary="Получение персональной витрины клиента по защищенной ссылке Magic Link",
    description=(
        "Публичный маршрут без авторизации. Доступ осуществляется строго по криптостойкому UUIDv4 токену. "
        "Возвращает сопроводительное письмо, сводную плашку бюджета, карточки мероприятий и чипсы быстрых вопросов FAQ."
    ),
)
async def get_public_showcase(magic_token: UUID) -> ShowcaseViewOut:
    """
    Эндпоинт загрузки данных клиентской витрины.
    Типизация magic_token: UUID гарантирует отсечение невалидных ссылок на уровне валидации FastAPI (код 422).
    В задаче D-10 замещается выборкой опубликованной витрины из БД по magic_token.
    """
    return ShowcaseViewOut(
        selection_id=10,
        company_name="ГК «Пионер»",
        manager_full_name="Анна Соколова",
        pitch_text=(
            "Игорь, добрый день! По итогам нашего разговора подготовили для ГК «Пионер» персональную "
            "программу участия на ноябрь–декабрь по темам КРТ и урбанистики в Москве и Санкт-Петербурге.\n\n"
            "В утвержденный пакет вошли 3 профильных мероприятия: спикерский слот на круглом столе «Ведомостей» "
            "и делегатское участие в закрытом завтраке «Коммерсантъ» и конференции ЕРЗ.РФ.\n\n"
            "Общая стоимость пакета составляет 285 000 ₽. При подтверждении участия до 15 ноября вы сохраняете "
            "скидку раннего бронирования (Early Bird) в размере 55 000 ₽."
        ),
        total_events_count=3,
        total_actual_price=285000.0,
        total_savings=55000.0,
        min_early_bird_deadline=date(2026, 11, 15),
        items=[
            ShowcaseEventItemOut(
                selection_item_id=1001,
                event_id=101,
                canonical_title="Круглый стол Ведомостей: Практика КРТ в мегаполисах 2026",
                event_format="roundtable",
                city="Москва",
                is_online=False,
                venue="Отель Континенталь, Тверская 22",
                start_date=date(2026, 11, 24),
                end_date=date(2026, 11, 24),
                summary="Закрытая дискуссия девелоперов и представителей Минстроя по механизмам комплексного развития территорий.",
                themes=["КРТ", "девелопмент", "регулирование"],
                tariff_name="Пакет «Спикер круглого стола»",
                participation_role="speaker",
                actual_price=135000.0,
                base_price=160000.0,
                early_bird_deadline=date(2026, 11, 15),
                savings=25000.0,
                included_benefits="Выступление 15 минут в основной сессии, упоминание в пост-релизе Ведомостей, 2 делегатских билета.",
                ai_rationale="Позволяет презентовать экспертизу ГК «Пионер» в сфере КРТ перед целевой аудиторией девелоперов.",
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
                venue="Гранд Отель Европа",
                start_date=date(2026, 12, 4),
                end_date=date(2026, 12, 4),
                summary="Камерный завтрак с ведущими урбанистами и архитекторами Санкт-Петербурга и Ленинградской области.",
                themes=["урбанистика", "мастер-планирование"],
                tariff_name="Участие делегата",
                participation_role="delegate",
                actual_price=75000.0,
                base_price=90000.0,
                early_bird_deadline=date(2026, 11, 20),
                savings=15000.0,
                included_benefits="Доступ ко всем дискуссиям, закрытый нетворкинг-завтрак с застройщиками, аналитические материалы.",
                ai_rationale="Камерный формат закрытого завтрака в СПб, прямой нетворкинг с градостроительным блоком.",
                client_reaction="pending",
                client_comment=None,
            ),
            ShowcaseEventItemOut(
                selection_item_id=1003,
                event_id=103,
                canonical_title="Конференция ЕРЗ.РФ: Тренды жилой недвижимости итоги года",
                event_format="conference",
                city="Москва",
                is_online=False,
                venue="ЦДП (Цифровое деловое пространство)",
                start_date=date(2026, 12, 11),
                end_date=date(2026, 12, 11),
                summary="Главная итоговая конференция девелоперов жилой недвижимости: аналитика продаж, проектное финансирование и тренды 2027.",
                themes=["жилая застройка", "ЕРЗ", "аналитика"],
                tariff_name="Делегатский билет (Офлайн + Видеозаписи)",
                participation_role="delegate",
                actual_price=75000.0,
                base_price=90000.0,
                early_bird_deadline=date(2026, 11, 25),
                savings=15000.0,
                included_benefits="Полный доступ к залам конференции, кофе-брейки, доступ к базе контактов участников.",
                ai_rationale="Ключевая площадка девелоперов РФ для подведения итогов года в рамках оставшегося лимита бюджета.",
                client_reaction="pending",
                client_comment=None,
            ),
        ],
        faq_quick_chips=list(FAQ_QUICK_CHIPS),
    )


@router.post(
    "/{magic_token}/items/{item_id}/react",
    response_model=ClientReactionOut,
    summary="Фиксация реакции клиента на карточку события и мгновенный пуш менеджеру в Telegram",
    description=(
        "Сохраняет реакцию клиента ('interested' 👍 или 'rejected' 👎) и опциональный комментарий, "
        "а также инициирует отправку уведомления персональному менеджеру."
    ),
)
async def react_to_showcase_item(
    magic_token: UUID,
    item_id: int,
    payload: ClientReactionIn,
) -> ClientReactionOut:
    """
    Эндпоинт реакции клиента на мероприятие.
    В задаче D-10 обновляет запись в selection_items и вызывает services/telegram.py.
    """
    return ClientReactionOut(
        selection_item_id=item_id,
        new_reaction=payload.reaction,
        manager_notified=True,
    )


@router.post(
    "/{magic_token}/events/{event_id}/ask",
    response_model=AskRegulationQuestionOut,
    summary="Изолированный RAG-ответ клиенту по регламенту конкретного события или эскалация в Telegram",
    description=(
        "Принимает вопрос клиента по конкретному мероприятию пакета. Если ответ присутствует в регламенте, "
        "возвращает подтвержденный факт с цитатой. Если данных нет, фиксирует обращение и эскалирует в Telegram менеджеру."
    ),
)
async def ask_event_regulation_question(
    magic_token: UUID,
    event_id: int,
    payload: AskRegulationQuestionIn,
) -> AskRegulationQuestionOut:
    """
    Эндпоинт интеллектуального чата по регламенту события.
    В задаче D-09 и D-10 сюда интегрируется модуль services/rag.py с context stuffing и llm_cache.
    """
    q_lower = payload.question_text.lower()

    # Сценарий эскалации: вопрос отсутствует в регламенте
    if any(keyword in q_lower for keyword in ["вертолет", "трансфер", "проживание", "отель", "перелет"]):
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

    # Сценарий точного ответа по регламенту (из кэша или контекста)
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
