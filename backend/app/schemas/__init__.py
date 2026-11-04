from app.schemas.event_ingestion import (
    EventIngestionSchema,
    FAQCacheItem,
    TariffExtracted,
)
from app.schemas.manager import (
    BundleEventItemOut,
    BundleVariantOut,
    BurningDeadlineOut,
    ClientQueryExtracted,
    ClientSummaryOut,
    ManagerDashboardOut,
    MatchRequestIn,
    MatchResponseOut,
    PublishSelectionIn,
    PublishSelectionOut,
    SelectedEventTariffPairIn,
    TariffOptionOut,
)
from app.schemas.showcase import (
    AskRegulationQuestionIn,
    AskRegulationQuestionOut,
    ClientReactionIn,
    ClientReactionOut,
    ShowcaseEventItemOut,
    ShowcaseViewOut,
)

# [AUDIT-CRUTCH]: В __all__ и импортах пропущены схемы CatalogEventItemOut, ManagerEventsCatalogOut, EscalateQuestionIn и EscalateQuestionOut.
__all__ = [
    "BurningDeadlineOut",
    "ClientSummaryOut",
    "ManagerDashboardOut",
    "ClientQueryExtracted",
    "MatchRequestIn",
    "TariffOptionOut",
    "BundleEventItemOut",
    "BundleVariantOut",
    "MatchResponseOut",
    "SelectedEventTariffPairIn",
    "PublishSelectionIn",
    "PublishSelectionOut",
    "ShowcaseEventItemOut",
    "ShowcaseViewOut",
    "ClientReactionIn",
    "ClientReactionOut",
    "AskRegulationQuestionIn",
    "AskRegulationQuestionOut",
    "TariffExtracted",
    "FAQCacheItem",
    "EventIngestionSchema",
]
