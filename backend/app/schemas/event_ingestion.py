from datetime import date
from typing import Literal, Self, TypeAlias

from pydantic import BaseModel, Field, field_validator, model_validator

from app.core.constants import normalize_city

CanonicalFAQQuestion: TypeAlias = Literal[
    "Что входит в рекомендованный тариф?",
    "Какие условия раннего бронирования и дедлайны?",
    "Формат участия и требования к спикеру",
]

_LEGACY_SEED_FAQ_ALIASES: dict[str, CanonicalFAQQuestion] = {
    "что входит в тариф?": "Что входит в рекомендованный тариф?",
    "условия early bird": "Какие условия раннего бронирования и дедлайны?",
    "требования к спикеру": "Формат участия и требования к спикеру",
}


class TariffExtracted(BaseModel):
    """Тариф участия в мероприятии, извлеченный из HTML или PDF."""

    tariff_name: str = Field(
        ...,
        description="Название пакета участия (например, 'Вездеход Бизнес', 'Пакет Спикер').",
    )
    participation_role: Literal["delegate", "speaker", "sponsor"] = Field(
        ..., description="Роль участника."
    )
    base_price: float | None = Field(
        None,
        description="Базовая цена в рублях с учетом НДС. Если цена 'По запросу' — строго null. Если участие бесплатное — 0.0.",
    )
    early_bird_price: float | None = Field(
        None,
        description="Льготная цена раннего бронирования с НДС. Если скидки нет — null.",
    )
    early_bird_deadline: date | None = Field(
        None,
        description="Дата окончания скидки Early Bird (YYYY-MM-DD). Если скидки нет — null.",
    )
    is_vat_included: bool = Field(
        default=True,
        description="True, если цена включает НДС (если в источнике указано '+ НДС 20%', прибавь 20% к числу и поставь True).",
    )
    included_benefits: str = Field(
        ..., description="Подробный перечень опций, входящих в тариф, одной строкой."
    )


class FAQCacheItem(BaseModel):
    """Готовый ответ на типовой вопрос для предзаполнения llm_cache согласно разделу 5.3 get_data.md."""

    question: CanonicalFAQQuestion = Field(
        ..., description="Канонический вопрос по регламенту мероприятия из FAQ_QUICK_CHIPS."
    )
    answer: str = Field(
        ...,
        description="Точный ответ на основе регламента. Если данных нет — напиши 'Уточняется у организаторов'.",
    )
    source_quote: str = Field(
        ..., description="Дословная цитата из регламента, подтверждающая ответ."
    )

    @field_validator("question", mode="before")
    @classmethod
    def canonicalize_seed_question(cls, value: object) -> object:
        """Приводит сокращенные ключи из seed_data.json / get_data.md к 3 каноническим вопросам витрины."""
        if not isinstance(value, str):
            return value
        cleaned = value.strip()
        mapped = _LEGACY_SEED_FAQ_ALIASES.get(cleaned.lower())
        return mapped if mapped is not None else cleaned


class EventIngestionSchema(BaseModel):
    """
    Целевая Pydantic v2 схема для финального извлечения мероприятия через Instructor LLM.
    Строго типизирована (date вместо str для интеграции с asyncpg/SQLAlchemy Date).
    """

    canonical_title: str = Field(
        ..., max_length=500, description="Официальное полное название мероприятия."
    )
    event_format: Literal[
        "forum", "conference", "roundtable", "business_breakfast", "session"
    ]
    city: str | None = Field(
        None,
        description="Город проведения в именительном падеже ('Москва', 'Казань'). Если мероприятие онлайн — строго null!",
    )
    is_online: bool = Field(
        ...,
        description="True для вебинаров и онлайн-конференций. Если city == null, is_online ОБЯЗАН быть True.",
    )
    venue: str | None = Field(
        None,
        description="Название площадки, отеля или экспоцентра (или 'Онлайн-платформа').",
    )
    start_date: date = Field(..., description="Дата начала проведения (строго YYYY-MM-DD).")
    end_date: date = Field(
        ...,
        description="Дата окончания проведения (строго YYYY-MM-DD, совпадает со start_date для однодневных).",
    )
    summary: str = Field(
        ...,
        min_length=250,
        max_length=850,
        description="Содержательное резюме мероприятия (250–850 символов): главные темы, формат и целевая аудитория.",
    )
    themes: list[str] = Field(
        ...,
        description="Массив ключевых тегов (например, ['строительство', 'девелопмент', 'КРТ', 'BIM']).",
    )
    full_regulation_markdown: str = Field(
        ...,
        description="Структурированный Markdown-регламент со всеми найденными деталями по разделам: 1. Цели, 2. Программа, 3. Аккредитация, 4. Спикерам, 5. Финансовые условия, 6. Логистика.",
    )
    tariffs: list[TariffExtracted] = Field(
        default_factory=list, description="Список найденных тарифов мероприятия."
    )
    faq_cache: list[FAQCacheItem] = Field(
        default_factory=list, description="Готовые ответы на 3 быстрых вопроса витрины."
    )
    missing_data_warnings: list[str] = Field(
        default_factory=list,
        description="Список важных сведений, которых НЕ оказалось в исходном тексте (для поля missing_data_warnings в БД).",
    )

    @model_validator(mode="after")
    def validate_event_ingestion(self) -> Self:
        """Гарантирует соблюдение CHECK (city IS NOT NULL OR is_online = true), нормализацию города и end_date >= start_date."""
        if self.city and self.city.strip().lower() not in ("онлайн", "online", "нет", "null"):
            self.city = normalize_city(self.city)
        else:
            self.city = None

        if not self.city:
            self.is_online = True

        self.end_date = max(self.end_date, self.start_date)
        return self
