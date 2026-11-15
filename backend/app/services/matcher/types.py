import datetime
from dataclasses import dataclass
from typing import Literal, TypeAlias

from app.models.models import Event
from app.schemas.manager import TariffOptionOut

EventFormat: TypeAlias = Literal["roundtable", "business_breakfast", "forum", "conference", "session"]
ParticipationRole: TypeAlias = Literal["delegate", "speaker", "sponsor"]
EventDataStatus: TypeAlias = Literal["ready", "needs_enrichment", "archived"]


@dataclass
class ScoredEventCandidate:
    """Кандидат мероприятия с рассчитанным RRF-рейтингом и разделенными тарифами."""

    event: Event
    rrf_score: float
    all_tariffs: list[TariffOptionOut]
    priced_tariffs: list[TariffOptionOut]
    on_request_tariffs: list[TariffOptionOut]


@dataclass
class EvaluatedCombo:
    """Оцененная комбинация мероприятий с назначенными тарифами и флагами соблюдения ограничений."""

    candidates: tuple[ScoredEventCandidate, ...]
    chosen_tariffs: tuple[TariffOptionOut, ...]
    total_actual_price: float
    total_base_price: float
    total_savings: float
    earliest_deadline: datetime.date | None
    combo_score: float
    is_over_budget_tolerance: bool
    roles_strictly_matched: bool = True
    has_date_conflict: bool = False
    matched_speaker_count: int = 0


def _normalize_participation_role(raw_role: str | None) -> ParticipationRole:
    """Приводит строковую роль из БД к строгому типу ParticipationRole."""
    if raw_role == "speaker":
        return "speaker"
    if raw_role == "sponsor":
        return "sponsor"
    return "delegate"


def _normalize_event_format(raw_format: str | None) -> EventFormat:
    """Приводит строковый формат события из БД к строгому типу EventFormat."""
    if raw_format == "roundtable":
        return "roundtable"
    if raw_format == "business_breakfast":
        return "business_breakfast"
    if raw_format == "forum":
        return "forum"
    if raw_format == "session":
        return "session"
    return "conference"


def _normalize_data_status(raw_status: str | None) -> EventDataStatus:
    """Приводит статус полноты данных из БД к строгому типу EventDataStatus."""
    if raw_status == "needs_enrichment":
        return "needs_enrichment"
    if raw_status == "archived":
        return "archived"
    return "ready"
