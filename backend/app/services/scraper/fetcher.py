import httpx
from bs4 import BeautifulSoup  # type: ignore[import-untyped]
from markdownify import markdownify as html_to_markdown  # type: ignore[import-untyped]

from app.services.scraper.sources import CustomerSourceConfig


async def _fetch_via_jina_reader(client: httpx.AsyncClient, target_url: str) -> str:
    """Запрашивает очищенный Markdown страницы через облачный рендер r.jina.ai."""
    import app.services.scraper as scraper_pkg

    jina_url = f"https://r.jina.ai/{target_url}"
    headers: dict[str, str] = {"X-With-Links-Summary": "true"}
    if scraper_pkg.settings.jina_token:
        headers["Authorization"] = f"Bearer {scraper_pkg.settings.jina_token}"
    resp = await client.get(jina_url, headers=headers)
    resp.raise_for_status()
    return resp.text.strip()


async def _fetch_raw_page_content(
    url: str,
    *,
    encoding: str = "utf-8",
    use_jina_reader: bool = False,
    cookies: dict[str, str] | None = None,
) -> tuple[str, bool]:
    """
    Загружает содержимое веб-страницы с учетом кодировки (windows-1251), cookies (beget=begetok)
    и автоматического фолбэка на r.jina.ai при SPA / JS-защите (< 300 видимых символов).
    Возвращает кортеж (content, is_markdown).
    """
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        )
    }
    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True, cookies=cookies) as client:
        if use_jina_reader:
            md_text = await _fetch_via_jina_reader(client, url)
            return md_text, True

        resp = await client.get(url, headers=headers)
        resp.raise_for_status()
        decoded_html = resp.content.decode(encoding, errors="replace")

        soup = BeautifulSoup(decoded_html, "lxml")
        visible_text = soup.get_text(" ", strip=True)
        if len(visible_text) < 300 or "хостадмин.онлайн" in visible_text.lower():
            md_text = await _fetch_via_jina_reader(client, url)
            return md_text, True

        return decoded_html, False


class HttpCatalogSourceScraper:
    """Боевой адаптер обхода каталогов 9 утвержденных площадок заказчика."""

    async def fetch_catalog_urls(self, source: CustomerSourceConfig) -> list[str]:
        import app.services.scraper as scraper_pkg

        cookies_dict = dict(source.required_cookies) if source.required_cookies else None
        raw_content, _ = await _fetch_raw_page_content(
            source.catalog_url,
            encoding=source.encoding,
            use_jina_reader=source.use_jina_reader,
            cookies=cookies_dict,
        )
        return scraper_pkg.extract_filtered_card_urls(raw_content, source)


def _convert_html_to_dossier_markdown(html_content: str) -> str:
    """Преобразует HTML-страницу мероприятия в очищенный Markdown с сохранением Schema.org JSON-LD в начале досье."""
    soup = BeautifulSoup(html_content, "lxml")
    ld_blocks = [
        (s.string or "").strip()
        for s in soup.find_all("script", attrs={"type": "application/ld+json"})
        if (s.string or "").strip()
    ]
    for tag in soup(["script", "style", "noscript", "svg", "footer", "nav"]):
        tag.decompose()

    md_body = str(html_to_markdown(str(soup), heading_style="ATX")).strip()
    if ld_blocks:
        ld_section = "--- SCHEMA.ORG LD+JSON ---\n" + "\n".join(ld_blocks)
        return f"{ld_section}\n\n{md_body}".strip()
    return md_body


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
    cookies_dict = dict(source_config.required_cookies) if (source_config and source_config.required_cookies) else None

    content, is_markdown = await _fetch_raw_page_content(
        url,
        encoding=enc,
        use_jina_reader=use_jina,
        cookies=cookies_dict,
    )
    return content if is_markdown else _convert_html_to_dossier_markdown(content)
