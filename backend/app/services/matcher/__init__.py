from app.core.config import settings
from app.core.timeutils import today_local
from app.services.ai_client import LLM_SEMAPHORE, get_embedding, structured_llm_client
from app.services.matcher.bundles import (
    build_bundles,
    build_tariff_option,
    evaluate_candidate_tuple,
    has_offline_date_conflict,
    pick_best_tariff_for_role,
)
from app.services.matcher.candidates import (
    build_fts_or_query,
    fetch_hybrid_rrf_candidates,
    get_scored_candidates,
)
from app.services.matcher.pipeline import (
    _format_bundle_variants_out as _format_bundle_variants_out,
)
from app.services.matcher.pipeline import (
    _load_and_update_client_profile as _load_and_update_client_profile,
)
from app.services.matcher.pipeline import (
    _persist_draft_selection as _persist_draft_selection,
)
from app.services.matcher.pipeline import (
    _to_bundle_event_item as _to_bundle_event_item,
)
from app.services.matcher.pipeline import (
    run_client_matching_pipeline,
)
from app.services.matcher.pitch import (
    EventRationaleLLMItem,
    PitchAndRationalesLLMResponse,
    PitchOnlyLLMResponse,
    build_default_rationale,
    build_fallback_pitch,
    generate_live_pitch_text,
    generate_pitch_and_rationales,
)
from app.services.matcher.types import (
    EvaluatedCombo,
    EventDataStatus,
    EventFormat,
    ParticipationRole,
    ScoredEventCandidate,
)
from app.services.profiler import extract_client_profile

__all__ = [
    "LLM_SEMAPHORE",
    "EvaluatedCombo",
    "EventDataStatus",
    "EventFormat",
    "EventRationaleLLMItem",
    "ParticipationRole",
    "PitchAndRationalesLLMResponse",
    "PitchOnlyLLMResponse",
    "ScoredEventCandidate",
    "build_bundles",
    "build_default_rationale",
    "build_fallback_pitch",
    "build_fts_or_query",
    "build_tariff_option",
    "evaluate_candidate_tuple",
    "extract_client_profile",
    "fetch_hybrid_rrf_candidates",
    "generate_live_pitch_text",
    "generate_pitch_and_rationales",
    "get_embedding",
    "get_scored_candidates",
    "has_offline_date_conflict",
    "pick_best_tariff_for_role",
    "run_client_matching_pipeline",
    "settings",
    "structured_llm_client",
    "today_local",
]
