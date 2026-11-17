import codecs
import re
from datetime import date, datetime
from typing import Literal, Self, cast
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.constants import is_online_format, normalize_city


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
    is_active: bool = Field(default=True, description="Признак активности клиента (False — архивирован)")
    latest_selection_id: int | None = Field(None, description="ID последней созданной подборки")
    latest_selection_status: Literal["draft", "published"] | None = Field(
        None, description="Статус подборки: черновик или опубликована"
    )
    magic_token: UUID | None = Field(None, description="UUID токен витрины, если подборка опубликована")


class ClientCreateIn(BaseModel):
    """Запрос на создание нового клиента в кабинете менеджера."""
    company_name: str = Field(..., min_length=1, max_length=255, description="Название компании клиента")
    contact_person: str | None = Field(None, max_length=255, description="Контактное лицо клиента")
    raw_manager_notes: str | None = Field(
        default="", max_length=10000, description="Первичный конспект встречи с клиентом"
    )

    @field_validator("company_name")
    @classmethod
    def validate_company_name(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Название компании клиента не может быть пустым.")
        return cleaned

    @field_validator("contact_person")
    @classmethod
    def normalize_contact_person(cls, v: str | None) -> str | None:
        if v is None:
            return None
        cleaned = v.strip()
        return cleaned or None

    @field_validator("raw_manager_notes")
    @classmethod
    def normalize_notes(cls, v: str | None) -> str:
        return v.strip() if v is not None else ""


class ClientUpdateIn(BaseModel):
    """Запрос на обновление данных клиента или мягкую архивацию/восстановление."""
    company_name: str | None = Field(default=None, max_length=255, description="Новое название компании")
    contact_person: str | None = Field(default=None, max_length=255, description="Контактное лицо")
    raw_manager_notes: str | None = Field(default=None, max_length=10000, description="Конспект встречи")
    is_active: bool | None = Field(
        default=None, description="Флаг активности клиента (False — мягкая архивация, True — восстановление)"
    )

    @field_validator("company_name")
    @classmethod
    def validate_company_name(cls, v: str | None) -> str | None:
        if v is None:
            return None
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Название компании клиента не может быть пустым.")
        return cleaned

    @field_validator("contact_person")
    @classmethod
    def normalize_contact_person(cls, v: str | None) -> str | None:
        if v is None:
            return None
        cleaned = v.strip()
        return cleaned or None

    @model_validator(mode="after")
    def validate_non_null_required_fields(self) -> Self:
        if "company_name" in self.model_fields_set and self.company_name is None:
            raise ValueError("Название компании клиента не может быть пустым (null).")
        if "is_active" in self.model_fields_set and self.is_active is None:
            raise ValueError("Флаг активности is_active не может быть null.")
        return self

class ManagerDashboardOut(BaseModel):
    """Ответ дашборда менеджера: клиенты и горящие дедлайны."""
    clients: list[ClientSummaryOut] = Field(..., description="Список закрепленных клиентов")
    burning_deadlines: list[BurningDeadlineOut] = Field(
        default_factory=list,
        description="Алерты: мероприятия, у которых скидка Early Bird сгорает менее чем через 72 часа"
    )

class ClientQueryExtracted(BaseModel):
    """
    Схема извлечения параметров из свободной заметки менеджера (NER-профайлер).
    Полностью совпадает с контрактом модуля profiler.py.
    """
    cities: list[str] = Field(default_factory=list, description="Канонические названия городов проведения")
    include_online: bool = Field(default=True, description="Включать ли онлайн-мероприятия (вебинары, трансляции)")
    date_from: date | None = Field(None, description="Начало периода поиска (YYYY-MM-DD)")
    date_to: date | None = Field(None, description="Конец периода поиска (YYYY-MM-DD)")
    total_budget_max: float = Field(..., gt=0, description="Общий потолок бюджета на всю серию в рублях")
    target_events_count: int = Field(default=3, ge=1, le=10, description="Желаемое число событий в пакете")
    preferred_formats: list[Literal["roundtable", "business_breakfast", "forum", "conference", "session"]] = Field(
        default_factory=list,
        description="Предпочтительные форматы деловых событий"
    )
    required_roles: list[Literal["delegate", "speaker", "sponsor"]] = Field(
        default_factory=lambda: [cast(Literal["delegate", "speaker", "sponsor"], "delegate")],
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
    budget_is_assumed: bool = Field(
        default=False,
        description="True, если бюджет не был явно назван клиентом и применен дефолтный ориентир",
    )
    profile_source: Literal["llm", "heuristic", "manual"] = Field(
        default="llm",
        description="Способ формирования профиля: llm (нейросеть), heuristic (детерминированный парсер) или manual (правка менеджера)",
    )

    @model_validator(mode="after")
    def validate_query_invariants(self) -> Self:
        """Синхронизирует границы дат, слоты спикера, канонические города и непустой семантический запрос."""
        if self.date_from and self.date_to and self.date_to < self.date_from:
            raise ValueError(f"date_to ({self.date_to}) не может быть раньше date_from ({self.date_from})")
        self.min_speaker_events = min(self.min_speaker_events, self.target_events_count)
        if self.cities:
            cleaned_cities: list[str] = []
            for c in self.cities:
                if not c:
                    continue
                if is_online_format(c):
                    self.include_online = True
                    continue
                norm = normalize_city(c)
                if norm and norm not in cleaned_cities:
                    cleaned_cities.append(norm)
            self.cities = cleaned_cities
        if not self.semantic_search_query or not self.semantic_search_query.strip():
            fallback_parts = [*self.themes_keywords, *self.cities]
            self.semantic_search_query = " ".join(fallback_parts).strip() or "деловые мероприятия форумы конференции"
        return self

class MatchRequestIn(BaseModel):
    """Входной запрос на подбор пакетов деловых мероприятий."""
    raw_manager_notes: str = Field(
        ...,
        min_length=10,
        description="Сырой текст заметки менеджера после звонка с клиентом",
        examples=[
            (
                "Созвонились с ГК Пионер. Ищут на ноябрь-декабрь в Москве или СПб 3 мероприятия по КРТ и урбанистике. "
                "Хотя бы на одном хотят выступить спикером. Общий бюджет на всё — 400 000 руб."
            )
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
    website_url: str | None = Field(
        default=None,
        description="Официальный сайт мероприятия или страница регистрации"
    )
    data_status: Literal["ready", "needs_enrichment", "archived"] = Field(
        default="ready",
        description="Статус полноты карточки: ready, needs_enrichment или archived",
    )
    missing_data_warnings: list[str] = Field(
        default_factory=list, description="Список предупреждений о недостающих данных"
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


class WorkspaceSelectionOut(BaseModel):
    """Восстановленное состояние последней подборки клиента из БД (draft или published)."""
    selection_id: int = Field(..., description="ID подборки в таблице selections")
    status: Literal["draft", "published"] = Field(..., description="Статус подборки")
    magic_token: UUID | None = Field(
        None, description="UUID токен публичной витрины (при статусе published)"
    )
    total_budget_limit: float = Field(..., description="Зафиксированный лимит бюджета подборки")
    bundle_variants: list[BundleVariantOut] = Field(
        default_factory=list,
        description="Восстановленные варианты пакетов мероприятий"
    )
    bonus_on_request_items: list[BundleEventItemOut] = Field(
        default_factory=list,
        description="Бонусные мероприятия по запросу (для совместимости со схемой конструктора)"
    )
    generated_pitch_text: str = Field(
        default="",
        description="Сохраненный текст сопроводительного письма КП"
    )


class ClientWorkspaceOut(BaseModel):
    """Серверное состояние рабочего пространства клиента для восстановления секций 01-03."""
    client_id: int = Field(..., description="ID клиента")
    company_name: str = Field(..., description="Название компании клиента")
    contact_person: str | None = Field(None, description="Контактное лицо клиента")
    raw_manager_notes: str = Field(..., description="Последний сохраненный конспект созвона")
    is_active: bool = Field(default=True, description="Признак активности клиента")
    extracted_profile: ClientQueryExtracted | None = Field(
        None,
        description="Сохраненный в БД структурированный профиль клиента (или None)"
    )
    selection: WorkspaceSelectionOut | None = Field(
        None,
        description="Последняя подборка клиента (draft или published) с позициями, либо None"
    )

class SelectedEventTariffPairIn(BaseModel):
    """Пара (мероприятие, выбранный тариф), утвержденная менеджером для публикации."""
    event_id: int = Field(..., description="ID события")
    tariff_id: int = Field(..., description="ID выбранного тарифа")
    ai_rationale: str | None = Field(None, description="Отредактированное менеджером обоснование")


def _validate_unique_final_items(items: list[SelectedEventTariffPairIn]) -> None:
    """Гарантирует отсутствие дублей одного и того же мероприятия в списке пар."""
    seen_events: set[int] = set()
    for item in items:
        if item.event_id in seen_events:
            raise ValueError(f"Дублирование мероприятия event_id={item.event_id} в final_items не допускается.")
        seen_events.add(item.event_id)


class PublishSelectionIn(BaseModel):
    """Запрос на фиксацию и публикацию персональной витрины клиенту."""
    selected_bundle_group: Literal[1, 2] = Field(
        default=1,
        description="Номер выбранного пакета, который утверждается (1 или 2)"
    )
    final_items: list[SelectedEventTariffPairIn] = Field(
        ...,
        min_length=1, description="Итоговый список пар (event_id, tariff_id), входящих в витрину клиента"
    )
    final_pitch_text: str = Field(
        ...,
        description="Финальный текст сопроводительного письма, отредактированный менеджером"
    )

    @model_validator(mode="after")
    def validate_unique_events(self) -> Self:
        """Гарантирует отсутствие дублей одного и того же мероприятия в публикуемом пакете."""
        _validate_unique_final_items(self.final_items)
        return self


class GeneratePitchIn(BaseModel):
    """Запрос на живую перегенерацию сопроводительного письма КП по выбранным парам (event_id, tariff_id)."""
    final_items: list[SelectedEventTariffPairIn] = Field(
        ...,
        min_length=1,
        description="Итоговый список пар (event_id, tariff_id), по которым пересчитывается письмо КП",
    )
    raw_manager_notes: str | None = Field(
        default=None,
        description="Актуальный конспект встречи от менеджера",
    )
    total_budget_max: float | None = Field(
        default=None,
        gt=0,
        description="Целевой лимит бюджета клиента в рублях",
    )
    include_budget_limit: bool = Field(
        default=True,
        description="Упоминать ли ориентир бюджета клиента в тексте письма",
    )

    @model_validator(mode="after")
    def validate_unique_events(self) -> Self:
        """Гарантирует отсутствие дублей одного и того же мероприятия в запросе генерации письма."""
        _validate_unique_final_items(self.final_items)
        return self


class GeneratePitchOut(BaseModel):
    """Результат живой генерации сопроводительного письма КП."""
    selection_id: int = Field(..., description="ID подборки")
    generated_pitch_text: str = Field(..., description="Сгенерированный текст сопроводительного письма КП")
    used_llm: bool = Field(..., description="True, если письмо сгенерировано живой LLM; False при откате на шаблон")

class PublishSelectionOut(BaseModel):
    """Результат публикации: ссылка Magic Link и параметры опубликованной витрины."""
    selection_id: int = Field(..., description="ID опубликованной подборки")
    status: Literal["published"] = "published"
    magic_token: UUID = Field(..., description="Криптографический UUIDv4 токен публичной витрины")
    public_showcase_url: str = Field(..., description="Относительный URL витрины для копирования (/s/{magic_token})")
    total_package_price: float = Field(..., description="Итоговая сумма утвержденного пакета")
    total_package_savings: float = Field(..., description="Суммарная экономия по раннему бронированию")

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
    website_url: str | None = Field(
        default=None,
        description="Официальный сайт мероприятия или страница регистрации"
    )
    data_status: Literal["ready", "needs_enrichment", "archived"] = Field(
        default="ready",
        description="Статус полноты карточки: ready, needs_enrichment или archived",
    )
    missing_data_warnings: list[str] = Field(
        default_factory=list, description="Список предупреждений о недостающих данных"
    )

class ManagerEventsCatalogOut(BaseModel):
    """Список всех активных мероприятий, отслеживаемых агентством."""
    total_count: int = Field(..., description="Общее количество активных площадок в базе")
    events: list[CatalogEventItemOut] = Field(default_factory=list, description="Список мероприятий с тарифами")


class EventUploadOut(BaseModel):
    """Результат ручной загрузки/обогащения мероприятия через PDF, URL или сырой текст."""
    event_id: int = Field(..., description="ID созданного или обогащенного мероприятия")
    canonical_title: str = Field(..., description="Каноническое название")
    data_status: str = Field(..., description="Статус полноты карточки (ready / needs_enrichment)")
    tariffs_count: int = Field(..., description="Количество извлеченных тарифов")
    message: str = Field(..., description="Результат обработки")


AdapterTypeLiteral = Literal["html_list", "rss", "html_digest", "manual_only"]

_CYRILLIC_TRANSLIT_MAP: dict[str, str] = {
    "а": "a",
    "б": "b",
    "в": "v",
    "г": "g",
    "д": "d",
    "е": "e",
    "ё": "e",
    "ж": "zh",
    "з": "z",
    "и": "i",
    "й": "y",
    "к": "k",
    "л": "l",
    "м": "m",
    "н": "n",
    "о": "o",
    "п": "p",
    "р": "r",
    "с": "s",
    "т": "t",
    "у": "u",
    "ф": "f",
    "х": "kh",
    "ц": "ts",
    "ч": "ch",
    "ш": "sh",
    "щ": "shch",
    "ъ": "",
    "ы": "y",
    "ь": "",
    "э": "e",
    "ю": "yu",
    "я": "ya",
}
_SOURCE_KEY_RE = re.compile(r"^[a-z0-9][a-z0-9_\-]{0,99}$")


def slugify_source_key(display_name: str) -> str:
    """Детерминированная транслитерация названия площадки в безопасный source_key."""
    translit = "".join(_CYRILLIC_TRANSLIT_MAP.get(ch, ch) for ch in display_name.lower())
    slug = re.sub(r"[^a-z0-9]+", "_", translit)
    slug = re.sub(r"_+", "_", slug)[:90].strip("_")
    if not slug:
        return "custom_source"
    if slug == "all":
        return "all_source"
    return slug


def _validate_catalog_urls_list(urls: list[str]) -> list[str]:
    cleaned_urls: list[str] = []
    seen: set[str] = set()
    for raw in urls:
        u = raw.strip()
        if not u:
            raise ValueError("URL каталога не может быть пустым.")
        parts = urlsplit(u)
        if parts.scheme.lower() not in ("http", "https") or not parts.netloc or not parts.hostname:
            raise ValueError(f"Некорректный URL каталога '{u}': ожидается http:// или https://.")
        if u not in seen:
            seen.add(u)
            cleaned_urls.append(u)
    if not cleaned_urls:
        raise ValueError("Необходимо указать хотя бы один URL каталога.")
    return cleaned_urls


_MAX_REGEX_PATTERNS_COUNT = 20
_MAX_REGEX_PATTERN_LENGTH = 300


def _validate_regex_patterns_list(patterns: list[str]) -> list[str]:
    if len(patterns) > _MAX_REGEX_PATTERNS_COUNT:
        raise ValueError(
            f"Слишком много regex-паттернов: допускается не более {_MAX_REGEX_PATTERNS_COUNT}."
        )
    validated: list[str] = []
    for raw in patterns:
        pat = raw.strip()
        if not pat:
            raise ValueError("Регулярное выражение не может быть пустой строкой.")
        if len(pat) > _MAX_REGEX_PATTERN_LENGTH:
            raise ValueError(
                f"Регулярное выражение слишком длинное ({len(pat)} симв.): максимум {_MAX_REGEX_PATTERN_LENGTH} символов."
            )
        try:
            re.compile(pat)
        except re.error as exc:
            raise ValueError(f"Некорректное регулярное выражение '{pat}': {exc}") from exc
        validated.append(pat)
    return validated


def _validate_encoding_name(value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError("Кодировка не может быть пустой.")
    try:
        codecs.lookup(cleaned)
    except LookupError as exc:
        raise ValueError(f"Неподдерживаемая кодировка '{cleaned}'.") from exc
    return cleaned


def _normalize_cookies_dict(cookies: dict[str, str]) -> dict[str, str]:
    normalized: dict[str, str] = {}
    for k, v in cookies.items():
        key = str(k).strip()
        if not key:
            raise ValueError("Имя cookie не может быть пустым.")
        normalized[key] = str(v)
    return normalized


class ScraperRunIn(BaseModel):
    """Запрос на ручной запуск фонового парсера по конкретной площадке или всем сразу."""
    source_key: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Ключ площадки из scraper_sources или 'all' для обхода всех активных площадок",
    )
    dry_run: bool = Field(
        default=False,
        description="Пробный запуск только стадии Discovery без вызова LLM и записи событий",
    )
    max_urls_per_source: int | None = Field(
        default=None,
        ge=1,
        le=50,
        description="Временный лимит новых URL на один источник для этого запуска (1..50)",
    )

    @field_validator("source_key")
    @classmethod
    def validate_source_key(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Ключ площадки source_key не может быть пустым.")
        return cleaned


class ScraperRunOut(BaseModel):
    """Статус постановки задачи скрейпера в фоновый воркер."""
    source_key: str = Field(..., description="Ключ площадки")
    status: Literal["queued", "running", "completed", "failed"] = Field(
        "queued", description="Статус запуска"
    )
    message: str = Field(..., description="Информационное сообщение")
    run_id: int | None = Field(default=None, description="ID записи прогона в scraper_runs")
    dry_run: bool = Field(default=False, description="Признак пробного прогона")


class ScraperSourceOut(BaseModel):
    """Конфигурация площадки мониторинга из таблицы scraper_sources."""
    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., description="ID источника")
    source_key: str = Field(..., description="Уникальный ключ площадки")
    display_name: str = Field(..., description="Отображаемое название площадки")
    catalog_urls: list[str] = Field(default_factory=list, description="Список URL каталогов/RSS-лент")
    adapter_type: AdapterTypeLiteral = Field(..., description="Тип адаптера сбора")
    card_url_patterns: list[str] = Field(default_factory=list, description="Regex-паттерны ссылок карточек")
    exclude_url_patterns: list[str] = Field(default_factory=list, description="Regex-паттерны исключений")
    b2b_filter_enabled: bool = Field(default=False, description="Фильтрация B2C/непрофильных событий")
    russia_online_only: bool = Field(default=True, description="Фильтр только РФ или онлайн")
    use_jina_reader: bool = Field(default=False, description="Загружать страницы через r.jina.ai")
    encoding: str = Field(default="utf-8", description="Кодировка страниц источника")
    required_cookies: dict[str, str] = Field(default_factory=dict, description="Обязательные cookies")
    max_urls_per_run: int = Field(default=10, description="Лимит новых URL за один прогон")
    is_enabled: bool = Field(default=True, description="Включен ли источник в автоматический мониторинг")
    is_builtin: bool = Field(default=False, description="Признак встроенной площадки заказчика")
    created_at: datetime = Field(..., description="Дата создания")
    updated_at: datetime = Field(..., description="Дата последнего обновления")


class ScraperSourceCreateIn(BaseModel):
    """Запрос на добавление новой площадки мониторинга (Вариант А + опциональные расширенные настройки)."""
    display_name: str = Field(..., min_length=2, max_length=255, description="Название площадки")
    catalog_urls: list[str] = Field(..., min_length=1, description="Список URL каталогов или RSS-лент")
    adapter_type: AdapterTypeLiteral = Field(default="html_list", description="Тип адаптера сбора")
    b2b_filter_enabled: bool = Field(default=False, description="Включить B2C/B2B фильтрацию")
    russia_online_only: bool = Field(default=True, description="Оставлять только РФ и онлайн")
    source_key: str | None = Field(
        default=None,
        max_length=100,
        description="Опциональный ключ площадки (если не указан — генерируется из названия)",
    )
    card_url_patterns: list[str] = Field(
        default_factory=list, description="Опциональные regex-паттерны ссылок карточек"
    )
    exclude_url_patterns: list[str] = Field(
        default_factory=list, description="Опциональные regex-паттерны исключений"
    )
    use_jina_reader: bool = Field(default=False, description="Использовать r.jina.ai")
    encoding: str = Field(default="utf-8", min_length=1, max_length=50, description="Кодировка")
    required_cookies: dict[str, str] = Field(default_factory=dict, description="Cookies для запросов")
    max_urls_per_run: int = Field(default=10, ge=1, le=50, description="Максимум новых URL за запуск")
    is_enabled: bool = Field(default=True, description="Активен ли источник")

    @field_validator("display_name")
    @classmethod
    def validate_display_name(cls, v: str) -> str:
        cleaned = v.strip()
        if len(cleaned) < 2:
            raise ValueError("Название площадки должно содержать минимум 2 символа.")
        return cleaned

    @field_validator("source_key")
    @classmethod
    def validate_source_key(cls, v: str | None) -> str | None:
        if v is None:
            return None
        cleaned = v.strip().lower()
        if not cleaned:
            return None
        if cleaned == "all":
            raise ValueError("Ключ 'all' зарезервирован системой.")
        if not _SOURCE_KEY_RE.match(cleaned):
            raise ValueError(
                "source_key должен содержать только строчную латиницу, цифры, '_' или '-'."
            )
        return cleaned

    @field_validator("catalog_urls")
    @classmethod
    def validate_catalog_urls(cls, v: list[str]) -> list[str]:
        return _validate_catalog_urls_list(v)

    @field_validator("card_url_patterns", "exclude_url_patterns")
    @classmethod
    def validate_regex_patterns(cls, v: list[str]) -> list[str]:
        return _validate_regex_patterns_list(v)

    @field_validator("encoding")
    @classmethod
    def validate_encoding(cls, v: str) -> str:
        return _validate_encoding_name(v)

    @field_validator("required_cookies")
    @classmethod
    def validate_cookies(cls, v: dict[str, str]) -> dict[str, str]:
        return _normalize_cookies_dict(v)


class ScraperSourceUpdateIn(BaseModel):
    """Запрос на частичное обновление параметров площадки мониторинга."""
    display_name: str | None = Field(default=None, min_length=2, max_length=255)
    catalog_urls: list[str] | None = Field(default=None, min_length=1)
    adapter_type: AdapterTypeLiteral | None = Field(default=None)
    card_url_patterns: list[str] | None = Field(default=None)
    exclude_url_patterns: list[str] | None = Field(default=None)
    b2b_filter_enabled: bool | None = Field(default=None)
    russia_online_only: bool | None = Field(default=None)
    use_jina_reader: bool | None = Field(default=None)
    encoding: str | None = Field(default=None, min_length=1, max_length=50)
    required_cookies: dict[str, str] | None = Field(default=None)
    max_urls_per_run: int | None = Field(default=None, ge=1, le=50)
    is_enabled: bool | None = Field(default=None)

    @field_validator("display_name")
    @classmethod
    def validate_display_name(cls, v: str | None) -> str | None:
        if v is None:
            return None
        cleaned = v.strip()
        if len(cleaned) < 2:
            raise ValueError("Название площадки должно содержать минимум 2 символа.")
        return cleaned

    @field_validator("catalog_urls")
    @classmethod
    def validate_catalog_urls(cls, v: list[str] | None) -> list[str] | None:
        return _validate_catalog_urls_list(v) if v is not None else None

    @field_validator("card_url_patterns", "exclude_url_patterns")
    @classmethod
    def validate_regex_patterns(cls, v: list[str] | None) -> list[str] | None:
        return _validate_regex_patterns_list(v) if v is not None else None

    @field_validator("encoding")
    @classmethod
    def validate_encoding(cls, v: str | None) -> str | None:
        return _validate_encoding_name(v) if v is not None else None

    @field_validator("required_cookies")
    @classmethod
    def validate_cookies(cls, v: dict[str, str] | None) -> dict[str, str] | None:
        return _normalize_cookies_dict(v) if v is not None else None

    @model_validator(mode="after")
    def reject_explicit_nulls(self) -> Self:
        for field_name in self.model_fields_set:
            if getattr(self, field_name) is None:
                raise ValueError(f"Поле '{field_name}' не может быть null.")
        return self


class ScraperSourceDeleteOut(BaseModel):
    """Подтверждение удаления пользовательской площадки мониторинга."""
    deleted: bool = True
    source_key: str


class ScraperSourcePreviewIn(BaseModel):
    """Параметры для бесплатного тест-просмотра Discovery (без вызова LLM) на первом catalog_url."""
    catalog_urls: list[str] = Field(..., min_length=1)
    adapter_type: AdapterTypeLiteral = Field(default="html_list")
    card_url_patterns: list[str] = Field(default_factory=list)
    exclude_url_patterns: list[str] = Field(default_factory=list)
    b2b_filter_enabled: bool = Field(default=False)
    russia_online_only: bool = Field(default=True)
    use_jina_reader: bool = Field(default=False)
    encoding: str = Field(default="utf-8", min_length=1, max_length=50)
    required_cookies: dict[str, str] = Field(default_factory=dict)

    @field_validator("catalog_urls")
    @classmethod
    def validate_catalog_urls(cls, v: list[str]) -> list[str]:
        return _validate_catalog_urls_list(v)

    @field_validator("card_url_patterns", "exclude_url_patterns")
    @classmethod
    def validate_regex_patterns(cls, v: list[str]) -> list[str]:
        return _validate_regex_patterns_list(v)

    @field_validator("encoding")
    @classmethod
    def validate_encoding(cls, v: str) -> str:
        return _validate_encoding_name(v)

    @field_validator("required_cookies")
    @classmethod
    def validate_cookies(cls, v: dict[str, str]) -> dict[str, str]:
        return _normalize_cookies_dict(v)


class ScraperPreviewCandidateOut(BaseModel):
    """Найденный кандидат мероприятия на этапе Discovery Preview."""
    url: str
    title: str = ""
    snippet: str = ""
    is_digest: bool = False


class ScraperSourcePreviewOut(BaseModel):
    """Результат бесплатного предпросмотра Discovery по первой ссылке каталога."""
    discovered_count: int = Field(default=0, ge=0)
    rejected_b2c: int = Field(default=0, ge=0)
    rejected_geo: int = Field(default=0, ge=0)
    sample_candidates: list[ScraperPreviewCandidateOut] = Field(default_factory=list)
    checked_url: str | None = Field(
        default=None,
        description="Фактически проверенный первый URL каталога из списка",
    )
    total_catalog_urls: int = Field(
        default=1,
        ge=0,
        description="Общее количество URL в catalog_urls (проверяется только первый)",
    )
    error: str | None = None


class ScraperRunSavedEventOut(BaseModel):
    """Конкретное мероприятие, созданное или обновленное в ходе прогона парсера."""
    event_id: int | None = None
    title: str
    url: str | None = None
    action: Literal["created", "updated"] = "created"
    data_status: str = "ready"
    start_date: str | None = None
    city: str | None = None


class ScraperRunSourceLogOut(BaseModel):
    """Детальный отчет по одной площадке внутри прогона скрейпера."""
    source_key: str
    display_name: str = ""
    adapter_type: str = "html_list"
    catalog_urls: list[str] = Field(default_factory=list)
    discovered_total: int = 0
    selected_new_count: int = 0
    events_created: int = 0
    events_updated: int = 0
    rejected_b2c: int = 0
    rejected_geo: int = 0
    rejected_past: int = 0
    errors_count: int = 0
    candidate_urls: list[str] = Field(default_factory=list)
    saved_events: list[ScraperRunSavedEventOut] = Field(default_factory=list)
    error: str | None = None


class ScraperRunDetailOut(BaseModel):
    """Полная запись запуска скрейпера (история и live-прогресс)."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: Literal["queued", "running", "completed", "failed"]
    target_source_key: str
    triggered_by: str
    dry_run: bool = False
    sources_total: int = 0
    sources_done: int = 0
    urls_discovered: int = 0
    events_created: int = 0
    events_updated: int = 0
    rejected_b2c: int = 0
    rejected_geo: int = 0
    rejected_past: int = 0
    errors_count: int = 0
    source_logs: list[ScraperRunSourceLogOut] = Field(default_factory=list)
    error_message: str | None = None
    started_at: datetime
    finished_at: datetime | None = None

    @model_validator(mode="after")
    def sync_dry_run_from_trigger(self) -> Self:
        """Вычисляет признак пробного запуска из triggered_by без изменения схемы БД."""
        if self.triggered_by == "manual_dry_run":
            self.dry_run = True
        return self


class ScraperRunsListOut(BaseModel):
    """Список последних прогонов парсера."""
    items: list[ScraperRunDetailOut] = Field(default_factory=list)


class SelectionItemReactionActivity(BaseModel):
    """Активность клиента: реакция на мероприятие из подборки."""
    item_id: int
    event_id: int
    event_title: str
    reaction: str
    comment: str | None = None


class SelectionQuestionActivity(BaseModel):
    """Вопрос клиента, требующий внимания персонального менеджера."""
    message_id: int
    event_id: int | None = None
    event_title: str | None = None
    question_text: str
    created_at: str | None = None


class SelectionResolvedReplyOut(BaseModel):
    """Ответное сообщение куратора на вопрос клиента."""
    reply_message_id: int
    reply_text: str
    created_at: str | None = None


class SelectionResolvedQuestionActivity(BaseModel):
    """История решенного вопроса клиента и ответа(ов) куратора."""
    message_id: int
    event_id: int | None = None
    event_title: str | None = None
    question_text: str
    question_created_at: str | None = None
    replies: list[SelectionResolvedReplyOut] = Field(default_factory=list)
    latest_reply_text: str
    replied_at: str | None = None


class SelectionActivityOut(BaseModel):
    """Сводка активности клиента по витрине для регулярного опроса (Polling) менеджером."""
    selection_id: int
    reactions: list[SelectionItemReactionActivity] = Field(default_factory=list)
    pending_questions: list[SelectionQuestionActivity] = Field(default_factory=list)
    resolved_questions: list[SelectionResolvedQuestionActivity] = Field(default_factory=list)


class ManagerReplyIn(BaseModel):
    """Ответ менеджера на вопрос клиента в чате витрины."""
    message_id: int = Field(..., description="ID сообщения клиента с needs_manager_attention = True")
    reply_text: str = Field(..., min_length=1, description="Текст ответа менеджера")

    @field_validator("reply_text")
    @classmethod
    def validate_reply_text(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Текст ответа менеджера не может быть пустым.")
        return cleaned


class ManagerReplyOut(BaseModel):
    """Результат отправки ответа менеджера в чат витрины."""
    message_id: int = Field(..., description="ID исходного вопроса клиента")
    reply_message_id: int = Field(..., description="ID созданного сообщения менеджера в чате")
    success: bool = True
    message: str = Field(..., description="Статус обработки")


class EventArchiveOut(BaseModel):
    """Результат архивации мероприятия менеджером."""
    event_id: int = Field(..., description="ID архивированного мероприятия")
    status: Literal["archived"] = Field(default="archived", description="Итоговый статус мероприятия")
    message: str = Field(..., description="Сообщение о результате архивации")


class EventRefreshIn(BaseModel):
    """Параметры точечного обновления карточки мероприятия с сайта-первоисточника."""
    force: bool = Field(
        default=False,
        description="Принудительно перечитать и перепарсить через LLM, даже если content_hash не изменился",
    )


class EventRefreshOut(BaseModel):
    """Результат постановки точечного обновления карточки мероприятия в фоновую задачу."""
    event_id: int = Field(..., description="ID мероприятия")
    status: Literal["queued", "running"] = Field(
        default="queued", description="Статус фоновой задачи обновления"
    )
    updated: bool = Field(default=False, description="True если карточка уже обновлена (для обратной совместимости)")
    message: str = Field(..., description="Статус запуска обновления")
    data_status: Literal["ready", "needs_enrichment", "archived"] | None = Field(
        default=None, description="Текущий статус полноты данных карточки"
    )


class EventRefreshStatusOut(BaseModel):
    """Текущий статус фонового обновления карточки мероприятия."""
    event_id: int = Field(..., description="ID мероприятия")
    status: Literal["idle", "queued", "running", "completed", "failed"] = Field(
        ..., description="Состояние задачи обновления"
    )
    updated: bool = Field(
        default=False,
        description="True если карточка была обновлена через LLM, False если изменений нет",
    )
    message: str = Field(default="", description="Человекочитаемый статус обновления")
    data_status: Literal["ready", "needs_enrichment", "archived"] | None = Field(
        default=None, description="Актуальный статус полноты данных карточки"
    )
    error: str | None = Field(default=None, description="Текст ошибки при status='failed'")
    started_at: str | None = Field(default=None, description="ISO-время старта обновления")
    finished_at: str | None = Field(default=None, description="ISO-время завершения обновления")
