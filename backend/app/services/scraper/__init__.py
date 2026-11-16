from app.core.config import settings
from app.services.ai_client import (
    LLM_SEMAPHORE,
    get_embedding,
    get_embeddings_batch,
    raw_openai_client,
    structured_llm_client,
)
from app.services.rag import (
    _is_quote_grounded as _is_quote_grounded,
)
from app.services.rag import (
    build_rag_cache_key,
    invalidate_rag_cache,
)
from app.services.scraper.crawler import (
    CollectedEventDossier,
    OrganizerLinksSelection,
    collect_event_dossier,
    collect_event_dossiers,
)
from app.services.scraper.fetcher import (
    CaptchaBlockedError,
    HttpCatalogSourceScraper,
    UnsafeUrlError,
    fetch_pdf_bytes_safe,
    fetch_url_dossier_text,
    validate_safe_public_url,
)
from app.services.scraper.fetcher import (
    _convert_html_to_dossier_markdown as _convert_html_to_dossier_markdown,
)
from app.services.scraper.fetcher import (
    _fetch_raw_page_content as _fetch_raw_page_content,
)
from app.services.scraper.fetcher import (
    _fetch_via_jina_reader as _fetch_via_jina_reader,
)
from app.services.scraper.ingestion import (
    MAX_DOSSIER_CHARS,
    DataQualityStatus,
    EventRejectedError,
    evaluate_event_quality,
    evaluate_event_quality_gate,
    find_duplicate_event,
    ingest_event_from_text,
    ingest_smart_event,
    is_russia_or_online_event,
)
from app.services.scraper.ingestion import (
    _clean_title_for_comparison as _clean_title_for_comparison,
)
from app.services.scraper.ingestion import (
    _extract_pdf_dossier_parts as _extract_pdf_dossier_parts,
)
from app.services.scraper.ingestion import (
    _extract_structured_event_via_llm as _extract_structured_event_via_llm,
)
from app.services.scraper.ingestion import (
    _merge_into_existing as _merge_into_existing,
)
from app.services.scraper.ingestion import (
    _merge_regulation_markdown as _merge_regulation_markdown,
)
from app.services.scraper.ingestion import (
    _populate_faq_cache as _populate_faq_cache,
)
from app.services.scraper.ingestion import (
    _sync_event_chunks as _sync_event_chunks,
)
from app.services.scraper.ingestion import (
    _sync_event_tariffs as _sync_event_tariffs,
)
from app.services.scraper.monitoring import (
    ScrapingRunSummary,
    run_customer_sources_monitoring,
)
from app.services.scraper.monitoring import (
    _ingest_source_new_urls as _ingest_source_new_urls,
)
from app.services.scraper.monitoring import (
    _load_known_source_urls as _load_known_source_urls,
)
from app.services.scraper.pdf_reader import (
    IMPORTANT_PDF_KEYWORDS,
    OcrBudgetTracker,
    OpenAICompatibleVisionOCRProvider,
    StubVisionOCRProvider,
    VisionOCRProviderProtocol,
    build_vision_ocr_provider,
    extract_pdf_text_async,
    extract_relevant_pdf_text_sync,
    should_run_vision_ocr,
    split_regulation_into_chunks,
)
from app.services.scraper.pdf_reader import (
    _validate_pdf_bytes as _validate_pdf_bytes,
)
from app.services.scraper.runner import (
    get_active_scraper_run_id,
    is_scraper_busy,
    recover_stale_scraper_runs,
    run_persisted_scraper_job,
    start_scraper_run_record,
    try_enqueue_scraper_run,
)
from app.services.scraper.sources import (
    CUSTOMER_SOURCES_REGISTRY,
    CatalogSourceScraperProtocol,
    CustomerSourceConfig,
    DiscoveredCandidate,
    DiscoveryResult,
    StubCatalogSourceScraper,
    canonicalize_url,
    ensure_builtin_scraper_sources,
    extract_discovery_candidates,
    extract_filtered_card_urls,
)
from app.services.scraper.sources import (
    _collect_raw_links as _collect_raw_links,
)
from app.services.scraper.sources import (
    _extract_urls_from_ld_dict as _extract_urls_from_ld_dict,
)
from app.services.scraper.sources import (
    _extract_urls_from_ld_json as _extract_urls_from_ld_json,
)
from app.services.scraper.sources import (
    _normalize_clean_url as _normalize_clean_url,
)
from app.services.scraper.triage import (
    CandidateTriageDecision,
    triage_discovery_candidate,
)

__all__ = [
    "CUSTOMER_SOURCES_REGISTRY",
    "IMPORTANT_PDF_KEYWORDS",
    "LLM_SEMAPHORE",
    "MAX_DOSSIER_CHARS",
    "CandidateTriageDecision",
    "CaptchaBlockedError",
    "CatalogSourceScraperProtocol",
    "CollectedEventDossier",
    "CustomerSourceConfig",
    "DataQualityStatus",
    "DiscoveredCandidate",
    "DiscoveryResult",
    "EventRejectedError",
    "HttpCatalogSourceScraper",
    "OcrBudgetTracker",
    "OpenAICompatibleVisionOCRProvider",
    "OrganizerLinksSelection",
    "ScrapingRunSummary",
    "StubCatalogSourceScraper",
    "StubVisionOCRProvider",
    "UnsafeUrlError",
    "VisionOCRProviderProtocol",
    "build_rag_cache_key",
    "build_vision_ocr_provider",
    "canonicalize_url",
    "collect_event_dossier",
    "collect_event_dossiers",
    "ensure_builtin_scraper_sources",
    "evaluate_event_quality",
    "evaluate_event_quality_gate",
    "extract_discovery_candidates",
    "extract_filtered_card_urls",
    "extract_pdf_text_async",
    "extract_relevant_pdf_text_sync",
    "fetch_pdf_bytes_safe",
    "fetch_url_dossier_text",
    "find_duplicate_event",
    "get_active_scraper_run_id",
    "get_embedding",
    "get_embeddings_batch",
    "ingest_event_from_text",
    "ingest_smart_event",
    "invalidate_rag_cache",
    "is_russia_or_online_event",
    "is_scraper_busy",
    "raw_openai_client",
    "recover_stale_scraper_runs",
    "run_customer_sources_monitoring",
    "run_persisted_scraper_job",
    "settings",
    "should_run_vision_ocr",
    "split_regulation_into_chunks",
    "start_scraper_run_record",
    "structured_llm_client",
    "triage_discovery_candidate",
    "try_enqueue_scraper_run",
    "validate_safe_public_url",
]
