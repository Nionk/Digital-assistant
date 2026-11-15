import json
import logging
import re
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urljoin, urlsplit, urlunsplit

from bs4 import BeautifulSoup  # type: ignore[import-untyped]

logger = logging.getLogger(__name__)

_STOP_URL_EXTENSIONS: tuple[str, ...] = (
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".svg",
    ".webp",
    ".ico",
    ".css",
    ".js",
    ".zip",
    ".rar",
    ".mp4",
    ".mp3",
)

_STOP_URL_SUBSTRINGS: tuple[str, ...] = (
    "/login",
    "/register",
    "/privacy",
    "/policy",
    "/agreement",
    "/contacts",
    "/about",
    "/advertising",
    "mailto:",
    "tel:",
    "javascript:",
)


@dataclass(frozen=True)
class CustomerSourceConfig:
    """Декларативная конфигурация одной из 9 утвержденных площадок мониторинга ГК «СКАРТ»."""

    source_key: str
    display_name: str
    catalog_url: str
    card_url_patterns: tuple[str, ...]
    encoding: str = "utf-8"
    use_jina_reader: bool = False
    required_cookies: tuple[tuple[str, str], ...] = ()


CUSTOMER_SOURCES_REGISTRY: tuple[CustomerSourceConfig, ...] = (
    CustomerSourceConfig(
        source_key="expomap_construction",
        display_name="Expomap — Строительство",
        catalog_url="https://expomap.ru/expo/city/moscow/theme/stroitelstvo/",
        card_url_patterns=(r"^https?://(?:www\.)?expomap\.ru/expo/[a-z0-9\-]+/?$",),
    ),
    CustomerSourceConfig(
        source_key="expomap_design",
        display_name="Expomap — Дизайн",
        catalog_url="https://expomap.ru/expo/city/moscow/theme/dizain/",
        card_url_patterns=(r"^https?://(?:www\.)?expomap\.ru/expo/[a-z0-9\-]+/?$",),
    ),
    CustomerSourceConfig(
        source_key="architime",
        display_name="ARCHITIME",
        catalog_url="https://www.architime.ru/lecturexibition.htm",
        card_url_patterns=(r"^https?://(?:www\.)?architime\.ru/activity/202\d/[a-z0-9_\-]+\.htm$",),
        encoding="windows-1251",
    ),
    CustomerSourceConfig(
        source_key="archi_ru",
        display_name="Архи.ру",
        catalog_url="https://archi.ru/events",
        card_url_patterns=(r"^https?://(?:www\.)?archi\.ru/events/\d+/[a-z0-9_\-]+",),
        use_jina_reader=True,
    ),
    CustomerSourceConfig(
        source_key="helpinver",
        display_name="Хелпинвер",
        catalog_url="https://helpinver.com/events/",
        card_url_patterns=(r"^https?://(?:www\.)?helpinver\.com/events/[a-z0-9_\-]+/?$",),
        required_cookies=(("beget", "begetok"),),
    ),
    CustomerSourceConfig(
        source_key="archdialog",
        display_name="АрхДиалог (Timepad)",
        catalog_url="https://archdialog.timepad.ru/events/",
        card_url_patterns=(r"^https?://archdialog\.timepad\.ru/event/\d+/?$",),
    ),
    CustomerSourceConfig(
        source_key="design_mate",
        display_name="Design Mate",
        catalog_url="https://design-mate.ru/read/go",
        card_url_patterns=(r"^https?://(?:www\.)?design-mate\.ru/read/go/[a-z0-9_\-]+/?$",),
    ),
    CustomerSourceConfig(
        source_key="votkuda",
        display_name="ВотКуда",
        catalog_url="https://votkuda.ru/moskva/vyistavki",
        card_url_patterns=(r"^https?://(?:www\.)?votkuda\.ru/[a-z\-]+/vyistavki/[a-z0-9_\-]+/?$",),
    ),
    CustomerSourceConfig(
        source_key="archdaily",
        display_name="ArchDaily",
        catalog_url="https://www.archdaily.com/tag/events",
        card_url_patterns=(r"^https?://(?:www\.)?archdaily\.com/\d+/[a-z0-9\-]+/?$",),
    ),
)


class CatalogSourceScraperProtocol(Protocol):
    """Протокол адаптера обхода каталога внешней площадки (2-Hop Scraper)."""

    async def fetch_catalog_urls(self, source: CustomerSourceConfig) -> list[str]: ...


# [DEV-STUB: Изолированный провайдер каталогов для автономных unit-тестов без сетевых запросов]
class StubCatalogSourceScraper:
    """
    Изолированный провайдер-заглушка для тестирования пайплайна мониторинга без выхода в интернет.
    """

    async def fetch_catalog_urls(self, source: CustomerSourceConfig) -> list[str]:
        logger.info(
            "[DEV-STUB SCRAPER] Автономный режим для %s (%s).",
            source.display_name,
            source.catalog_url,
        )
        return []


def _normalize_clean_url(raw_href: str, base_url: str) -> str | None:
    """Приводит ссылку к абсолютному виду без fragment/query и отсекает невалидные схемы/расширения."""
    href = raw_href.strip()
    if not href or href.startswith("#"):
        return None
    low_href = href.lower()
    if any(sub in low_href for sub in _STOP_URL_SUBSTRINGS):
        return None

    abs_url = urljoin(base_url, href)
    parts = urlsplit(abs_url)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        return None

    clean_path = parts.path
    if any(clean_path.lower().endswith(ext) for ext in _STOP_URL_EXTENSIONS):
        return None

    normalized = urlunsplit((parts.scheme, parts.netloc, clean_path, "", ""))
    if normalized.rstrip("/") == base_url.rstrip("/"):
        return None
    return normalized


def _extract_urls_from_ld_dict(obj: dict[str, object]) -> list[str]:
    """Извлекает URL из одного объекта JSON-LD (включая вложенный itemListElement)."""
    urls: list[str] = []
    url_val = obj.get("url")
    if isinstance(url_val, str) and url_val.strip():
        urls.append(url_val.strip())

    item_list = obj.get("itemListElement")
    if not isinstance(item_list, list):
        return urls

    for el in item_list:
        if not isinstance(el, dict):
            continue
        nested_item = el.get("item")
        el_url = el.get("url") or (nested_item.get("url") if isinstance(nested_item, dict) else None)
        if isinstance(el_url, str) and el_url.strip():
            urls.append(el_url.strip())
    return urls


def _extract_urls_from_ld_json(soup: BeautifulSoup) -> list[str]:
    """Извлекает URL карточек мероприятий из блоков Schema.org (<script type='application/ld+json'>)."""
    extracted: list[str] = []
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw_json = (script.string or "").strip()
        if not raw_json:
            continue
        try:
            payload = json.loads(raw_json)
        except json.JSONDecodeError:
            continue

        items = payload if isinstance(payload, list) else [payload]
        for obj in items:
            if isinstance(obj, dict):
                extracted.extend(_extract_urls_from_ld_dict(obj))
    return extracted


def _collect_raw_links(raw_content: str) -> list[str]:
    """Собирает все сырые ссылки из HTML (<a>, JSON-LD) и Markdown-разметки."""
    raw_candidates: list[str] = []
    content_lower = raw_content.lower()
    if "<a" in content_lower or "<script" in content_lower:
        soup = BeautifulSoup(raw_content, "lxml")
        raw_candidates.extend(_extract_urls_from_ld_json(soup))
        for a_tag in soup.find_all("a", href=True):
            href_val = a_tag.get("href")
            if isinstance(href_val, str):
                raw_candidates.append(href_val)

    raw_candidates.extend(re.findall(r"\]\((https?://[^\s\)\"']+)\)", raw_content))
    return raw_candidates


def extract_filtered_card_urls(raw_content: str, source: CustomerSourceConfig) -> list[str]:
    """
    Извлекает ссылки на карточки мероприятий из HTML или Markdown (включая ответ r.jina.ai)
    и строго фильтрует их по декларативным regex-паттернам source.card_url_patterns.
    """
    raw_candidates = _collect_raw_links(raw_content)
    compiled_patterns = [re.compile(pat, re.IGNORECASE) for pat in source.card_url_patterns]
    matched_urls: list[str] = []
    seen: set[str] = set()

    for cand in raw_candidates:
        norm_url = _normalize_clean_url(cand, source.catalog_url)
        if norm_url is None or norm_url in seen:
            continue
        if any(regex.search(norm_url) for regex in compiled_patterns):
            seen.add(norm_url)
            matched_urls.append(norm_url)

    return matched_urls
