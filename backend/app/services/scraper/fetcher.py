import asyncio
import ipaddress
import logging
import socket
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from urllib.parse import urljoin, urlsplit
from weakref import WeakKeyDictionary

import httpx
from bs4 import BeautifulSoup  # type: ignore[import-untyped]
from markdownify import markdownify as html_to_markdown  # type: ignore[import-untyped]

from app.services.scraper.sources import (
    CustomerSourceConfig,
    DiscoveredCandidate,
    DiscoveryResult,
    looks_like_xml_feed,
)

logger = logging.getLogger(__name__)

_HOST_POLITENESS_DELAY_SEC: float = 0.65
_BLOCKED_HOST_SUFFIXES: tuple[str, ...] = (".localhost", ".local", ".internal")
_BLOCKED_EXACT_HOSTS: frozenset[str] = frozenset({"localhost", "localhost.localdomain"})

_loop_host_locks: WeakKeyDictionary[asyncio.AbstractEventLoop, dict[str, asyncio.Lock]] = (
    WeakKeyDictionary()
)
_loop_host_last_ts: WeakKeyDictionary[asyncio.AbstractEventLoop, dict[str, float]] = (
    WeakKeyDictionary()
)
_loop_jina_semaphores: WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Semaphore] = (
    WeakKeyDictionary()
)


class UnsafeUrlError(ValueError):
    """Исключение безопасности при попытке обращения к внутреннему или недопустимому URL (SSRF)."""


class CaptchaBlockedError(ValueError):
    """Контролируемая ошибка при обнаружении CAPTCHA-стены (обход запрещен, нужен ручной импорт)."""


def _is_unsafe_ip(ip_obj: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if (
        isinstance(ip_obj, ipaddress.IPv6Address)
        and ip_obj.ipv4_mapped is not None
        and _is_unsafe_ip(ip_obj.ipv4_mapped)
    ):
        return True
    return bool(
        ip_obj.is_private
        or ip_obj.is_loopback
        or ip_obj.is_link_local
        or ip_obj.is_reserved
        or ip_obj.is_multicast
        or ip_obj.is_unspecified
    )


async def validate_safe_public_url(url: str) -> str:
    """
    SSRF-валидатор: разрешает только http/https, блокирует localhost/.local/.internal
    и любые приватные/локальные/link-local/reserved/multicast/unspecified IP после DNS-резолвинга.
    """
    cleaned = (url or "").strip()
    if not cleaned:
        raise UnsafeUrlError("Передан пустой URL.")

    parts = urlsplit(cleaned)
    scheme = parts.scheme.lower()
    if scheme not in ("http", "https"):
        raise UnsafeUrlError(f"Недопустимая схема URL '{scheme}': разрешены только http и https.")
    if not parts.netloc or not parts.hostname:
        raise UnsafeUrlError("URL должен содержать корректное доменное имя или IP-адрес.")
    if parts.username is not None or parts.password is not None:
        raise UnsafeUrlError("URL не должен содержать встроенные учетные данные (userinfo).")

    host = parts.hostname.lower().rstrip(".")
    if host in _BLOCKED_EXACT_HOSTS or host.endswith(_BLOCKED_HOST_SUFFIXES):
        raise UnsafeUrlError(f"Заблокирован доступ к внутреннему хосту '{host}'.")

    try:
        ip_literal = ipaddress.ip_address(host)
    except ValueError:
        ip_literal = None

    if ip_literal is not None:
        if _is_unsafe_ip(ip_literal):
            raise UnsafeUrlError(f"Заблокирован доступ к непубличному IP-адресу '{host}'.")
        return cleaned

    try:
        addr_infos = await asyncio.to_thread(socket.getaddrinfo, host, None)
    except socket.gaierror as exc:
        raise UnsafeUrlError(f"Не удалось разрешить DNS-имя '{host}': {exc}") from exc

    if not addr_infos:
        raise UnsafeUrlError(f"DNS не вернул ни одного адреса для '{host}'.")

    for entry in addr_infos:
        sockaddr = entry[4]
        if not sockaddr:
            continue
        raw_ip = str(sockaddr[0]).split("%", 1)[0]
        try:
            resolved_ip = ipaddress.ip_address(raw_ip)
        except ValueError as exc:
            raise UnsafeUrlError(f"Некорректный IP '{raw_ip}' от DNS для '{host}'.") from exc
        if _is_unsafe_ip(resolved_ip):
            raise UnsafeUrlError(
                f"Домен '{host}' разрешился в запрещенный непубличный IP '{raw_ip}'."
            )

    return cleaned


def _get_jina_semaphore() -> asyncio.Semaphore:
    loop = asyncio.get_running_loop()
    sem = _loop_jina_semaphores.get(loop)
    if sem is None:
        sem = asyncio.Semaphore(2)
        _loop_jina_semaphores[loop] = sem
    return sem


@asynccontextmanager
async def _host_rate_limit(
    host: str, delay_sec: float = _HOST_POLITENESS_DELAY_SEC
) -> AsyncIterator[None]:
    loop = asyncio.get_running_loop()
    locks_map = _loop_host_locks.setdefault(loop, {})
    last_ts_map = _loop_host_last_ts.setdefault(loop, {})
    norm_host = host.lower()
    lock = locks_map.setdefault(norm_host, asyncio.Lock())
    async with lock:
        now = time.monotonic()
        last_ts = last_ts_map.get(norm_host)
        if last_ts is not None:
            wait_for = delay_sec - (now - last_ts)
            if wait_for > 0:
                await asyncio.sleep(wait_for)
        try:
            yield
        finally:
            last_ts_map[norm_host] = time.monotonic()


async def _ssrf_request_hook(request: httpx.Request) -> None:
    await validate_safe_public_url(str(request.url))


def _is_captcha_page(decoded_html: str, visible_text: str, final_url: str) -> bool:
    html_low = decoded_html.lower()
    vis_low = visible_text.lower()
    url_low = final_url.lower()
    if "showcaptchafast" in html_low or "showcaptcha" in url_low:
        return True
    return bool(
        len(visible_text) < 1500
        and (
            "smartcaptcha" in html_low
            or "вы не робот" in vis_low
            or "подтвердите, что запросы отправляли вы" in vis_low
            or "cf-turnstile" in html_low
        )
    )


def _is_jina_waf_or_captcha_block(md_text: str) -> bool:
    low = (md_text or "").lower()
    if not low:
        return False
    if "showcaptchafast" in low or "waf@hostadmin.online" in low or "access denied by waf" in low:
        return True
    return bool(
        len(md_text) < 3500
        and (
            "checking your browser before accessing" in low
            or "hostadmin.online" in low
            or "хостадмин.онлайн" in low
            or "attention required! | cloudflare" in low
            or "cf-turnstile" in low
            or "enable javascript and cookies to continue" in low
            or "подтвердите, что запросы отправляли вы" in low
            or "вы не робот" in low
        )
    )


async def _fetch_via_jina_reader(client: httpx.AsyncClient, target_url: str) -> str:
    """Запрашивает очищенный Markdown страницы через облачный рендер r.jina.ai (с SSRF-проверкой и Semaphore(2))."""
    import app.services.scraper as scraper_pkg

    safe_target = await validate_safe_public_url(target_url)
    jina_url = f"https://r.jina.ai/{safe_target}"
    headers: dict[str, str] = {"X-With-Links-Summary": "true"}
    if scraper_pkg.settings.jina_token:
        headers["Authorization"] = f"Bearer {scraper_pkg.settings.jina_token}"
    async with _get_jina_semaphore():
        resp = await client.get(jina_url, headers=headers)
    resp.raise_for_status()
    md_text = resp.text.strip()
    if _is_jina_waf_or_captcha_block(md_text):
        raise CaptchaBlockedError(
            f"Страница '{safe_target}' заблокирована WAF/антибот-проверкой при загрузке через r.jina.ai."
        )
    return md_text


async def _fetch_raw_page_content(
    url: str,
    *,
    encoding: str = "utf-8",
    use_jina_reader: bool = False,
    cookies: dict[str, str] | None = None,
) -> tuple[str, bool]:
    """
    Загружает содержимое веб-страницы с SSRF-защитой, per-host politeness, учетом кодировки/cookies,
    детекцией CAPTCHA и фолбэком на r.jina.ai при 403/429, заглушке хостинга или SPA (< 300 символов).
    Возвращает кортеж (content, is_markdown).
    """
    safe_url = await validate_safe_public_url(url)
    target_host = (urlsplit(safe_url).hostname or "").lower()
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        )
    }
    async with httpx.AsyncClient(
        timeout=20.0,
        follow_redirects=True,
        cookies=cookies,
        event_hooks={"request": [_ssrf_request_hook]},
    ) as client:
        if use_jina_reader:
            md_text = await _fetch_via_jina_reader(client, safe_url)
            return md_text, True

        async with _host_rate_limit(target_host):
            resp = await client.get(safe_url, headers=headers)

        decoded_html = resp.content.decode(encoding, errors="replace")

        if resp.status_code < 400 and looks_like_xml_feed(decoded_html):
            return decoded_html, False

        soup = BeautifulSoup(decoded_html, "lxml")
        visible_text = soup.get_text(" ", strip=True)

        if _is_captcha_page(decoded_html, visible_text, str(resp.url)):
            raise CaptchaBlockedError(
                f"Страница '{safe_url}' защищена CAPTCHA; автоматический обход отключен."
            )

        if resp.status_code in (403, 429):
            md_text = await _fetch_via_jina_reader(client, safe_url)
            return md_text, True

        if resp.status_code >= 400:
            resp.raise_for_status()

        if len(visible_text) < 300 or "хостадмин.онлайн" in visible_text.lower():
            md_text = await _fetch_via_jina_reader(client, safe_url)
            return md_text, True

        return decoded_html, False


class HttpCatalogSourceScraper:
    """Боевой адаптер Discovery для обхода каталогов (HTML, XML/RSS, Jina Reader) всех источников."""

    async def discover_catalog(self, source: CustomerSourceConfig) -> DiscoveryResult:
        """Обходит все catalog_urls источника, объединяя кандидатов и счетчики отсева B2C/Geo."""
        import app.services.scraper as scraper_pkg

        cookies_dict = dict(source.required_cookies) if source.required_cookies else None
        urls_to_fetch = source.catalog_urls or (() if not source.catalog_url else (source.catalog_url,))
        if not urls_to_fetch:
            return DiscoveryResult()

        merged_candidates: list[DiscoveredCandidate] = []
        seen_keys: set[str] = set()
        total_b2c = 0
        total_geo = 0
        last_error: Exception | None = None
        succeeded_count = 0

        for cat_url in urls_to_fetch:
            try:
                raw_content, _ = await _fetch_raw_page_content(
                    cat_url,
                    encoding=source.encoding,
                    use_jina_reader=source.use_jina_reader,
                    cookies=cookies_dict,
                )
                result = scraper_pkg.extract_discovery_candidates(
                    raw_content,
                    source,
                    base_url=cat_url,
                )
                succeeded_count += 1
                total_b2c += result.rejected_b2c
                total_geo += result.rejected_geo
                for cand in result.candidates:
                    dedup_key = cand.url.rstrip("/")
                    if dedup_key not in seen_keys:
                        seen_keys.add(dedup_key)
                        merged_candidates.append(cand)
            except (httpx.HTTPError, ValueError, RuntimeError) as exc:
                last_error = exc
                logger.warning(
                    "Ошибка при загрузке каталога %s для источника %s: %s",
                    cat_url,
                    source.source_key,
                    exc,
                )

        if succeeded_count == 0 and last_error is not None:
            raise last_error

        return DiscoveryResult(
            candidates=merged_candidates,
            rejected_b2c=total_b2c,
            rejected_geo=total_geo,
        )

    async def fetch_catalog_urls(self, source: CustomerSourceConfig) -> list[str]:
        discovery = await self.discover_catalog(source)
        return [c.url for c in discovery.candidates]


def _convert_html_to_dossier_markdown(
    html_content: str,
    *,
    base_url: str | None = None,
    strip_chrome: bool = False,
) -> str:
    """Преобразует HTML-страницу мероприятия в очищенный Markdown с сохранением Schema.org JSON-LD в начале досье."""
    soup = BeautifulSoup(html_content, "lxml")
    ld_blocks = [
        "\n".join(line for line in (s.string or "").splitlines() if line.strip())
        for s in soup.find_all("script", attrs={"type": "application/ld+json"})
        if (s.string or "").strip()
    ]
    tags_to_remove = (
        ["script", "style", "noscript", "svg", "header", "nav", "footer", "aside"]
        if strip_chrome
        else ["script", "style", "noscript", "svg", "footer", "nav"]
    )
    for tag in soup(tags_to_remove):
        tag.decompose()

    if base_url:
        for a_tag in soup.find_all("a", href=True):
            raw_href = str(a_tag.get("href") or "").strip()
            if not raw_href or raw_href.startswith(("#", "mailto:", "tel:", "javascript:", "data:")):
                continue
            try:
                abs_href = urljoin(base_url, raw_href)
                parsed_href = urlsplit(abs_href)
            except ValueError:
                continue
            a_tag["href"] = abs_href
            if not a_tag.get_text(" ", strip=True):
                fallback_label = str(a_tag.get("title") or a_tag.get("aria-label") or "").strip()
                if not fallback_label:
                    img = a_tag.find("img")
                    if img is not None:
                        fallback_label = str(img.get("alt") or "").strip()
                if not fallback_label:
                    fallback_label = (parsed_href.hostname or "").strip()
                if fallback_label:
                    a_tag.string = fallback_label

    md_body = str(html_to_markdown(str(soup), heading_style="ATX")).strip()
    if ld_blocks:
        ld_section = "--- SCHEMA.ORG LD+JSON ---\n" + "\n".join(ld_blocks)
        return f"{ld_section}\n\n{md_body}".strip()
    return md_body


def _is_acceptable_pdf_content_type(content_type: str, *candidate_urls: str) -> bool:
    media_type = content_type.split(";", 1)[0].strip().lower()
    if media_type in ("application/pdf", "application/x-pdf"):
        return True
    has_pdf_ext = any(urlsplit(u).path.lower().endswith(".pdf") for u in candidate_urls if u)
    if media_type in ("application/octet-stream", "binary/octet-stream") and has_pdf_ext:
        return True
    return not media_type and has_pdf_ext


async def fetch_pdf_bytes_safe(
    url: str,
    *,
    max_bytes: int = 15 * 1024 * 1024,
    cookies: dict[str, str] | None = None,
) -> bytes:
    """
    Безопасно скачивает PDF потоком с SSRF-защитой (включая редиректы),
    проверкой Content-Length, Content-Type, жестким лимитом байт и сигнатурой %PDF.
    """
    if max_bytes <= 0:
        raise ValueError("max_bytes должен быть положительным числом.")

    safe_url = await validate_safe_public_url(url)
    target_host = (urlsplit(safe_url).hostname or "").lower()
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        ),
        "Accept": "application/pdf,application/octet-stream;q=0.9,*/*;q=0.5",
    }

    async with (
        httpx.AsyncClient(
            timeout=30.0,
            follow_redirects=True,
            cookies=cookies,
            event_hooks={"request": [_ssrf_request_hook]},
        ) as client,
        _host_rate_limit(target_host),
        client.stream("GET", safe_url, headers=headers) as resp,
    ):
        resp.raise_for_status()

        raw_cl = resp.headers.get("content-length")
        if raw_cl is not None:
            try:
                content_length = int(raw_cl.strip())
            except ValueError:
                content_length = None
            if content_length is not None and content_length > max_bytes:
                raise ValueError(
                    f"Размер PDF ({content_length} байт) превышает лимит {max_bytes} байт."
                )

        content_type = str(resp.headers.get("content-type") or "")
        final_url = str(resp.url) if getattr(resp, "url", None) else safe_url
        if not _is_acceptable_pdf_content_type(content_type, safe_url, final_url):
            raise ValueError(
                f"Недопустимый Content-Type '{content_type}' при загрузке PDF с {safe_url}."
            )

        buf = bytearray()
        total_bytes = 0
        async for chunk in resp.aiter_bytes():
            if not chunk:
                continue
            total_bytes += len(chunk)
            if total_bytes > max_bytes:
                raise ValueError(
                    f"Потоковое скачивание PDF прервано: превышен лимит {max_bytes} байт."
                )
            buf.extend(chunk)

    pdf_bytes = bytes(buf)
    if not pdf_bytes or not pdf_bytes.lstrip().startswith(b"%PDF"):
        raise ValueError(f"Файл по адресу {safe_url} не является валидным PDF (отсутствует %PDF).")
    return pdf_bytes


async def fetch_url_dossier_text(
    url: str,
    source_config: CustomerSourceConfig | None = None,
) -> str:
    """
    Загружает страницу мероприятия по URL и преобразует её в структурированный Markdown-текст
    для передачи в LLM-3 (EventIngestionSchema).
    """
    enc = source_config.encoding if source_config else "utf-8"
    use_jina = source_config.use_jina_reader if source_config else False
    cookies_dict = (
        dict(source_config.required_cookies)
        if (source_config and source_config.required_cookies)
        else None
    )

    content, is_markdown = await _fetch_raw_page_content(
        url,
        encoding=enc,
        use_jina_reader=use_jina,
        cookies=cookies_dict,
    )
    if is_markdown:
        return content
    return _convert_html_to_dossier_markdown(
        content,
        base_url=url,
        strip_chrome=(source_config is not None),
    )
