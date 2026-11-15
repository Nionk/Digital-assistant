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
from app.services.scraper.fetcher import (
    HttpCatalogSourceScraper,
    fetch_url_dossier_text,
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
    evaluate_event_quality,
    evaluate_event_quality_gate,
    find_duplicate_event,
    ingest_event_from_text,
    ingest_smart_event,
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
    StubVisionOCRProvider,
    VisionOCRProviderProtocol,
    extract_pdf_text_async,
    extract_relevant_pdf_text_sync,
    split_regulation_into_chunks,
)
from app.services.scraper.pdf_reader import (
    _validate_pdf_bytes as _validate_pdf_bytes,
)
from app.services.scraper.sources import (
    CUSTOMER_SOURCES_REGISTRY,
    CatalogSourceScraperProtocol,
    CustomerSourceConfig,
    StubCatalogSourceScraper,
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

__all__ = [
    "CUSTOMER_SOURCES_REGISTRY",
    "IMPORTANT_PDF_KEYWORDS",
    "LLM_SEMAPHORE",
    "MAX_DOSSIER_CHARS",
    "CatalogSourceScraperProtocol",
    "CustomerSourceConfig",
    "DataQualityStatus",
    "HttpCatalogSourceScraper",
    "ScrapingRunSummary",
    "StubCatalogSourceScraper",
    "StubVisionOCRProvider",
    "VisionOCRProviderProtocol",
    "build_rag_cache_key",
    "evaluate_event_quality",
    "evaluate_event_quality_gate",
    "extract_filtered_card_urls",
    "extract_pdf_text_async",
    "extract_relevant_pdf_text_sync",
    "fetch_url_dossier_text",
    "find_duplicate_event",
    "get_embedding",
    "get_embeddings_batch",
    "ingest_event_from_text",
    "ingest_smart_event",
    "invalidate_rag_cache",
    "raw_openai_client",
    "run_customer_sources_monitoring",
    "settings",
    "split_regulation_into_chunks",
    "structured_llm_client",
]
