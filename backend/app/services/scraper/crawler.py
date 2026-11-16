import asyncio
import inspect
import json
import logging
import re
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlsplit

import httpx
from bs4 import BeautifulSoup, Tag  # type: ignore[import-untyped]
from instructor.core import InstructorError
from markdownify import markdownify as html_to_markdown  # type: ignore[import-untyped]
from openai import APIError
from pydantic import BaseModel, Field

from app.services.scraper import fetcher as fetcher_mod
from app.services.scraper.ingestion import MAX_DOSSIER_CHARS
from app.services.scraper.pdf_reader import OcrBudgetTracker, VisionOCRProviderProtocol
from app.services.scraper.sources import (
    _SOCIAL_DOMAINS,
    _STOP_URL_EXTENSIONS,
    CustomerSourceConfig,
    DiscoveredCandidate,
    _is_obvious_b2c,
    canonicalize_url,
)

logger = logging.getLogger(__name__)

_MAX_NAV_CANDIDATE_LINKS: int = 40
_MAX_HTML_SUBPAGES: int = 2
_MAX_PDF_FILES: int = 2

_AGGREGATOR_AND_TICKETING_DOMAINS: tuple[str, ...] = (
    "expomap.ru",
    "architime.ru",
    "archi.ru",
    "helpinver.com",
    "design-mate.ru",
    "votkuda.ru",
    "archdaily.com",
    "timepad.ru",
    "afisha.ru",
    "kassir.ru",
    "ticketland.ru",
    "leader-id.ru",
    "runet-id.com",
)

_BLOCKED_NOISE_DOMAINS: tuple[str, ...] = (
    *_SOCIAL_DOMAINS,
    "top.mail.ru",
    "yadro.ru",
    "mc.yandex.ru",
    "metrika.yandex.ru",
    "maps.yandex.ru",
    "googletagmanager.com",
    "google-analytics.com",
    "doubleclick.net",
    "liveinternet.ru",
    "rambler.ru",
    "google.com",
    "google.ru",
    "maps.google.com",
    "2gis.ru",
    "apps.apple.com",
    "play.google.com",
    "r.jina.ai",
    "schema.org",
    "w3.org",
    "fonts.googleapis.com",
    "fonts.gstatic.com",
)

_AGGREGATOR_BOILERPLATE_MARKERS: tuple[str, ...] = (
    "mediakit",
    "media-kit",
    "media_kit",
    "reklama",
    "advertising",
    "privacy",
    "policy",
    "agreement",
    "cookie",
)

_OFFICIAL_STRONG_MARKERS: tuple[str, ...] = (
    "официальный сайт",
    "сайт мероприятия",
    "сайт события",
    "сайт форума",
    "сайт выставки",
    "сайт конференции",
    "сайт организатора",
    "official site",
    "official website",
)

_OFFICIAL_MEDIUM_MARKERS: tuple[str, ...] = (
    "подробнее на сайте",
    "перейти на сайт",
    "страница мероприятия",
    "регистрация",
    "участие",
    "купить билет",
    "билеты",
    "тарифы",
    "программа",
    "сайт",
    "website",
)

_NAV_POSITIVE_KEYWORDS: tuple[tuple[str, int], ...] = (
    ("тариф", 10),
    ("стоимост", 10),
    ("прайс", 10),
    ("price", 10),
    ("pricing", 10),
    ("tariff", 10),
    ("участ", 8),
    ("participation", 8),
    ("спикер", 7),
    ("speaker", 7),
    ("делегат", 7),
    ("спонсор", 7),
    ("sponsor", 7),
    ("программ", 7),
    ("program", 7),
    ("schedule", 7),
    ("регламент", 8),
    ("regulation", 8),
    ("пакет", 6),
    ("билет", 6),
    ("ticket", 6),
    ("условия", 6),
    ("аккредитац", 5),
    ("регистрац", 5),
    ("register", 5),
    ("презентац", 5),
    ("брошюр", 5),
    ("кп", 4),
    (".pdf", 6),
)

_NAV_NEGATIVE_KEYWORDS: tuple[str, ...] = (
    "privacy",
    "policy",
    "политик",
    "cookie",
    "login",
    "signin",
    "signup",
    "cart",
    "checkout",
    "галерея",
    "фото",
    "архив",
    "archive",
)

_DIGEST_B2B_KEYWORDS: tuple[str, ...] = (
    "форум",
    "конференц",
    "выставк",
    "архитект",
    "дизайн",
    "интерьер",
    "девелоп",
    "строит",
    "урбан",
    "инженер",
    "бизнес",
    "саммит",
    "конгресс",
    "круглый стол",
    "программ",
    "регистрац",
    "тариф",
    "стоимост",
    "билет",
    "лекц",
    "дискусс",
)


class OrganizerLinksSelection(BaseModel):
    """Результат навигации AI Link Navigator (LLM-2) по сайту организатора."""

    html_subpage_urls: list[str] = Field(
        default_factory=list,
        description="До 2 URL HTML-подстраниц организатора (тарифы, участие, программа, регламент).",
    )
    pdf_urls: list[str] = Field(
        default_factory=list,
        description="До 2 URL PDF-документов (коммерческое предложение, прайс-лист, программа, регламент).",
    )


@dataclass(frozen=True)
class CollectedEventDossier:
    """Единое структурированное досье события после 2-Hop краулинга и чтения PDF."""

    dossier_text: str
    source_urls: list[str] = field(default_factory=list)
    official_site_url: str | None = None
    warnings: list[str] = field(default_factory=list)

    @property
    def collected_source_urls(self) -> list[str]:
        return self.source_urls


@dataclass(frozen=True)
class _LinkCandidate:
    url: str
    label: str
    context: str
    is_pdf: bool
    score: int


def _url_dedup_key(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme.lower()}://{parts.netloc.lower()}{parts.path.rstrip('/')}?{parts.query}"


def _host_matches_domain(host: str, domain: str) -> bool:
    clean_host = host.lower().removeprefix("www.")
    clean_dom = domain.lower().removeprefix("www.")
    return clean_host == clean_dom or clean_host.endswith(f".{clean_dom}")


def _is_blocked_external_url(url: str) -> bool:
    parts = urlsplit(url)
    if parts.scheme.lower() not in ("http", "https") or not parts.hostname:
        return True
    host = parts.hostname.lower()
    if any(_host_matches_domain(host, dom) for dom in _BLOCKED_NOISE_DOMAINS):
        return True
    path_low = parts.path.lower()
    if (
        (_host_matches_domain(host, "yandex.ru") or _host_matches_domain(host, "ya.ru"))
        and (path_low in ("", "/") or path_low.startswith(("/maps", "/clck", "/poll", "/search")))
    ):
        return True
    return any(path_low.endswith(ext) for ext in _STOP_URL_EXTENSIONS)


def _is_aggregator_or_ticketing(url: str, extra_aggregator_hosts: set[str]) -> bool:
    host = (urlsplit(url).hostname or "").lower()
    if not host:
        return True
    if any(_host_matches_domain(host, dom) for dom in _AGGREGATOR_AND_TICKETING_DOMAINS):
        return True
    return any(_host_matches_domain(host, dom) for dom in extra_aggregator_hosts)


def _is_aggregator_boilerplate(url: str) -> bool:
    low = url.lower()
    return any(marker in low for marker in _AGGREGATOR_BOILERPLATE_MARKERS)


def _same_organizer_domain(candidate_url: str, organizer_url: str) -> bool:
    cand_host = (urlsplit(candidate_url).hostname or "").lower().removeprefix("www.")
    org_host = (urlsplit(organizer_url).hostname or "").lower().removeprefix("www.")
    if not cand_host or not org_host:
        return False
    return (
        cand_host == org_host
        or cand_host.endswith(f".{org_host}")
        or org_host.endswith(f".{cand_host}")
    )


def _split_ld_json_and_body(agg_markdown: str) -> tuple[list[object], str]:
    marker = "--- SCHEMA.ORG LD+JSON ---"
    stripped = agg_markdown.lstrip()
    if not stripped.startswith(marker):
        return [], agg_markdown

    rest = stripped[len(marker) :].lstrip()
    decoder = json.JSONDecoder()
    ld_objects: list[object] = []
    while rest and rest[0] in ("{", "["):
        try:
            obj, idx = decoder.raw_decode(rest)
            ld_objects.append(obj)
            rest = rest[idx:].lstrip()
        except json.JSONDecodeError:
            break
    return ld_objects, rest


_IGNORED_LD_URL_PARENTS: frozenset[str] = frozenset(
    {"location", "venue", "image", "logo", "publisher", "author", "provider"}
)


def _collect_ld_json_urls(
    obj: object,
    *,
    offer_urls: list[str],
    organizer_urls: list[str],
    weak_urls: list[str],
    context: str = "",
) -> None:
    if isinstance(obj, list):
        for item in obj:
            _collect_ld_json_urls(
                item,
                offer_urls=offer_urls,
                organizer_urls=organizer_urls,
                weak_urls=weak_urls,
                context=context,
            )
        return
    if not isinstance(obj, dict):
        return

    for key, val in obj.items():
        k_low = str(key).lower()
        if k_low in ("offers", "organizer"):
            _collect_ld_json_urls(
                val,
                offer_urls=offer_urls,
                organizer_urls=organizer_urls,
                weak_urls=weak_urls,
                context=k_low,
            )
        elif k_low in _IGNORED_LD_URL_PARENTS:
            continue
        elif k_low == "url":
            if isinstance(val, str) and val.strip():
                if context == "offers":
                    offer_urls.append(val.strip())
                elif context == "organizer":
                    organizer_urls.append(val.strip())
                else:
                    weak_urls.append(val.strip())
        elif k_low == "sameas":
            items = val if isinstance(val, list) else [val]
            for item in items:
                if isinstance(item, str) and item.strip():
                    if context == "organizer":
                        organizer_urls.append(item.strip())
                    else:
                        weak_urls.append(item.strip())
        elif isinstance(val, (dict, list)):
            _collect_ld_json_urls(
                val,
                offer_urls=offer_urls,
                organizer_urls=organizer_urls,
                weak_urls=weak_urls,
                context=context,
            )


def _extract_markdown_links_with_context(
    md_text: str,
    base_url: str,
) -> list[tuple[str, str, str]]:
    results: list[tuple[str, str, str]] = []
    for line in md_text.splitlines():
        line_clean = " ".join(line.split())
        if not line_clean:
            continue
        found_in_line: set[str] = set()
        for match in re.finditer(r"\[([^\]]*)\]\((https?://[^\s\)\"']+)\)", line):
            label = " ".join(match.group(1).split())
            raw_url = match.group(2).strip()
            norm = canonicalize_url(raw_url, base_url)
            if norm:
                found_in_line.add(norm)
                results.append((norm, label, line_clean))
        for match in re.finditer(r"(?<!\()(https?://[^\s\)\]>\"']+)", line):
            raw_url = match.group(1).rstrip(".,;:!?")
            norm = canonicalize_url(raw_url, base_url)
            if norm and norm not in found_in_line:
                results.append((norm, "", line_clean))
    return results


def _discover_official_site_and_card_pdfs(
    agg_markdown: str,
    candidate: DiscoveredCandidate,
    source: CustomerSourceConfig,
) -> tuple[str | None, list[str]]:
    ld_objects, body_md = _split_ld_json_and_body(agg_markdown)
    extra_agg_hosts = {
        (urlsplit(u).hostname or "").lower().removeprefix("www.")
        for u in (candidate.url, *source.catalog_urls)
        if u and urlsplit(u).hostname
    }
    card_key = _url_dedup_key(candidate.url)

    offer_raw: list[str] = []
    organizer_raw: list[str] = []
    weak_ld_raw: list[str] = []
    for obj in ld_objects:
        _collect_ld_json_urls(
            obj,
            offer_urls=offer_raw,
            organizer_urls=organizer_raw,
            weak_urls=weak_ld_raw,
        )

    card_pdf_urls: list[str] = []
    seen_pdfs: set[str] = set()

    def _maybe_add_pdf(url: str) -> bool:
        if not urlsplit(url).path.lower().endswith(".pdf"):
            return False
        if _is_blocked_external_url(url) or _is_aggregator_boilerplate(url):
            return True
        k = _url_dedup_key(url)
        if k not in seen_pdfs:
            seen_pdfs.add(k)
            card_pdf_urls.append(url)
        return True

    def _is_valid_official_url(url: str) -> bool:
        if _url_dedup_key(url) == card_key:
            return False
        if _is_blocked_external_url(url):
            return False
        if _is_aggregator_or_ticketing(url, extra_agg_hosts):
            return False
        return not _is_aggregator_boilerplate(url)

    def _filter_ld_group(raw_list: list[str]) -> list[str]:
        filtered: list[str] = []
        for raw_u in raw_list:
            norm = canonicalize_url(raw_u, candidate.url)
            if not norm:
                continue
            if _maybe_add_pdf(norm):
                continue
            if _is_valid_official_url(norm):
                filtered.append(norm)
        return filtered

    offer_candidates = _filter_ld_group(offer_raw)
    organizer_candidates = _filter_ld_group(organizer_raw)
    weak_ld_candidates = _filter_ld_group(weak_ld_raw)

    scored_body_candidates: list[tuple[int, int, str]] = []
    for idx, (norm, label, ctx) in enumerate(_extract_markdown_links_with_context(body_md, candidate.url)):
        if _maybe_add_pdf(norm):
            continue
        if not _is_valid_official_url(norm):
            continue

        combined_low = f"{label} {ctx}".lower()
        score = 1
        if any(m in combined_low for m in _OFFICIAL_STRONG_MARKERS):
            score += 12
        elif any(m in combined_low for m in _OFFICIAL_MEDIUM_MARKERS):
            score += 6

        parts = urlsplit(norm)
        path_low = parts.path.lower()
        if path_low in ("", "/") or len(path_low.strip("/").split("/")) <= 1:
            score += 2
        if any(bad in path_low for bad in ("/share", "/intent", "/login", "/privacy", "/policy", "/terms")):
            score -= 10
        scored_body_candidates.append((score, -idx, norm))

    if offer_candidates:
        return offer_candidates[0], card_pdf_urls
    if organizer_candidates:
        return organizer_candidates[0], card_pdf_urls

    strong_body = [c for c in scored_body_candidates if c[0] >= 13]
    if strong_body:
        strong_body.sort(reverse=True)
        return strong_body[0][2], card_pdf_urls

    if weak_ld_candidates:
        return weak_ld_candidates[0], card_pdf_urls

    positive_body = [c for c in scored_body_candidates if c[0] >= 1]
    if positive_body:
        positive_body.sort(reverse=True)
        return positive_body[0][2], card_pdf_urls

    return None, card_pdf_urls


def _convert_organizer_html_to_markdown(html_content: str, *, base_url: str) -> str:
    """
    Очищает HTML-страницу организатора: удаляет <footer>, <script>, <style>, <noscript>, <svg>,
    но СОХРАНЯЕТ <header> и <nav>, где организаторы обычно размещают меню тарифов и программы.
    """
    soup = BeautifulSoup(html_content, "lxml")
    for tag in soup(["footer", "script", "style", "noscript", "svg"]):
        tag.decompose()

    for a_tag in soup.find_all("a", href=True):
        raw_href = str(a_tag.get("href") or "").strip()
        if not raw_href or raw_href.startswith(("#", "mailto:", "tel:", "javascript:", "data:")):
            continue
        try:
            a_tag["href"] = urljoin(base_url, raw_href)
        except ValueError:
            continue

    return str(html_to_markdown(str(soup), heading_style="ATX")).strip()


def _score_organizer_link(norm_url: str, label: str, *, is_pdf: bool, in_nav_or_header: bool) -> int:
    text_low = f"{label} {urlsplit(norm_url).path}".lower()
    score = 0
    for kw, weight in _NAV_POSITIVE_KEYWORDS:
        if kw in text_low:
            score += weight
    if is_pdf:
        score += 4
    if in_nav_or_header and score > 0:
        score += 2
    if any(bad in text_low for bad in _NAV_NEGATIVE_KEYWORDS):
        score -= 8
    return score


def _extract_organizer_candidate_links(
    raw_content: str,
    *,
    is_markdown: bool,
    organizer_url: str,
) -> list[_LinkCandidate]:
    org_key = _url_dedup_key(organizer_url)
    extra_agg_hosts: set[str] = set()
    by_key: dict[str, _LinkCandidate] = {}

    def _consider_link(raw_href: str, label: str, ctx: str, *, in_nav: bool) -> None:
        norm = canonicalize_url(raw_href, organizer_url)
        if not norm:
            return
        k = _url_dedup_key(norm)
        if k == org_key:
            return
        if _is_blocked_external_url(norm):
            return
        is_pdf = urlsplit(norm).path.lower().endswith(".pdf")
        if not is_pdf:
            if not _same_organizer_domain(norm, organizer_url):
                return
            if _is_aggregator_or_ticketing(norm, extra_agg_hosts):
                return
        score = _score_organizer_link(norm, label, is_pdf=is_pdf, in_nav_or_header=in_nav)
        if not is_pdf and score < -2:
            return
        cand = _LinkCandidate(url=norm, label=label, context=ctx, is_pdf=is_pdf, score=score)
        prev = by_key.get(k)
        if prev is None or cand.score > prev.score or (cand.score == prev.score and len(cand.label) > len(prev.label)):
            by_key[k] = cand

    if not is_markdown:
        soup = BeautifulSoup(raw_content, "lxml")
        for tag in soup(["footer", "script", "style", "noscript", "svg"]):
            tag.decompose()
        for a_tag in soup.find_all("a", href=True):
            raw_href = str(a_tag.get("href") or "").strip()
            if not raw_href:
                continue
            label = " ".join(a_tag.get_text(" ", strip=True).split())
            if not label:
                label = " ".join(str(a_tag.get("title") or a_tag.get("aria-label") or "").split())
            in_nav = isinstance(a_tag, Tag) and a_tag.find_parent(["header", "nav"]) is not None
            _consider_link(raw_href, label, label, in_nav=in_nav)
    else:
        for norm, label, line_ctx in _extract_markdown_links_with_context(raw_content, organizer_url):
            _consider_link(norm, label, line_ctx, in_nav=False)

    ordered = sorted(by_key.values(), key=lambda c: (-c.score, c.url))
    return ordered[:_MAX_NAV_CANDIDATE_LINKS]


def _select_organizer_links_deterministic(
    candidates: list[_LinkCandidate],
    *,
    max_html: int = _MAX_HTML_SUBPAGES,
    max_pdf: int = _MAX_PDF_FILES,
) -> tuple[list[str], list[str]]:
    html_urls = [c.url for c in candidates if not c.is_pdf and c.score > 0][:max_html]
    pdf_candidates = [c for c in candidates if c.is_pdf and c.score >= 0]
    if not pdf_candidates:
        pdf_candidates = [c for c in candidates if c.is_pdf]
    pdf_urls = [c.url for c in pdf_candidates][:max_pdf]
    return html_urls, pdf_urls


async def _select_organizer_links(
    organizer_url: str,
    candidates: list[_LinkCandidate],
) -> tuple[list[str], list[str]]:
    """
    AI Link Navigator (LLM-2): выбирает до 2 HTML-подстраниц и до 2 PDF-ссылок.
    При отсутствии LLM_API_KEY или сбое LLM использует детерминированный отбор по ключевым словам.
    """
    import app.services.scraper as scraper_pkg

    if not candidates:
        return [], []

    if not scraper_pkg.settings.LLM_API_KEY:
        return _select_organizer_links_deterministic(candidates)

    by_key = {_url_dedup_key(c.url): c for c in candidates}
    lines = [
        f"{idx}. [{'PDF' if c.is_pdf else 'HTML'}] {c.label or '(без текста)'} -> {c.url}"
        for idx, c in enumerate(candidates, start=1)
    ]
    system_prompt = (
        "Ты — навигатор сайтов B2B-мероприятий (LLM-2). "
        "Из списка ссылок на сайте организатора выбери:\n"
        f"- до {_MAX_HTML_SUBPAGES} самых полезных HTML-подстраниц с тарифами/ценами, условиями участия, "
        "требованиями к спикерам, программой или регламентом;\n"
        f"- до {_MAX_PDF_FILES} самых полезных .pdf ссылок (коммерческое предложение, прайс, регламент, программа).\n"
        "Возвращай ТОЛЬКО точные URL из переданного списка. Ничего не выдумывай."
    )
    user_prompt = f"Главная страница организатора: {organizer_url}\nКандидаты:\n" + "\n".join(lines)

    try:
        async with scraper_pkg.LLM_SEMAPHORE:
            selection: OrganizerLinksSelection = await asyncio.wait_for(
                scraper_pkg.structured_llm_client.chat.completions.create(
                    model=scraper_pkg.settings.LLM_MODEL,
                    response_model=OrganizerLinksSelection,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    max_tokens=300,
                    max_retries=1,
                ),
                timeout=15.0,
            )
    except (TimeoutError, APIError, httpx.HTTPError, InstructorError) as exc:
        logger.warning(
            "Сбой AI Link Navigator (LLM-2) для %s, переход на детерминированный отбор: %s",
            organizer_url,
            exc,
        )
        return _select_organizer_links_deterministic(candidates)

    valid_html: list[str] = []
    seen_html: set[str] = set()
    for raw_u in selection.html_subpage_urls:
        norm = canonicalize_url(raw_u, organizer_url)
        if not norm:
            continue
        k = _url_dedup_key(norm)
        cand = by_key.get(k)
        if cand and not cand.is_pdf and k not in seen_html:
            seen_html.add(k)
            valid_html.append(cand.url)
            if len(valid_html) >= _MAX_HTML_SUBPAGES:
                break

    valid_pdf: list[str] = []
    seen_pdf: set[str] = set()
    for raw_u in selection.pdf_urls:
        norm = canonicalize_url(raw_u, organizer_url)
        if not norm:
            continue
        k = _url_dedup_key(norm)
        cand = by_key.get(k)
        if cand and cand.is_pdf and k not in seen_pdf:
            seen_pdf.add(k)
            valid_pdf.append(cand.url)
            if len(valid_pdf) >= _MAX_PDF_FILES:
                break

    if not valid_html and not valid_pdf:
        return _select_organizer_links_deterministic(candidates)
    return valid_html, valid_pdf


@dataclass(frozen=True)
class _DigestSection:
    title: str
    body: str
    ext_links: list[str]
    score: int


def _extract_digest_b2b_sections(
    agg_markdown: str,
    candidate: DiscoveredCandidate,
    source: CustomerSourceConfig,
    *,
    max_sections: int = 3,
) -> tuple[str, list[_DigestSection]]:
    """
    Разбирает статью-дайджест по заголовкам h2/h3, отсекает очевидные B2C-блоки
    и возвращает intro + до max_sections самых релевантных B2B-секций.
    """
    _, body_md = _split_ld_json_and_body(agg_markdown)
    extra_agg_hosts = {
        (urlsplit(u).hostname or "").lower().removeprefix("www.")
        for u in (candidate.url, *source.catalog_urls)
        if u and urlsplit(u).hostname
    }
    heading_re = re.compile(r"^(#{2,3})\s+(.+?)\s*$")

    intro_lines: list[str] = []
    sections: list[tuple[str, str]] = []
    current_title: str | None = None
    current_lines: list[str] = []

    for line in body_md.splitlines():
        m = heading_re.match(line)
        if m:
            if current_title is not None:
                sections.append((current_title, "\n".join(current_lines).strip()))
            current_title = m.group(2).strip()
            current_lines = []
        else:
            if current_title is None:
                intro_lines.append(line)
            else:
                current_lines.append(line)

    if current_title is not None:
        sections.append((current_title, "\n".join(current_lines).strip()))

    non_empty_sections = [
        (title, body)
        for title, body in sections
        if len(f"{title} {body}".strip()) >= 40
    ]
    intro_text = "\n".join(intro_lines).strip()[:1500]
    if not non_empty_sections:
        return intro_text, []

    if len(non_empty_sections) > 1:
        b2b_sections = [
            (title, body)
            for title, body in non_empty_sections
            if not _is_obvious_b2c(f"{title}\n{body}")
        ]
        pool = b2b_sections if b2b_sections else non_empty_sections
    else:
        pool = non_empty_sections

    scored_pool: list[tuple[int, int, _DigestSection]] = []
    for idx, (title, body) in enumerate(pool):
        ext_links: list[str] = []
        seen_ext: set[str] = set()
        for norm, _, _ in _extract_markdown_links_with_context(body, candidate.url):
            if _is_blocked_external_url(norm) or _is_aggregator_or_ticketing(norm, extra_agg_hosts):
                continue
            k = _url_dedup_key(norm)
            if k not in seen_ext:
                seen_ext.add(k)
                ext_links.append(norm)

        low = f"{title} {body}".lower()
        rel_score = sum(1 for kw in _DIGEST_B2B_KEYWORDS if kw in low) * 3
        if ext_links:
            rel_score += 2
        sec = _DigestSection(title=title, body=body, ext_links=ext_links, score=rel_score)
        scored_pool.append((rel_score, -idx, sec))

    scored_pool.sort(key=lambda item: (item[0], item[1]), reverse=True)
    selected = sorted(scored_pool[:max_sections], key=lambda item: -item[1])
    return intro_text, [item[2] for item in selected]


def _build_digest_dossier_text(
    agg_markdown: str,
    candidate: DiscoveredCandidate,
    source: CustomerSourceConfig,
) -> str:
    """Формирует единый Markdown-дайджест (до 3 B2B-секций) для совместимого вызова collect_event_dossier."""
    intro_text, selected = _extract_digest_b2b_sections(agg_markdown, candidate, source)
    if not selected:
        return f"=== ДАЙДЖЕСТ С АГРЕГАТОРА ({candidate.url}) ===\n{agg_markdown[:35000]}".strip()

    parts: list[str] = [f"=== ДАЙДЖЕСТ СОБЫТИЙ ({candidate.url}) ==="]
    if intro_text:
        parts.append(intro_text)

    per_section_budget = 14_000
    for sec in selected:
        sec_lines = [f"## {sec.title}", sec.body[:per_section_budget]]
        if sec.ext_links:
            sec_lines.append("Внешние ссылки секции: " + ", ".join(sec.ext_links[:5]))
        parts.append("\n\n".join(sec_lines))

    return "\n\n".join(parts)[:MAX_DOSSIER_CHARS].strip()


def _accepts_kwarg(fn: object, name: str) -> bool:
    side_effect = getattr(fn, "side_effect", None)
    target = side_effect if callable(side_effect) else fn
    if not callable(target):
        return False
    try:
        sig = inspect.signature(target)
    except (TypeError, ValueError):
        return False
    for param in sig.parameters.values():
        if param.kind == inspect.Parameter.VAR_KEYWORD:
            return True
        if param.name == name and param.kind in (
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            inspect.Parameter.KEYWORD_ONLY,
        ):
            return True
    return False


def _filter_supported_kwargs(fn: object, kwargs: dict[str, object]) -> dict[str, object]:
    """Фильтрует kwargs по сигнатуре функции или mock.side_effect для обратной совместимости."""
    return {k: v for k, v in kwargs.items() if _accepts_kwarg(fn, k)}


def _truncate_section(text: str, limit: int) -> str:
    cleaned = text.strip()
    if len(cleaned) <= limit:
        return cleaned
    return f"{cleaned[:limit].rstrip()}\n...[фрагмент сокращен]"


async def _enrich_from_base_markdown(
    *,
    base_label: str,
    base_url: str,
    base_markdown: str,
    source: CustomerSourceConfig,
    official_url: str | None,
    card_pdf_urls: list[str],
    agg_budget: int = 17_000,
    vision_ocr: VisionOCRProviderProtocol | None = None,
    ocr_budget: OcrBudgetTracker | None = None,
) -> CollectedEventDossier:
    """Общий 2-Hop обогатитель: загружает сайт организатора (с <nav>), подстраницы, PDF и собирает досье."""
    import app.services.scraper as scraper_pkg

    collected_urls: list[str] = [base_url]
    seen_collected: set[str] = {_url_dedup_key(base_url)}
    warnings: list[str] = []

    def _add_collected_url(url: str) -> None:
        k = _url_dedup_key(url)
        if k not in seen_collected:
            seen_collected.add(k)
            collected_urls.append(url)

    org_homepage_md = ""
    subpage_sections: list[tuple[str, str]] = []
    org_pdf_urls: list[str] = []
    subpage_pdf_urls: list[str] = []

    if official_url:
        try:
            org_raw, org_is_md = await fetcher_mod._fetch_raw_page_content(official_url)
            _add_collected_url(official_url)
            org_homepage_md = (
                org_raw
                if org_is_md
                else _convert_organizer_html_to_markdown(org_raw, base_url=official_url)
            )
            org_candidates = _extract_organizer_candidate_links(
                org_raw,
                is_markdown=org_is_md,
                organizer_url=official_url,
            )
            selected_subpages, org_pdf_urls = await _select_organizer_links(
                official_url, org_candidates
            )

            for sub_url in selected_subpages[:_MAX_HTML_SUBPAGES]:
                try:
                    sub_raw, sub_is_md = await fetcher_mod._fetch_raw_page_content(sub_url)
                    _add_collected_url(sub_url)
                    sub_md = (
                        sub_raw
                        if sub_is_md
                        else _convert_organizer_html_to_markdown(sub_raw, base_url=sub_url)
                    )
                    if sub_md.strip():
                        subpage_sections.append((sub_url, sub_md))
                    sub_links = _extract_organizer_candidate_links(
                        sub_raw, is_markdown=sub_is_md, organizer_url=official_url
                    )
                    for lc in sub_links:
                        if lc.is_pdf:
                            subpage_pdf_urls.append(lc.url)
                except (
                    fetcher_mod.CaptchaBlockedError,
                    fetcher_mod.UnsafeUrlError,
                    httpx.HTTPError,
                    ValueError,
                    RuntimeError,
                    TimeoutError,
                ) as exc:
                    logger.warning(
                        "2-Hop: не удалось загрузить подстраницу организатора %s: %s",
                        sub_url,
                        exc,
                    )
                    warnings.append("official_subpage_unreachable")
        except (
            fetcher_mod.CaptchaBlockedError,
            fetcher_mod.UnsafeUrlError,
            httpx.HTTPError,
            ValueError,
            RuntimeError,
            TimeoutError,
        ) as exc:
            logger.warning(
                "2-Hop: сайт организатора недоступен (%s) для карточки %s: %s",
                official_url,
                base_url,
                exc,
            )
            warnings.append("official_site_unreachable")

    sections_out: list[str] = [
        f"=== {base_label} ({base_url}) ===\n{_truncate_section(base_markdown, agg_budget)}"
    ]
    if org_homepage_md.strip():
        sections_out.append(
            f"=== ОФИЦИАЛЬНЫЙ САЙТ ОРГАНИЗАТОРА ({official_url}) ===\n"
            f"{_truncate_section(org_homepage_md, 13_000)}"
        )

    if subpage_sections:
        sub_budget = 14_000 if len(subpage_sections) == 1 else 8_000
        for sub_url, sub_md in subpage_sections:
            sections_out.append(
                f"=== ПОДСТРАНИЦА ОРГАНИЗАТОРА ({sub_url}) ===\n"
                f"{_truncate_section(sub_md, sub_budget)}"
            )

    html_context = "\n\n".join(sections_out).strip()

    candidate_pdfs: list[str] = []
    seen_pdf_keys: set[str] = set()
    for pdf_u in [*card_pdf_urls, *org_pdf_urls, *subpage_pdf_urls]:
        k = _url_dedup_key(pdf_u)
        if k not in seen_pdf_keys:
            seen_pdf_keys.add(k)
            candidate_pdfs.append(pdf_u)
        if len(candidate_pdfs) >= _MAX_PDF_FILES:
            break

    source_cookies = dict(source.required_cookies) if source.required_cookies else None
    card_host = (urlsplit(base_url).hostname or "").lower()
    pdf_sections: list[tuple[str, str]] = []
    ocr_sections: list[tuple[str, str]] = []
    for pdf_url in candidate_pdfs:
        try:
            pdf_host = (urlsplit(pdf_url).hostname or "").lower()
            cookies_for_pdf = (
                source_cookies
                if source_cookies and _host_matches_domain(pdf_host, card_host)
                else None
            )
            pdf_bytes = await fetcher_mod.fetch_pdf_bytes_safe(
                pdf_url,
                max_bytes=scraper_pkg.settings.SCRAPER_MAX_PDF_BYTES,
                cookies=cookies_for_pdf,
            )
            pdf_text, ocr_images = await scraper_pkg.extract_pdf_text_async(
                pdf_bytes,
                max_ocr_pages=scraper_pkg.settings.VISION_OCR_MAX_PAGES_AUTO,
                include_all_if_compact=True,
            )
            if pdf_text and pdf_text.strip():
                _add_collected_url(pdf_url)
                pdf_sections.append((pdf_url, pdf_text.strip()))
        except (
            fetcher_mod.UnsafeUrlError,
            httpx.HTTPError,
            ValueError,
            RuntimeError,
            TimeoutError,
        ) as exc:
            logger.warning("2-Hop: ошибка загрузки/чтения PDF %s: %s", pdf_url, exc)
            warnings.append("pdf_download_failed")
            continue

        if ocr_images and scraper_pkg.should_run_vision_ocr(html_context, pdf_text, ocr_images):
            if vision_ocr is None:
                warnings.append("vision_ocr_not_configured")
            else:
                if ocr_budget is not None:
                    allowed = ocr_budget.reserve(
                        len(ocr_images),
                        per_doc_limit=scraper_pkg.settings.VISION_OCR_MAX_PAGES_AUTO,
                    )
                else:
                    allowed = min(
                        len(ocr_images),
                        scraper_pkg.settings.VISION_OCR_MAX_PAGES_AUTO,
                    )
                if allowed <= 0:
                    warnings.append("vision_ocr_budget_exhausted")
                else:
                    try:
                        ocr_text = await vision_ocr.extract_text_from_images(ocr_images[:allowed])
                    except (TimeoutError, APIError, httpx.HTTPError, RuntimeError, ValueError) as exc:
                        logger.warning("2-Hop: сбой Vision OCR для PDF %s: %s", pdf_url, exc)
                        ocr_text = ""
                    if ocr_text and ocr_text.strip():
                        _add_collected_url(pdf_url)
                        ocr_sections.append((pdf_url, ocr_text.strip()))
                    else:
                        warnings.append("pdf_scanned_pages_not_recognized")

    if pdf_sections:
        pdf_budget = 11_000 if len(pdf_sections) == 1 else 6_000
        for pdf_url, pdf_txt in pdf_sections:
            sections_out.append(
                f"=== ТЕКСТ ИЗ PDF-ДОКУМЕНТА ({pdf_url}) ===\n"
                f"{_truncate_section(pdf_txt, pdf_budget)}"
            )

    if ocr_sections:
        ocr_budget_chars = 11_000 if len(ocr_sections) == 1 else 6_000
        for pdf_url, ocr_txt in ocr_sections:
            sections_out.append(
                f"=== РАСПОЗНАННЫЙ OCR ТЕКСТ PDF ===\nИсточник: {pdf_url}\n"
                f"{_truncate_section(ocr_txt, ocr_budget_chars)}"
            )

    assembled = "\n\n".join(sections_out).strip()
    if len(assembled) > MAX_DOSSIER_CHARS:
        assembled = assembled[:MAX_DOSSIER_CHARS]

    return CollectedEventDossier(
        dossier_text=assembled,
        source_urls=collected_urls,
        official_site_url=official_url,
        warnings=list(dict.fromkeys(warnings)),
    )


async def collect_event_dossier(
    candidate: DiscoveredCandidate,
    source: CustomerSourceConfig,
    *,
    vision_ocr: VisionOCRProviderProtocol | None = None,
    ocr_budget: OcrBudgetTracker | None = None,
) -> CollectedEventDossier:
    """
    Боевой 2-Hop краулер:
    1. Загружает карточку агрегатора (удаляя <header>/<nav>/<footer>/<aside>, но сохраняя ld+json).
    2. При candidate.is_digest=True формирует дайджест до 3 B2B-секций (для изолированного раздельного ингеста используй collect_event_dossiers).
    3. Ищет официальный сайт организатора (offers.url -> organizer.url -> маркеры в очищенном контенте).
    4. Загружает главную организатора (сохраняя <header>/<nav>), через LLM-2 / fallback отбирает
       до 2 HTML-подстраниц и до 2 PDF, безопасно скачивает PDF и читает через extract_pdf_text_async
       (с гибридным бюджетным Vision OCR для сканов).
    """
    import app.services.scraper as scraper_pkg

    agg_markdown = await scraper_pkg.fetch_url_dossier_text(candidate.url, source_config=source)
    is_digest = candidate.is_digest or source.adapter_type == "html_digest"
    if is_digest:
        digest_text = _build_digest_dossier_text(agg_markdown, candidate, source)
        return CollectedEventDossier(
            dossier_text=digest_text,
            source_urls=[candidate.url],
            official_site_url=None,
            warnings=[],
        )

    official_url, card_pdf_urls = _discover_official_site_and_card_pdfs(
        agg_markdown, candidate, source
    )
    return await _enrich_from_base_markdown(
        base_label="ДАННЫЕ С АГРЕГАТОРА",
        base_url=candidate.url,
        base_markdown=agg_markdown,
        source=source,
        official_url=official_url,
        card_pdf_urls=card_pdf_urls,
        vision_ocr=vision_ocr,
        ocr_budget=ocr_budget,
    )


async def collect_event_dossiers(
    candidate: DiscoveredCandidate,
    source: CustomerSourceConfig,
    *,
    max_digest_events: int = 3,
    vision_ocr: VisionOCRProviderProtocol | None = None,
    ocr_budget: OcrBudgetTracker | None = None,
) -> list[CollectedEventDossier]:
    """
    Возвращает список независимых досье:
    - для обычной карточки -> 1 досье через collect_event_dossier;
    - для дайджеста (h2/h3 подборка) -> до max_digest_events независимых досье (1 секция = 1 событие),
      причём каждое при наличии внешней ссылки проходит полноценный 2-Hop на сайт организатора.
    """
    import app.services.scraper as scraper_pkg

    is_digest = candidate.is_digest or source.adapter_type == "html_digest"
    if not is_digest:
        dossier_kwargs = _filter_supported_kwargs(
            scraper_pkg.collect_event_dossier,
            {"vision_ocr": vision_ocr, "ocr_budget": ocr_budget},
        )
        return [await scraper_pkg.collect_event_dossier(candidate, source, **dossier_kwargs)]  # type: ignore[arg-type]

    agg_markdown = await scraper_pkg.fetch_url_dossier_text(candidate.url, source_config=source)
    intro_text, selected = _extract_digest_b2b_sections(
        agg_markdown, candidate, source, max_sections=max_digest_events
    )
    if not selected:
        return [
            CollectedEventDossier(
                dossier_text=f"=== ДАЙДЖЕСТ С АГРЕГАТОРА ({candidate.url}) ===\n{agg_markdown[:35000]}".strip(),
                source_urls=[candidate.url],
                official_site_url=None,
                warnings=[],
            )
        ]

    dossiers: list[CollectedEventDossier] = []
    for sec in selected:
        sec_md_parts = [f"## {sec.title}", sec.body]
        if intro_text:
            sec_md_parts.append(f"Контекст подборки: {intro_text[:600]}")
        sec_md = "\n\n".join(sec_md_parts)
        sec_pdfs = [u for u in sec.ext_links if urlsplit(u).path.lower().endswith(".pdf")]
        sec_official = next(
            (u for u in sec.ext_links if not urlsplit(u).path.lower().endswith(".pdf")),
            None,
        )
        enriched = await _enrich_from_base_markdown(
            base_label="СЕКЦИЯ ДАЙДЖЕСТА",
            base_url=candidate.url,
            base_markdown=sec_md,
            source=source,
            official_url=sec_official,
            card_pdf_urls=sec_pdfs,
            agg_budget=14_000,
            vision_ocr=vision_ocr,
            ocr_budget=ocr_budget,
        )
        dossiers.append(enriched)
    return dossiers
