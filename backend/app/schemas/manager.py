from datetime import date
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field


# ============================================================================
# 1. СХЕМЫ ДАШБОРДА МЕНЕДЖЕРА (GET /api/manager/clients)
# ============================================================================

class BurningDeadlineOut(BaseModel):
    """Информация о горящем дедлайне со скидкой Early Bird (< 72 часов)."""
    event_id: int = Field(..., description="ID мероприятия в БД")
    event_title: str = Field(..., description="Каноническое название мероприятия")
    early_bird_deadline: date = Field(..., description="Дата сгорания скидки Early Bird")
    potential_savings: float = Field(..., description="Сумма потери скидки в рублях при пропуске дедлайна")


class ClientSummaryOut(BaseModel):
    """Сводная карточка клиента в сайдбаре менеджера."""
    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., description="ID клиента")
    company_name: str = Field(..., description="Название компании клиента (например, ГК Пионер)")
    contact_person: str | None = Field(None, description="Контактное лицо клиента")
    raw_manager_notes: str = Field(..., description="Последний сохраненный конспект созвона")
    latest_selection_id: int | None = Field(None, description="ID последней созданной подборки")
    latest_selection_status: Literal["draft", "published"] | None = Field(
        None, description="Статус подборки: черновик или опубликована"
    )
    magic_token: UUID | None = Field(None, description="UUID токен витрины, если подборка опубликована")


class ManagerDashboardOut(BaseModel):
    """Ответ дашборда менеджера: клиенты и горящие дедлайны."""
    clients: list[ClientSummaryOut] = Field(..., description="Список закрепленных клиентов")
    burning_deadlines: list[BurningDeadlineOut] = Field(
        default_factory=list,
        description="Алерты: мероприятия, у которых скидка Early Bird сгорает менее чем через 72 часа"
    )


# ============================================================================
# 2. СХЕМЫ ИИ-ПРОФИЛИРОВАНИЯ И МАТЧИНГА (POST /api/manager/clients/{id}/match)
# ============================================================================

class ClientQueryExtracted(BaseModel):
    """
    Схема извлечения параметров из свободной заметки менеджера (NER-профайлер).
    Полностью совпадает с контрактом модуля profiler.py.
    """
    cities: list[str] = Field(default_factory=list, description="Канонические названия городов проведения")
    include_online: bool = Field(default=True, description="Включать ли онлайн-мероприятия (вебинары, трансляции)")
    date_from: date | None = Field(None, description="Начало периода поиска (YYYY-MM-DD)")
    date_to: date | None = Field(None, description="Конец периода поиска (YYYY-MM-DD)")
    total_budget_max: float = Field(..., description="Общий потолок бюджета на всю серию в рублях")
    target_events_count: int = Field(default=3, ge=1, le=10, description="Желаемое число событий в пакете")
    preferred_formats: list[Literal["roundtable", "business_breakfast", "forum", "conference", "session"]] = Field(
        default_factory=list,
        description="Предпочтительные форматы деловых событий"
    )
    required_roles: list[Literal["delegate", "speaker", "sponsor"]] = Field(
        default_factory=lambda: ["delegate"],
        description="Требуемые форматы участия"
    )
    min_speaker_events: int = Field(
        default=0, ge=0, le=5,
        description="На скольких событиях минимум клиент хочет выступить спикером"
    )
    themes_keywords: list[str] = Field(
        default_factory=list,
        description="Ключевые отраслевые теги (КРТ, ИЖС, урбанистика, цифровизация)"
    )
    semantic_search_query: str = Field(
        ...,
        description="Развернутый поисковый запрос для векторного поиска (pgvector cosine ops)"
    )


class MatchRequestIn(BaseModel):
    """Входной запрос на подбор пакетов деловых мероприятий."""
    raw_manager_notes: str = Field(
        ...,
        min_length=10,
        description="Сырой текст заметки менеджера после звонка с клиентом",
        examples=[
            "Созвонились с ГК Пионер. Ищут на ноябрь-декабрь в Москве или СПб 3 мероприятия по КРТ и урбанистике. "
            "Хотя бы на одном хотят выступить спикером. Общий бюджет на всё — 400 000 руб."
        ]
    )
    override_profile: ClientQueryExtracted | None = Field(
        None,
        description="Передается, если менеджер скорректировал распознанные теги в UI и нажал 'Пересобрать пакеты'"
    )


class TariffOptionOut(BaseModel):
    """Тариф участия в мероприятии."""
    model_config = ConfigDict(from_attributes=True)

    tariff_id: int = Field(..., description="ID тарифа в таблице event_tariffs")
    tariff_name: str = Field(..., description="Название тарифа (например, 'Пакет Спикер сессии')")
    participation_role: Literal["delegate", "speaker", "sponsor"] = Field(..., description="Роль участия")
    base_price: float | None = Field(None, description="Базовая цена с НДС (None = По запросу)")
    early_bird_price: float | None = Field(None, description="Цена Early Bird с НДС")
    early_bird_deadline: date | None = Field(None, description="Дедлайн действия цены раннего бронирования")
    actual_price: float | None = Field(None, description="Актуальная цена на сегодня с учетом даты Early Bird")
    savings: float = Field(default=0.0, description="Экономия в рублях при бронировании до дедлайна Early Bird")
    included_benefits: str | None = Field(None, description="Что включено в тариф (билеты, нетворкинг, опции)")


class BundleEventItemOut(BaseModel):
    """Мероприятие, предложенное в составе пакета."""
    event_id: int = Field(..., description="ID события в таблице events")
    canonical_title: str = Field(..., description="Официальное название форума/сессии")
    event_format: Literal["roundtable", "business_breakfast", "forum", "conference", "session"] = Field(
        ..., description="Формат проведения"
    )
    city: str | None = Field(None, description="Город проведения в именительном падеже (None, если строго онлайн)")
    is_online: bool = Field(False, description="Признак онлайн-формата мероприятия")
    venue: str | None = Field(None, description="Площадка, отель, адрес или платформа трансляции")
    start_date: date = Field(..., description="Дата начала (YYYY-MM-DD)")
    end_date: date = Field(..., description="Дата окончания (YYYY-MM-DD)")
    themes: list[str] = Field(default_factory=list, description="Список отраслевых тегов")
    recommended_tariff: TariffOptionOut = Field(..., description="Тариф, рассчитанный алгоритмом в рамках бюджета")
    available_tariffs: list[TariffOptionOut] = Field(
        default_factory=list,
        description="Все тарифы события, позволяющие менеджеру вручную переключить роль в UI"
    )
    ai_rationale: str = Field(
        ...,
        description="Обоснование ИИ, какую конкретно бизнес-задачу клиента решает данное мероприятие"
    )


class BundleVariantOut(BaseModel):
    """Один из сгенерированных вариантов пакета мероприятий."""
    bundle_group: int = Field(
        ...,
        description="1 — Максимальное совпадение по темам (RRF), 2 — Оптимальный по экономии бюджета"
    )
    bundle_title: str = Field(..., description="Заголовок пакета для вкладки в интерфейсе менеджера")
    items: list[BundleEventItemOut] = Field(..., description="Список мероприятий пакета")
    total_actual_price: float = Field(..., description="Итоговая актуальная стоимость всего пакета в рублях")
    total_base_price: float = Field(..., description="Стоимость пакета без учета скидок раннего бронирования")
    total_savings: float = Field(..., description="Суммарная экономия по скидкам Early Bird в рублях")
    earliest_deadline: date | None = Field(None, description="Ближайшая дата сгорания скидки среди событий пакета")
    is_over_budget_tolerance: bool = Field(
        default=False,
        description="True, если пакет превышает бюджет клиента в пределах допустимых +10% (требует согласования)"
    )


class MatchResponseOut(BaseModel):
    """Результат подбора: извлеченный профиль, два варианта пакета, бонусный слот и черновик КП."""
    selection_id: int = Field(..., description="ID созданного черновика подборки в таблице selections")
    client_id: int = Field(..., description="ID клиента")
    extracted_profile: ClientQueryExtracted = Field(..., description="Извлеченный из заметки профиль потребностей")
    bundle_variants: list[BundleVariantOut] = Field(
        ..., description="Два взаимоисключающих варианта пакета (Вариант №1 и Вариант №2)"
    )
    bonus_on_request_items: list[BundleEventItemOut] = Field(
        default_factory=list,
        description="Бонусный слот: профильные мероприятия с тарифом 'Цена по запросу' (base_price IS NULL)"
    )
    generated_pitch_text: str = Field(
        ...,
        description="Сгенерированный ИИ текст приветственного КП с подтвержденными Python-цифрами"
    )


# ============================================================================
# 3. СХЕМЫ ПУБЛИКАЦИИ ВИТРИНЫ (PUT /api/manager/selections/{id}/publish)
# ============================================================================

class SelectedEventTariffPairIn(BaseModel):
    """Пара (мероприятие, выбранный тариф), утвержденная менеджером для публикации."""
    event_id: int = Field(..., description="ID события")
    tariff_id: int = Field(..., description="ID выбранного тарифа")
    ai_rationale: str | None = Field(None, description="Отредактированное менеджером обоснование")


class PublishSelectionIn(BaseModel):
    """Запрос на фиксацию и публикацию персональной витрины клиенту."""
    selected_bundle_group: int = Field(
        default=1,
        description="Номер выбранного пакета, который утверждается (1 или 2)"
    )
    final_items: list[SelectedEventTariffPairIn] = Field(
        ...,
        description="Итоговый список пар (event_id, tariff_id), входящих в витрину клиента"
    )
    final_pitch_text: str = Field(
        ...,
        description="Финальный текст сопроводительного письма, отредактированный менеджером"
    )


class PublishSelectionOut(BaseModel):
    """Результат публикации: ссылка Magic Link и параметры опубликованной витрины."""
    selection_id: int = Field(..., description="ID опубликованной подборки")
    status: Literal["published"] = "published"
    magic_token: UUID = Field(..., description="Криптографический UUIDv4 токен публичной витрины")
    public_showcase_url: str = Field(..., description="Относительный URL витрины для копирования (/s/{magic_token})")
    total_package_price: float = Field(..., description="Итоговая сумма утвержденного пакета")
    total_package_savings: float = Field(..., description="Суммарная экономия по раннему бронированию")


# ============================================================================
# 4. СХЕМЫ КАТАЛОГА МЕРОПРИЯТИЙ В КАБИНЕТЕ МЕНЕДЖЕРА (GET /api/manager/events)
# ============================================================================

class CatalogEventItemOut(BaseModel):
    """Карточка мероприятия в базе отслеживаемых площадок менеджера."""
    model_config = ConfigDict(from_attributes=True)

    event_id: int = Field(..., description="ID события в таблице events")
    canonical_title: str = Field(..., description="Официальное название мероприятия")
    event_format: Literal["roundtable", "business_breakfast", "forum", "conference", "session"] = Field(
        ..., description="Формат проведения"
    )
    city: str | None = Field(None, description="Город проведения (None для онлайн)")
    is_online: bool = Field(False, description="Признак онлайн-мероприятия")
    venue: str | None = Field(None, description="Площадка проведения или онлайн-платформа")
    start_date: date = Field(..., description="Дата начала (YYYY-MM-DD)")
    end_date: date = Field(..., description="Дата окончания (YYYY-MM-DD)")
    summary: str = Field(..., description="Краткое описание и целевая аудитория площадки")
    themes: list[str] = Field(default_factory=list, description="Отраслевые теги и направления")
    tariffs: list[TariffOptionOut] = Field(
        default_factory=list,
        description="Доступные тарифы организатора и условия раннего бронирования"
    )


class ManagerEventsCatalogOut(BaseModel):
    """Список всех активных мероприятий, отслеживаемых агентством."""
    total_count: int = Field(..., description="Общее количество активных площадок в базе")
    events: list[CatalogEventItemOut] = Field(default_factory=list, description="Список мероприятий с тарифами")
