import json
import logging
import re
from dataclasses import dataclass, field
from typing import Protocol
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

from bs4 import BeautifulSoup, Tag  # type: ignore[import-untyped]
from lxml import etree  # type: ignore[import-untyped]
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import ScraperSource

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

_AUTO_STOP_EXTENSIONS: tuple[str, ...] = (
    *_STOP_URL_EXTENSIONS,
    ".pdf",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".ppt",
    ".pptx",
    ".xml",
    ".json",
    ".avi",
    ".mov",
    ".woff",
    ".woff2",
    ".ttf",
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

_SERVICE_ROUTE_MARKERS: tuple[str, ...] = (
    "/about",
    "/contacts",
    "/contact",
    "/tag/",
    "/tags/",
    "/page/",
    "/login",
    "/signin",
    "/signup",
    "/register",
    "/auth",
    "/privacy",
    "/policy",
    "/agreement",
    "/terms",
    "/advertising",
    "/search",
    "/rss",
    "/feed",
    "/cart",
    "/checkout",
    "/faq",
    "/help",
)

_SOCIAL_DOMAINS: tuple[str, ...] = (
    "vk.com",
    "t.me",
    "telegram.me",
    "youtube.com",
    "youtu.be",
    "facebook.com",
    "instagram.com",
    "linkedin.com",
    "ok.ru",
    "twitter.com",
    "x.com",
    "dzen.ru",
    "zen.yandex.ru",
    "wa.me",
    "whatsapp.com",
    "viber.com",
    "rutube.ru",
    "pinterest.com",
    "tiktok.com",
    "max.ru",
    "tenchat.ru",
    "vc.ru",
    "habr.com",
    "telegra.ph",
)

_TRACKING_QUERY_PARAMS: frozenset[str] = frozenset(
    {"fbclid", "yclid", "gclid", "erid", "ref", "from", "_openstat"}
)

_PAGINATION_QUERY_KEYS: frozenset[str] = frozenset({"page", "month", "year", "sort"})

_CYRILLIC_RE = re.compile(r"[а-яА-ЯёЁ]")
_RF_GEO_RE = re.compile(
    r"\b(?:russia|russian|moscow|saint[\s.\-]*petersburg|st\.?[\s\-]*petersburg|"
    r"petersburg|ekaterinburg|yekaterinburg|kazan|sochi|novosibirsk|"
    r"nizhny\s+novgorod|krasnodar|vladivostok|kaliningrad|samara|ufa|perm|rostov)\b",
    re.IGNORECASE,
)
_ONLINE_PHRASE_RE = re.compile(
    r"\b(?:online\s+(?:event|forum|lecture|webinar|conference|summit|symposium|"
    r"panel|talk|workshop|course|exhibition|session)|webinar|"
    r"virtual\s+(?:event|forum|conference|summit|exhibition))\b",
    re.IGNORECASE,
)

_B2C_AGE_RE = re.compile(r"(?<!\d)(?:0|3|4|6|12)\+")
_B2C_KEYWORDS_RE = re.compile(
    r"(?:\bспектакл|репродукц|\bконцерт|\bдетям\b|живопис|дегустац|экскурси)",
    re.IGNORECASE,
)
_B2B_STRONG_OVERRIDE_RE = re.compile(
    r"(?:форум|конференц|саммит|конгресс|\bb2b\b)",
    re.IGNORECASE,
)
_B2B_OVERRIDE_RE = re.compile(
    r"(?:форум|конференц|девелоп|строит|архитект|дизайн|интерьер|урбан|\bb2b\b|саммит|конгресс|промышлен)",
    re.IGNORECASE,
)
_GENERIC_CARD_LINK_TEXTS: frozenset[str] = frozenset(
    {
        "подробнее",
        "читать далее",
        "читать",
        "перейти",
        "смотреть",
        "more",
        "read more",
        "details",
        "бесплатно",
        "платно",
        "регистрация",
        "билеты",
        "участвовать",
        "купить билет",
        "free",
    }
)
_XML_ENCODING_RE = re.compile(r"^(<\?xml[^>]*?\sencoding=['\"])([^'\"]+)(['\"][^>]*\?>)", re.IGNORECASE)
_PAGE_SEGMENT_RE = re.compile(r"/page(?:/\d+)?/?$", re.IGNORECASE)


@dataclass(frozen=True)
class CustomerSourceConfig:
    """Декларативная конфигурация площадки мониторинга ГК «СКАРТ»."""

    source_key: str
    display_name: str
    catalog_urls: tuple[str, ...]
    card_url_patterns: tuple[str, ...] = ()
    exclude_url_patterns: tuple[str, ...] = ()
    adapter_type: str = "html_list"
    b2b_filter_enabled: bool = False
    russia_online_only: bool = True
    encoding: str = "utf-8"
    use_jina_reader: bool = False
    required_cookies: tuple[tuple[str, str], ...] = ()
    max_urls_per_run: int = 10
    is_enabled: bool = True
    is_builtin: bool = True

    @property
    def catalog_url(self) -> str:
        """Возвращает основной URL каталога (первый из catalog_urls) для обратной совместимости."""
        return self.catalog_urls[0] if self.catalog_urls else ""

    @classmethod
    def from_orm(cls, row: ScraperSource) -> "CustomerSourceConfig":
        """Создает конфигурацию из ORM-модели ScraperSource."""
        cookies_dict = row.required_cookies if isinstance(row.required_cookies, dict) else {}
        return cls(
            source_key=row.source_key,
            display_name=row.display_name,
            catalog_urls=tuple(str(u) for u in (row.catalog_urls or [])),
            card_url_patterns=tuple(str(p) for p in (row.card_url_patterns or [])),
            exclude_url_patterns=tuple(str(p) for p in (row.exclude_url_patterns or [])),
            adapter_type=row.adapter_type or "html_list",
            b2b_filter_enabled=bool(row.b2b_filter_enabled) if row.b2b_filter_enabled is not None else False,
            russia_online_only=bool(row.russia_online_only) if row.russia_online_only is not None else True,
            encoding=row.encoding or "utf-8",
            use_jina_reader=bool(row.use_jina_reader) if row.use_jina_reader is not None else False,
            required_cookies=tuple((str(k), str(v)) for k, v in cookies_dict.items()),
            max_urls_per_run=int(row.max_urls_per_run) if row.max_urls_per_run is not None else 10,
            is_enabled=bool(row.is_enabled) if row.is_enabled is not None else True,
            is_builtin=bool(row.is_builtin) if row.is_builtin is not None else False,
        )


@dataclass(frozen=True)
class DiscoveredCandidate:
    """Структурированный кандидат мероприятия со стадии Discovery (без затрат LLM)."""

    url: str
    title: str = ""
    snippet: str = ""
    source_key: str = ""
    is_digest: bool = False


@dataclass(frozen=True)
class DiscoveryResult:
    """Результат этапа Discovery по источнику: кандидаты и счетчики ручного pre-filter отсева."""

    candidates: list[DiscoveredCandidate] = field(default_factory=list)
    rejected_b2c: int = 0
    rejected_geo: int = 0


_EXPOMAP_CARD_PATTERNS: tuple[str, ...] = (
    r"^https?://(?:www\.)?expomap\.ru/(?:expo|conference)/[a-z0-9\-]+/?$",
)
_EXPOMAP_EXCLUDE_PATTERNS: tuple[str, ...] = (
    r"^https?://(?:www\.)?expomap\.ru/(?:expo|conference)/(?:city|country|theme|venue|202\d)/?$",
)

CUSTOMER_SOURCES_REGISTRY: tuple[CustomerSourceConfig, ...] = (
    CustomerSourceConfig(
        source_key="expomap_construction",
        display_name="Expomap — Строительство",
        catalog_urls=(
            "https://expomap.ru/expo/theme/stroitel-stvo/country/russia/",
            "https://expomap.ru/conference/theme/stroitel-stvo/country/russia/",
        ),
        card_url_patterns=_EXPOMAP_CARD_PATTERNS,
        exclude_url_patterns=_EXPOMAP_EXCLUDE_PATTERNS,
    ),
    CustomerSourceConfig(
        source_key="expomap_design",
        display_name="Expomap — Дизайн",
        catalog_urls=("https://expomap.ru/expo/theme/mebel-inter-er-dekor/country/russia/",),
        card_url_patterns=_EXPOMAP_CARD_PATTERNS,
        exclude_url_patterns=_EXPOMAP_EXCLUDE_PATTERNS,
    ),
    CustomerSourceConfig(
        source_key="architime",
        display_name="ARCHITIME",
        catalog_urls=("https://www.architime.ru/lecturexibition.htm",),
        card_url_patterns=(r"^https?://(?:www\.)?architime\.ru/activity/202\d/[a-z0-9_\-]+\.htm$",),
        encoding="windows-1251",
    ),
    CustomerSourceConfig(
        source_key="archi_ru",
        display_name="Архи.ру",
        catalog_urls=("https://archi.ru/events",),
        card_url_patterns=(r"^https?://(?:www\.)?archi\.ru/events/\d+/[a-z0-9_\-]+",),
        use_jina_reader=True,
    ),
    CustomerSourceConfig(
        source_key="helpinver",
        display_name="Хелпинвер",
        catalog_urls=("https://helpinver.com/events/",),
        card_url_patterns=(r"^https?://(?:www\.)?helpinver\.com/events/[a-z0-9_\-]+(?:\.php)?/?$",),
        required_cookies=(("beget", "begetok"),),
    ),
    CustomerSourceConfig(
        source_key="archdialog",
        display_name="АрхДиалог (Timepad)",
        catalog_urls=("https://archdialog.timepad.ru/events/",),
        card_url_patterns=(r"^https?://archdialog\.timepad\.ru/event/\d+/?$",),
        adapter_type="manual_only",
        is_enabled=False,
    ),
    CustomerSourceConfig(
        source_key="design_mate",
        display_name="Design Mate",
        catalog_urls=(
            "https://design-mate.ru/read/go",
            "https://design-mate.ru/zen",
        ),
        card_url_patterns=(
            r"^https?://(?:www\.)?design-mate\.ru/go/[a-z0-9_\-]+/[a-z0-9_\-]+/?$",
            r"^https?://(?:www\.)?design-mate\.ru/read/megapolis/[a-z0-9_\-]+/?$",
        ),
        b2b_filter_enabled=True,
    ),
    CustomerSourceConfig(
        source_key="votkuda",
        display_name="ВотКуда",
        catalog_urls=("https://votkuda.ru/moskva/vystavki/",),
        card_url_patterns=(r"^https?://(?:www\.)?votkuda\.ru/event/[a-z0-9_\-]+/?$",),
        b2b_filter_enabled=True,
        max_urls_per_run=5,
    ),
    CustomerSourceConfig(
        source_key="archdaily",
        display_name="ArchDaily",
        catalog_urls=("https://www.archdaily.com/tag/events.xml",),
        card_url_patterns=(r"^https?://(?:www\.)?archdaily\.com/\d+/[a-z0-9\-]+/?$",),
        adapter_type="rss",
        b2b_filter_enabled=True,
        russia_online_only=True,
    ),
)


class CatalogSourceScraperProtocol(Protocol):
    """Протокол адаптера обхода каталога внешней площадки (Discovery)."""

    async def fetch_catalog_urls(self, source: CustomerSourceConfig) -> list[str]: ...


# [DEV-STUB: Изолированный провайдер каталогов для автономных unit-тестов без сетевых запросов]
class StubCatalogSourceScraper:
    """
    Изолированный провайдер-заглушка для тестирования пайплайна мониторинга без выхода в интернет.
    """

    async def discover_catalog(self, source: CustomerSourceConfig) -> DiscoveryResult:
        """Возвращает пустой DiscoveryResult в автономном тестовом режиме."""
        logger.info(
            "[DEV-STUB SCRAPER] Автономный режим для %s (%s).",
            source.display_name,
            source.catalog_url,
        )
        return DiscoveryResult()

    async def fetch_catalog_urls(self, source: CustomerSourceConfig) -> list[str]:
        result = await self.discover_catalog(source)
        return [c.url for c in result.candidates]


async def ensure_builtin_scraper_sources(session: AsyncSession) -> list[ScraperSource]:
    """
    Идемпотентно добавляет недостающие встроенные площадки из CUSTOMER_SOURCES_REGISTRY в таблицу
    scraper_sources без перезаписи пользовательских флагов (is_enabled, max_urls_per_run) у существующих строк.
    """
    import app.services.scraper as scraper_pkg

    res = await session.execute(select(ScraperSource).order_by(ScraperSource.id))
    existing_rows = [row for row in res.scalars().all() if isinstance(row, ScraperSource)]
    existing_by_key = {row.source_key: row for row in existing_rows}

    created_rows: list[ScraperSource] = []
    for src in scraper_pkg.CUSTOMER_SOURCES_REGISTRY:
        if src.source_key in existing_by_key:
            continue
        row = ScraperSource(
            source_key=src.source_key,
            display_name=src.display_name,
            catalog_urls=list(src.catalog_urls),
            adapter_type=src.adapter_type,
            card_url_patterns=list(src.card_url_patterns),
            exclude_url_patterns=list(src.exclude_url_patterns),
            b2b_filter_enabled=src.b2b_filter_enabled,
            russia_online_only=src.russia_online_only,
            use_jina_reader=src.use_jina_reader,
            encoding=src.encoding,
            required_cookies=dict(src.required_cookies),
            max_urls_per_run=src.max_urls_per_run,
            is_enabled=src.is_enabled,
            is_builtin=src.is_builtin,
        )
        session.add(row)
        created_rows.append(row)

    if created_rows:
        await session.flush()

    return [*existing_rows, *created_rows]


def canonicalize_url(raw_url: str, base_url: str | None = None) -> str | None:
    """
    Канонизирует URL: оставляет только http/https, приводит netloc к lowercase,
    удаляет #fragment и трекинговые query-параметры (utm_*, fbclid, yclid, gclid, erid, ref, from, _openstat),
    сохраняя остальные значимые query-параметры.
    """
    href = (raw_url or "").strip()
    if not href or href.startswith("#"):
        return None
    low_href = href.lower()
    if low_href.startswith(("mailto:", "tel:", "javascript:", "data:")):
        return None

    abs_url = urljoin(base_url, href) if base_url else href
    parts = urlsplit(abs_url)
    scheme = parts.scheme.lower()
    if scheme not in ("http", "https") or not parts.netloc:
        return None

    hostname = (parts.hostname or "").lower()
    if not hostname:
        return None

    try:
        port = parts.port
    except ValueError:
        return None

    host_formatted = f"[{hostname}]" if ":" in hostname else hostname
    if port is not None and not (
        (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
    ):
        netloc = f"{host_formatted}:{port}"
    else:
        netloc = host_formatted

    if parts.query:
        kept_params = [
            (k, v)
            for k, v in parse_qsl(parts.query, keep_blank_values=True)
            if not (k.lower().startswith("utm_") or k.lower() in _TRACKING_QUERY_PARAMS)
        ]
        clean_query = urlencode(kept_params)
    else:
        clean_query = ""

    return urlunsplit((scheme, netloc, parts.path, clean_query, ""))


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


@dataclass(frozen=True)
class _RawDiscoveryItem:
    url: str
    title: str = ""
    snippet: str = ""
    category: str = ""
    context_text: str = ""
    is_rss: bool = False
    is_digest: bool = False
    is_heading: bool = False


def _local_tag_name(el: etree._Element) -> str:
    if not isinstance(el.tag, str):
        return ""
    return str(etree.QName(el).localname).lower()


def _strip_html_tags(text: str) -> str:
    if not text:
        return ""
    if "<" in text and ">" in text:
        return BeautifulSoup(text, "lxml").get_text(" ", strip=True)
    return " ".join(text.split())


def looks_like_xml_feed(raw_content: str, *, allow_xml_prolog_only: bool = False) -> bool:
    """Проверяет по содержимому, является ли ответ XML/RSS/Atom-лентой."""
    stripped = raw_content.lstrip("\ufeff\r\n\t ")
    if not stripped:
        return False
    head = stripped[:200].lower()
    if head.startswith(("<rss", "<feed")):
        return True
    if head.startswith("<?xml"):
        preview = stripped[:1000].lower()
        return "<rss" in preview or "<feed" in preview or allow_xml_prolog_only
    return False


def _is_xml_feed_content(raw_content: str, source: CustomerSourceConfig) -> bool:
    return looks_like_xml_feed(raw_content, allow_xml_prolog_only=source.adapter_type == "rss")


def _parse_xml_feed_items(raw_content: str) -> list[_RawDiscoveryItem]:
    """Безопасно парсит RSS 2.0 (<item>) и Atom (<entry>) через lxml без XXE и сетевых запросов."""
    stripped = raw_content.lstrip("\ufeff\r\n\t ")
    normalized_xml = _XML_ENCODING_RE.sub(r'\1utf-8\3', stripped, count=1)
    parser = etree.XMLParser(resolve_entities=False, no_network=True, recover=False)
    root = etree.fromstring(normalized_xml.encode("utf-8"), parser=parser)

    items: list[_RawDiscoveryItem] = []
    for node in root.iter():
        tag_name = _local_tag_name(node)
        if tag_name not in ("item", "entry"):
            continue

        title = ""
        link = ""
        description = ""
        pub_date = ""
        categories: list[str] = []
        guid_link = ""

        for child in node:
            cname = _local_tag_name(child)
            if not cname:
                continue
            ctext = "".join(child.itertext()).strip()
            if cname == "title" and not title:
                title = _strip_html_tags(ctext)
            elif cname == "link":
                href = (child.get("href") or "").strip()
                rel = (child.get("rel") or "").strip().lower()
                if href:
                    if not link or rel in ("", "alternate"):
                        link = href
                elif ctext and not link:
                    link = ctext
            elif cname == "guid" and ctext and (child.get("isPermaLink") or "").lower() != "false":
                guid_link = ctext
            elif cname in ("description", "summary", "content", "encoded", "full-text") and ctext:
                cleaned = _strip_html_tags(ctext)
                if len(cleaned) > len(description):
                    description = cleaned
            elif cname in ("pubdate", "published", "updated", "date") and ctext and not pub_date:
                pub_date = ctext
            elif cname == "category":
                term = (child.get("term") or "").strip()
                cat_val = _strip_html_tags(ctext) or term
                if cat_val:
                    categories.append(cat_val)

        target_link = link or guid_link
        if not target_link:
            continue

        cat_text = ", ".join(categories)
        snippet_parts = [p for p in (description[:400], f"[{cat_text}]" if cat_text else "", pub_date) if p]
        items.append(
            _RawDiscoveryItem(
                url=target_link,
                title=title,
                snippet=" | ".join(snippet_parts),
                category=cat_text,
                context_text=f"{title} {description} {cat_text}".strip(),
                is_rss=True,
            )
        )
    return items


def _passes_russia_online_geo(
    title: str,
    description: str,
    category: str,
    *,
    allow_global_online: bool = True,
) -> bool:
    """Фильтр РФ/онлайн для англоязычных/смешанных RSS-лент (для archdaily — строго только РФ)."""
    combined = f"{title} {description} {category}".strip()
    if not combined:
        return False
    if _CYRILLIC_RE.search(combined):
        return True
    if _RF_GEO_RE.search(combined):
        return True
    if not allow_global_online:
        return False
    if "online" in category.lower():
        return True
    return bool(_ONLINE_PHRASE_RE.search(combined))


def _is_obvious_b2c(text: str) -> bool:
    """
    0-токенный pre-filter: отсекает очевидный B2C.
    Возрастной тег 0+/3+/4+/6+/12+ отменяется только строгими B2B-маркерами
    (форум/конференц/саммит/конгресс/b2b), а не общими словами вроде 'дизайн'.
    """
    if not text:
        return False
    if _B2C_AGE_RE.search(text):
        return not _B2B_STRONG_OVERRIDE_RE.search(text)
    if _B2C_KEYWORDS_RE.search(text):
        return not _B2B_OVERRIDE_RE.search(text)
    return False


def _extract_single_card_context(a_tag: Tag) -> tuple[str, str]:
    """Извлекает заголовок ссылки и текст строго одной карточки-контейнера без захвата соседних карточек."""
    link_text = a_tag.get_text(" ", strip=True)
    if not link_text:
        img = a_tag.find("img")
        if isinstance(img, Tag):
            alt_val = img.get("alt")
            if isinstance(alt_val, str):
                link_text = alt_val.strip()
    if not link_text:
        title_attr = a_tag.get("title")
        if isinstance(title_attr, str):
            link_text = title_attr.strip()

    best_container: Tag | None = None
    cur: Tag | None = a_tag.parent if isinstance(a_tag.parent, Tag) else None
    for _ in range(4):
        if cur is None or cur.name in ("body", "main", "html", "[document]", "ul", "ol", "table", "tbody", "section"):
            break
        distinct_hrefs = {
            str(tag.get("href") or "").split("#", 1)[0].strip()
            for tag in cur.find_all("a", href=True)
            if str(tag.get("href") or "").strip()
        }
        cur_text = cur.get_text(" ", strip=True)
        if len(distinct_hrefs) > 4 or len(cur_text) > 800:
            break
        best_container = cur
        if cur.name in ("article", "li", "tr"):
            break
        cur = cur.parent if isinstance(cur.parent, Tag) else None

    if best_container is not None:
        card_text = best_container.get_text(" ", strip=True)
        if not link_text or link_text.lower() in _GENERIC_CARD_LINK_TEXTS:
            heading = best_container.find(["h1", "h2", "h3", "h4"])
            if isinstance(heading, Tag):
                heading_text = heading.get_text(" ", strip=True)
                if heading_text:
                    link_text = heading_text
        return link_text, card_text[:500]

    return link_text, link_text[:500]


def _host_without_www(url: str) -> str:
    host = (urlsplit(url).hostname or "").lower()
    return host.removeprefix("www.")


def _passes_auto_extractor_filters(
    norm_url: str,
    allowed_hosts: set[str],
    catalog_roots: set[str],
) -> bool:
    """Фильтр Варианта А (без regex): тот же домен, без служебных маршрутов, медиа и пагинации."""
    parts = urlsplit(norm_url)
    host = (parts.hostname or "").lower()
    base_domain = host.removeprefix("www.")
    if not base_domain or base_domain not in allowed_hosts:
        return False
    if any(base_domain == soc or base_domain.endswith(f".{soc}") for soc in _SOCIAL_DOMAINS):
        return False

    path_low = parts.path.lower()
    if (norm_url.rstrip("/") in catalog_roots or path_low in ("", "/")) and not parts.query:
        return False
    if any(path_low.endswith(ext) for ext in _AUTO_STOP_EXTENSIONS):
        return False
    if any(marker in path_low for marker in _SERVICE_ROUTE_MARKERS) or _PAGE_SEGMENT_RE.search(path_low):
        return False

    if parts.query:
        for key, _ in parse_qsl(parts.query, keep_blank_values=True):
            k_low = key.lower()
            if k_low in _PAGINATION_QUERY_KEYS or k_low.startswith("pagen"):
                return False

    return True


def _collect_html_and_markdown_items(
    raw_content: str,
    source: CustomerSourceConfig,
    base_url: str,
) -> list[_RawDiscoveryItem]:
    items: list[_RawDiscoveryItem] = []
    content_lower = raw_content.lower()
    use_auto = len(source.card_url_patterns) == 0

    if "<a" in content_lower or "<script" in content_lower or "<div" in content_lower:
        soup = BeautifulSoup(raw_content, "lxml")
        if use_auto:
            for tag in soup(["header", "nav", "footer", "aside", "script", "style", "noscript"]):
                tag.decompose()
            main_tag = soup.find("main") or soup.find(attrs={"role": "main"})
            root: BeautifulSoup | Tag = (
                main_tag
                if isinstance(main_tag, Tag) and main_tag.find("a", href=True)
                else (soup.body if isinstance(soup.body, Tag) else soup)
            )
            for a_tag in root.find_all("a", href=True):
                href_val = a_tag.get("href")
                if isinstance(href_val, str) and href_val.strip():
                    title, snippet = _extract_single_card_context(a_tag)
                    is_heading = (
                        a_tag.find_parent(["h1", "h2", "h3", "h4"]) is not None
                        or a_tag.find(["h1", "h2", "h3", "h4"]) is not None
                    )
                    items.append(
                        _RawDiscoveryItem(
                            url=href_val,
                            title=title,
                            snippet=snippet,
                            context_text=snippet or title,
                            is_heading=is_heading,
                        )
                    )
        else:
            for a_tag in soup.find_all("a", href=True):
                href_val = a_tag.get("href")
                if isinstance(href_val, str) and href_val.strip():
                    title, snippet = _extract_single_card_context(a_tag)
                    is_heading = (
                        a_tag.find_parent(["h1", "h2", "h3", "h4"]) is not None
                        or a_tag.find(["h1", "h2", "h3", "h4"]) is not None
                    )
                    items.append(
                        _RawDiscoveryItem(
                            url=href_val,
                            title=title,
                            snippet=snippet,
                            context_text=snippet or title,
                            is_heading=is_heading,
                        )
                    )
            for ld_url in _extract_urls_from_ld_json(soup):
                items.append(_RawDiscoveryItem(url=ld_url))

    md_lines = raw_content.splitlines()
    for idx, line in enumerate(md_lines):
        if "](" not in line:
            continue
        ctx_slice = " ".join(
            part.strip()
            for part in md_lines[max(0, idx - 1) : min(len(md_lines), idx + 2)]
            if part.strip()
        )
        for match in re.finditer(r"\[([^\]]*)\]\((https?://[^\s\)\"']+)\)", line):
            md_title = match.group(1).strip()
            md_url = match.group(2).strip()
            items.append(
                _RawDiscoveryItem(
                    url=md_url,
                    title=md_title,
                    snippet=ctx_slice[:500],
                    context_text=ctx_slice,
                )
            )
        # Покрывает вложенные Markdown-конструкции Jina вроде [![alt](img)](url)
        for match in re.finditer(r"\]\((https?://[^\s\)\"']+)\)", line):
            bare_url = match.group(1).strip()
            items.append(
                _RawDiscoveryItem(
                    url=bare_url,
                    snippet=ctx_slice[:500],
                    context_text=ctx_slice,
                )
            )

    if use_auto and not items and base_url:
        return []
    return items


def _title_informativeness_score(title: str, is_heading: bool) -> tuple[int, int]:
    """Оценивает информативность заголовка ссылки, чтобы служебные бейджи не перебивали реальный title."""
    cleaned = " ".join((title or "").split())
    if not cleaned:
        return (-1, 0)
    normalized = cleaned.lower().strip(" .!?:;»«\"'")
    if normalized in _GENERIC_CARD_LINK_TEXTS or re.fullmatch(r"[\d\s₽$€+.,\-–—/]+", cleaned):
        return (0, len(cleaned))
    if is_heading and 3 <= len(cleaned) <= 220:
        return (3, len(cleaned))
    if 10 <= len(cleaned) <= 220:
        return (2, len(cleaned))
    return (1, min(len(cleaned), 220))


def _merge_raw_discovery_items(
    existing: _RawDiscoveryItem,
    incoming: _RawDiscoveryItem,
) -> _RawDiscoveryItem:
    """Объединяет дубликаты одной карточки, сохраняя лучший заголовок и наиболее полный контекст."""
    ex_score = _title_informativeness_score(existing.title, existing.is_heading)
    in_score = _title_informativeness_score(incoming.title, incoming.is_heading)
    use_incoming_title = in_score > ex_score

    best_title = incoming.title if use_incoming_title else existing.title
    best_is_heading = incoming.is_heading if use_incoming_title else existing.is_heading
    best_snippet = incoming.snippet if len(incoming.snippet) > len(existing.snippet) else existing.snippet
    best_category = incoming.category if len(incoming.category) > len(existing.category) else existing.category

    ex_ctx = existing.context_text.strip()
    in_ctx = incoming.context_text.strip()
    if not ex_ctx:
        best_context = in_ctx
    elif not in_ctx or in_ctx in ex_ctx:
        best_context = ex_ctx
    elif ex_ctx in in_ctx:
        best_context = in_ctx
    else:
        best_context = f"{ex_ctx} {in_ctx}"[:1000]

    return _RawDiscoveryItem(
        url=existing.url,
        title=best_title,
        snippet=best_snippet,
        category=best_category,
        context_text=best_context,
        is_rss=existing.is_rss or incoming.is_rss,
        is_digest=existing.is_digest or incoming.is_digest,
        is_heading=best_is_heading,
    )


def extract_discovery_candidates(
    raw_content: str,
    source: CustomerSourceConfig,
    *,
    base_url: str | None = None,
) -> DiscoveryResult:
    """
    Выполняет content-aware Discovery-разбор каталога/RSS:
    1. Детектирует XML/RSS (или HTML/Markdown).
    2. Применяет card_url_patterns или Вариант А авто-экстрактор (если card_url_patterns пуст).
    3. Применяет exclude_url_patterns после позитивных правил.
    4. Объединяет дубликаты одного dedup_key с выбором самого информативного title/snippet (порядок первого появления).
    5. Применяет гео-фильтр (для RSS с russia_online_only=True; для archdaily — строго РФ) и 0-токенный B2C pre-filter.
    """
    if not raw_content or not raw_content.strip():
        return DiscoveryResult()

    effective_base = base_url or source.catalog_url
    catalog_roots = {
        u.rstrip("/")
        for u in (effective_base, *source.catalog_urls)
        if u and u.strip()
    }
    allowed_hosts = {
        h for h in (_host_without_www(u) for u in (effective_base, *source.catalog_urls)) if h
    }

    if _is_xml_feed_content(raw_content, source):
        try:
            raw_items = _parse_xml_feed_items(raw_content)
        except etree.XMLSyntaxError:
            logger.warning("Некорректный XML/RSS ответ для %s (%s)", source.source_key, effective_base)
            raw_items = _collect_html_and_markdown_items(raw_content, source, effective_base)
    else:
        raw_items = _collect_html_and_markdown_items(raw_content, source, effective_base)

    compiled_card = [re.compile(pat, re.IGNORECASE) for pat in source.card_url_patterns]
    compiled_exclude = [re.compile(pat, re.IGNORECASE) for pat in source.exclude_url_patterns]

    merged_by_key: dict[str, tuple[str, _RawDiscoveryItem]] = {}
    for item in raw_items:
        norm_url = canonicalize_url(item.url, effective_base)
        if norm_url is None:
            continue
        dedup_key = norm_url.rstrip("/")
        if dedup_key in catalog_roots:
            continue
        if any(urlsplit(norm_url).path.lower().endswith(ext) for ext in _STOP_URL_EXTENSIONS):
            continue

        if compiled_card:
            if not any(regex.search(norm_url) for regex in compiled_card):
                continue
        else:
            if not _passes_auto_extractor_filters(norm_url, allowed_hosts, catalog_roots):
                continue

        if compiled_exclude and any(regex.search(norm_url) for regex in compiled_exclude):
            continue

        existing_entry = merged_by_key.get(dedup_key)
        if existing_entry is None:
            merged_by_key[dedup_key] = (norm_url, item)
        else:
            first_norm_url, existing_item = existing_entry
            merged_by_key[dedup_key] = (
                first_norm_url,
                _merge_raw_discovery_items(existing_item, item),
            )

    candidates: list[DiscoveredCandidate] = []
    rejected_b2c = 0
    rejected_geo = 0
    allow_global_online = source.source_key != "archdaily"

    for norm_url, item in merged_by_key.values():
        if (
            (item.is_rss or source.adapter_type == "rss")
            and source.russia_online_only
            and not _passes_russia_online_geo(
                item.title,
                item.snippet,
                item.category,
                allow_global_online=allow_global_online,
            )
        ):
            rejected_geo += 1
            continue

        if source.b2b_filter_enabled:
            b2c_text = item.context_text or f"{item.title} {item.snippet}".strip()
            if _is_obvious_b2c(b2c_text):
                rejected_b2c += 1
                continue

        is_digest = (
            item.is_digest
            or source.adapter_type == "html_digest"
            or "/read/megapolis/" in norm_url.lower()
        )
        candidates.append(
            DiscoveredCandidate(
                url=norm_url,
                title=item.title,
                snippet=item.snippet,
                source_key=source.source_key,
                is_digest=is_digest,
            )
        )

    return DiscoveryResult(
        candidates=candidates,
        rejected_b2c=rejected_b2c,
        rejected_geo=rejected_geo,
    )


def extract_filtered_card_urls(raw_content: str, source: CustomerSourceConfig) -> list[str]:
    """
    Извлекает ссылки на карточки мероприятий из HTML, XML/RSS или Markdown (включая r.jina.ai)
    с применением card_url_patterns (или авто-экстрактора) и exclude_url_patterns.
    """
    return [c.url for c in extract_discovery_candidates(raw_content, source).candidates]
