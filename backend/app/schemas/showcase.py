from datetime import date
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


# ============================================================================
# СХЕМЫ ПУБЛИЧНОЙ ИНТЕРАКТИВНОЙ ВИТРИНЫ КЛИЕНТА (/api/public/s/{magic_token})
# ============================================================================

class ShowcaseEventItemOut(BaseModel):
    """Карточка мероприятия на интерактивной витрине клиента."""
    model_config = ConfigDict(from_attributes=True)

    selection_item_id: int = Field(
        ...,
        description="ID строки в таблице selection_items (передается при отправке реакции)"
    )
    event_id: int = Field(..., description="ID события")
    canonical_title: str = Field(..., description="Официальное название мероприятия")
    event_format: str = Field(..., description="Формат: roundtable, business_breakfast, forum, conference, session")
    city: str | None = Field(None, description="Город проведения в именительном падеже (None для онлайн)")
    is_online: bool = Field(False, description="Признак онлайн-формата (вебинар, трансляция)")
    venue: str | None = Field(None, description="Площадка, отель или онлайн-платформа")
    start_date: date = Field(..., description="Дата начала проведения (YYYY-MM-DD)")
    end_date: date = Field(..., description="Дата окончания проведения (YYYY-MM-DD)")
    summary: str = Field(..., description="Краткое саммари для карточки (2-3 предложения о ключевых темах)")
    themes: list[str] = Field(default_factory=list, description="Список отраслевых тем")

    # Параметры рекомендованного тарифа
    tariff_name: str = Field(..., description="Название рекомендованного тарифа")
    participation_role: Literal["delegate", "speaker", "sponsor"] = Field(..., description="Роль участия")
    actual_price: float | None = Field(None, description="Актуальная стоимость с НДС (None = По запросу)")
    base_price: float | None = Field(None, description="Базовая стоимость без скидок")
    early_bird_deadline: date | None = Field(None, description="Дата окончания скидки Early Bird")
    savings: float = Field(default=0.0, description="Сумма экономии в рублях")
    included_benefits: str | None = Field(None, description="Что входит в пакет участия")

    # ИИ-обоснование и текущая реакция клиента
    ai_rationale: str = Field(
        ...,
        description="Персональное пояснение ИИ, какую задачу компании решает это мероприятие"
    )
    client_reaction: Literal["pending", "interested", "rejected"] = Field(
        default="pending",
        description="Статус реакции клиента: ожидает ответа, интересно, или отклонено"
    )
    client_comment: str | None = Field(None, description="Текстовый комментарий клиента к реакции")


class ShowcaseViewOut(BaseModel):
    """
    Полная структура данных для отрисовки витрины клиента по ссылке /s/{magic_token}.
    Включает приветственное письмо, сводную плашку бюджета, карточки и чипсы FAQ.
    """
    selection_id: int = Field(..., description="ID подборки")
    company_name: str = Field(..., description="Название компании клиента")
    manager_full_name: str = Field(..., description="ФИО персонального менеджера сопровождения")
    pitch_text: str = Field(..., description="Приветственное сопроводительное письмо от менеджера")

    # Сводные показатели утвержденного пакета
    total_events_count: int = Field(..., description="Количество мероприятий в пакете")
    total_actual_price: float = Field(..., description="Итоговая сумма пакета к оплате")
    total_savings: float = Field(..., description="Суммарная экономия клиента при своевременном бронировании")
    min_early_bird_deadline: date | None = Field(
        None,
        description="Ближайшая дата дедлайна, до которой необходимо согласовать пакет"
    )

    items: list[ShowcaseEventItemOut] = Field(..., description="Мероприятия утвержденного пакета")
    faq_quick_chips: list[str] = Field(
        default_factory=lambda: [
            "Что входит в рекомендованный тариф?",
            "Какие условия раннего бронирования и дедлайны?",
            "Формат участия и требования к спикеру"
        ],
        description="3 фиксированные кнопки быстрых вопросов для выдвижной панели чата"
    )


class ClientReactionIn(BaseModel):
    """Входные данные при клике клиентом кнопки 'Интересно' или 'Заменить'."""
    reaction: Literal["interested", "rejected"] = Field(
        ...,
        description="Реакция: interested (Интересно) или rejected (Заменить/Отклонить)"
    )
    comment: str | None = Field(
        None,
        description="Опциональный комментарий клиента (например: 'В эти даты командировка, подберите замену')"
    )


class ClientReactionOut(BaseModel):
    """Результат сохранения реакции клиента."""
    selection_item_id: int = Field(..., description="ID элемента подборки")
    new_reaction: Literal["interested", "rejected"] = Field(..., description="Зафиксированная реакция")
    manager_notified: bool = Field(
        ...,
        description="True, если уведомление о реакции успешно отправлено менеджеру в Telegram"
    )


class AskRegulationQuestionIn(BaseModel):
    """Вопрос клиента по регламенту конкретного мероприятия."""
    question_text: str = Field(
        ...,
        min_length=3,
        max_length=500,
        description="Текст вопроса клиента или текст выбранного быстрого чипса",
        examples=["Что входит в рекомендованный тариф?"]
    )


class AskRegulationQuestionOut(BaseModel):
    """Ответ ИИ-ассистента по регламенту события (изолированный RAG)."""
    event_id: int = Field(..., description="ID мероприятия")
    question_text: str = Field(..., description="Исходный вопрос клиента")
    is_answer_found: bool = Field(
        ...,
        description="True — точный ответ найден в тексте программы; False — информации нет, вопрос эскалирован менеджеру"
    )
    answer_text: str = Field(
        ...,
        description="Сформулированный ответ ИИ по регламенту либо вежливое уведомление о передаче вопроса менеджеру"
    )
    source_quote: str | None = Field(
        None,
        description="Цитата из официального регламента, подтверждающая ответ (защита от галлюцинаций)"
    )
    from_cache: bool = Field(
        default=False,
        description="True, если ответ получен мгновенно из PostgreSQL таблицы llm_cache"
    )
    escalated_to_telegram: bool = Field(
        default=False,
        description="True, если неотвеченный вопрос отправлен в виде пуша в Telegram менеджеру"
    )
