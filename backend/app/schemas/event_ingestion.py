from datetime import date
from typing import List, Optional, Literal
from pydantic import BaseModel, Field, model_validator


class TariffExtracted(BaseModel):
    """Тариф участия в мероприятии, извлеченный из HTML или PDF."""
    tariff_name: str = Field(..., description="Название пакета участия (например, 'Вездеход Бизнес', 'Пакет Спикер').")
    participation_role: Literal["delegate", "speaker", "sponsor"] = Field(..., description="Роль участника.")
    base_price: Optional[float] = Field(
        None, description="Базовая цена в рублях с учетом НДС. Если цена 'По запросу' — строго null. Если участие бесплатное — 0.0."
    )
    early_bird_price: Optional[float] = Field(
        None, description="Льготная цена раннего бронирования с НДС. Если скидки нет — null."
    )
    early_bird_deadline: Optional[date] = Field(
        None, description="Дата окончания скидки Early Bird (YYYY-MM-DD). Если скидки нет — null."
    )
    is_vat_included: bool = Field(
        default=True, description="True, если цена включает НДС (если в источнике указано '+ НДС 20%', прибавь 20% к числу и поставь True)."
    )
    included_benefits: str = Field(..., description="Подробный перечень опций, входящих в тариф, одной строкой.")


class FAQCacheItem(BaseModel):
    """Готовый ответ на типовой вопрос для предзаполнения llm_cache."""
    question: str = Field(..., description="Вопрос по регламенту мероприятия (нормализуется к каноническому чипсу при совпадении).")
    answer: str = Field(..., description="Точный ответ на основе регламента. Если данных нет — напиши 'Уточняется у организаторов'.")
    source_quote: str = Field(..., description="Дословная цитата из регламента, подтверждающая ответ.")


    @model_validator(mode="before")
    @classmethod
    def normalize_question(cls, data):
        """Нормализует вариации вопросов к единому каноническому стандарту."""
        if isinstance(data, dict) and "question" in data:
            q = str(data["question"]).strip()
            aliases = {
                "Что входит в тариф?": "Что входит в рекомендованный тариф?",
                "Что входит в рекомендованный тариф?": "Что входит в рекомендованный тариф?",
                "Условия Early Bird": "Какие условия раннего бронирования и дедлайны?",
                "Какие условия раннего бронирования и дедлайны?": "Какие условия раннего бронирования и дедлайны?",
                "Требования к спикеру": "Формат участия и требования к спикеру",
                "Формат участия и требования к спикеру": "Формат участия и требования к спикеру",
            }
            if q in aliases:
                data["question"] = aliases[q]
            else:
                q_lower = q.lower()
                if "входит в" in q_lower or "тариф" in q_lower:
                    data["question"] = "Что входит в рекомендованный тариф?"
                elif "early bird" in q_lower or "ранн" in q_lower or "бронирован" in q_lower:
                    data["question"] = "Какие условия раннего бронирования и дедлайны?"
                elif "спикер" in q_lower or "доклад" in q_lower:
                    data["question"] = "Формат участия и требования к спикеру"
        return data


class EventIngestionSchema(BaseModel):
    """
    Целевая Pydantic v2 схема для финального извлечения мероприятия через Instructor LLM.
    Строго типизирована (date вместо str для интеграции с asyncpg/SQLAlchemy Date).
    """
    canonical_title: str = Field(..., max_length=500, description="Официальное полное название мероприятия.")
    event_format: Literal["forum", "conference", "roundtable", "business_breakfast", "session"]
    city: Optional[str] = Field(
        None, description="Город проведения в именительном падеже ('Москва', 'Казань'). Если мероприятие онлайн — строго null!"
    )
    is_online: bool = Field(
        ..., description="True для вебинаров и онлайн-конференций. Если city == null, is_online ОБЯЗАН быть True."
    )
    venue: Optional[str] = Field(None, description="Название площадки, отеля или экспоцентра (или 'Онлайн-платформа').")
    start_date: date = Field(..., description="Дата начала проведения (строго YYYY-MM-DD).")
    end_date: date = Field(..., description="Дата окончания проведения (строго YYYY-MM-DD, совпадает со start_date для однодневных).")
    summary: str = Field(
        ..., min_length=100, max_length=1500,
        description="Содержательное резюме мероприятия (300–800 символов): главные темы, формат и целевая аудитория."
    )
    themes: List[str] = Field(..., description="Массив ключевых тегов (например, ['строительство', 'девелопмент', 'КРТ', 'BIM']).")
    full_regulation_markdown: str = Field(
        ..., description="Структурированный Markdown-регламент со всеми найденными деталями по разделам: 1. Цели, 2. Программа, 3. Аккредитация, 4. Спикерам, 5. Финансовые условия, 6. Логистика."
    )
    tariffs: List[TariffExtracted] = Field(default_factory=list, description="Список найденных тарифов мероприятия.")
    faq_cache: List[FAQCacheItem] = Field(default_factory=list, description="Готовые ответы на 3 быстрых вопроса витрины.")
    missing_data_warnings: List[str] = Field(
        default_factory=list,
        description="Список важных сведений, которых НЕ оказалось в исходном тексте (для поля missing_data_warnings в БД)."
    )

    @model_validator(mode="after")
    def validate_event_ingestion(self):
        """Гарантирует соблюдение CHECK (city IS NOT NULL OR is_online = true) и end_date >= start_date."""
        if not self.city or (isinstance(self.city, str) and self.city.strip().lower() in ("онлайн", "online", "нет", "null")):
            self.city = None
            self.is_online = True
        if self.end_date < self.start_date:
            self.end_date = self.start_date
        return self

