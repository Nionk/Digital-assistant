import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

# Add backend directory to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.models.models import Event, ScraperRun, ScraperSeenUrl, ScraperSource
from app.services import scraper as scraper_pkg
from app.services.scraper import (
    CUSTOMER_SOURCES_REGISTRY,
    CaptchaBlockedError,
    CustomerSourceConfig,
    DiscoveredCandidate,
    DiscoveryResult,
    HttpCatalogSourceScraper,
    ScrapingRunSummary,
    UnsafeUrlError,
    canonicalize_url,
    ensure_builtin_scraper_sources,
    extract_discovery_candidates,
    extract_filtered_card_urls,
    run_customer_sources_monitoring,
    validate_safe_public_url,
)
from app.services.scraper.fetcher import _fetch_raw_page_content, _fetch_via_jina_reader

_PUBLIC_ADDRINFO = [(2, 1, 6, "", ("93.184.216.34", 0))]


def _make_source_row(cfg: CustomerSourceConfig, idx: int = 1) -> ScraperSource:
    return ScraperSource(
        id=idx,
        source_key=cfg.source_key,
        display_name=cfg.display_name,
        catalog_urls=list(cfg.catalog_urls),
        adapter_type=cfg.adapter_type,
        card_url_patterns=list(cfg.card_url_patterns),
        exclude_url_patterns=list(cfg.exclude_url_patterns),
        b2b_filter_enabled=cfg.b2b_filter_enabled,
        russia_online_only=cfg.russia_online_only,
        use_jina_reader=cfg.use_jina_reader,
        encoding=cfg.encoding,
        required_cookies=dict(cfg.required_cookies),
        max_urls_per_run=cfg.max_urls_per_run,
        is_enabled=cfg.is_enabled,
        is_builtin=cfg.is_builtin,
    )


def _mock_monitoring_session(
    *,
    source_rows: list[ScraperSource] | None = None,
    event_urls: list[list[str]] | None = None,
    seen_rows: list[ScraperSeenUrl] | None = None,
) -> AsyncMock:
    session = AsyncMock()
    session.add = MagicMock()
    session.new = set()

    s_rows = source_rows if source_rows is not None else [_make_source_row(c, i + 1) for i, c in enumerate(CUSTOMER_SOURCES_REGISTRY)]
    e_urls = event_urls if event_urls is not None else []
    u_rows = seen_rows if seen_rows is not None else []

    async def _execute(stmt):
        sql = str(stmt)
        res = MagicMock()
        if "FROM scraper_sources" in sql:
            res.scalars.return_value.all.return_value = list(s_rows)
        elif "FROM scraper_seen_urls" in sql:
            if "WHERE scraper_seen_urls.url =" in sql:
                res.scalar_one_or_none.return_value = None
            else:
                res.scalars.return_value.all.return_value = list(u_rows)
        elif "FROM events" in sql:
            res.scalars.return_value.all.return_value = list(e_urls)
        else:
            res.scalars.return_value.all.return_value = []
            res.scalar_one_or_none.return_value = None
        return res

    session.execute = AsyncMock(side_effect=_execute)
    return session


class TestPhase1ScraperModelsAndSeed(unittest.IsolatedAsyncioTestCase):
    """Тесты ORM-моделей Фазы 1, CustomerSourceConfig.from_orm и idempotent seed."""

    def test_orm_models_structure_and_defaults(self) -> None:
        self.assertEqual(ScraperSource.__tablename__, "scraper_sources")
        src_cols = ScraperSource.__table__.columns
        self.assertEqual(src_cols["adapter_type"].default.arg, "html_list")
        self.assertEqual(src_cols["encoding"].default.arg, "utf-8")
        self.assertEqual(src_cols["max_urls_per_run"].default.arg, 10)
        self.assertTrue(src_cols["russia_online_only"].default.arg)
        self.assertFalse(src_cols["b2b_filter_enabled"].default.arg)
        self.assertTrue(src_cols["is_enabled"].default.arg)
        self.assertFalse(src_cols["is_builtin"].default.arg)
        self.assertTrue(src_cols["source_key"].unique)

        # In-memory экземпляр с минимальными полями корректно преобразуется в CustomerSourceConfig
        src_minimal = ScraperSource(
            source_key="custom_expo",
            display_name="Custom Expo",
            catalog_urls=["https://example.com/events"],
        )
        cfg_minimal = CustomerSourceConfig.from_orm(src_minimal)
        self.assertEqual(cfg_minimal.adapter_type, "html_list")
        self.assertEqual(cfg_minimal.max_urls_per_run, 10)
        self.assertTrue(cfg_minimal.russia_online_only)
        self.assertTrue(cfg_minimal.is_enabled)

        self.assertEqual(ScraperSeenUrl.__tablename__, "scraper_seen_urls")
        seen_cols = ScraperSeenUrl.__table__.columns
        self.assertTrue(seen_cols["url"].unique)
        self.assertTrue(seen_cols["source_key"].index)
        self.assertTrue(seen_cols["outcome"].index)
        self.assertEqual(seen_cols["recheck_attempts"].default.arg, 0)

        seen = ScraperSeenUrl(
            url="https://example.com/events/1",
            source_key="custom_expo",
            outcome="ingested_needs_enrichment",
            recheck_attempts=0,
        )
        self.assertIsNone(seen.event_id)

        self.assertEqual(ScraperRun.__tablename__, "scraper_runs")
        run_cols = ScraperRun.__table__.columns
        self.assertTrue(run_cols["status"].index)
        self.assertEqual(run_cols["triggered_by"].default.arg, "manual")
        self.assertEqual(run_cols["urls_discovered"].default.arg, 0)
        self.assertEqual(run_cols["rejected_b2c"].default.arg, 0)
        self.assertEqual(run_cols["rejected_geo"].default.arg, 0)

    def test_customer_source_config_from_orm_and_registry(self) -> None:
        self.assertEqual(len(CUSTOMER_SOURCES_REGISTRY), 9)
        helpinver_row = _make_source_row(
            next(s for s in CUSTOMER_SOURCES_REGISTRY if s.source_key == "helpinver")
        )
        cfg = CustomerSourceConfig.from_orm(helpinver_row)
        self.assertIsInstance(cfg.catalog_urls, tuple)
        self.assertIsInstance(cfg.card_url_patterns, tuple)
        self.assertIsInstance(cfg.required_cookies, tuple)
        self.assertEqual(cfg.catalog_url, "https://helpinver.com/events/")
        self.assertEqual(cfg.required_cookies, (("beget", "begetok"),))

        archdialog = next(s for s in CUSTOMER_SOURCES_REGISTRY if s.source_key == "archdialog")
        self.assertEqual(archdialog.adapter_type, "manual_only")
        self.assertFalse(archdialog.is_enabled)

        votkuda = next(s for s in CUSTOMER_SOURCES_REGISTRY if s.source_key == "votkuda")
        self.assertTrue(votkuda.b2b_filter_enabled)
        self.assertEqual(votkuda.max_urls_per_run, 5)

        archdaily = next(s for s in CUSTOMER_SOURCES_REGISTRY if s.source_key == "archdaily")
        self.assertEqual(archdaily.adapter_type, "rss")
        self.assertTrue(archdaily.russia_online_only)

    async def test_ensure_builtin_scraper_sources_idempotent_preserves_user_flags(self) -> None:
        custom_existing = ScraperSource(
            id=1,
            source_key="expomap_construction",
            display_name="Expomap — Строительство",
            catalog_urls=["https://expomap.ru/expo/theme/stroitel-stvo/country/russia/"],
            is_enabled=False,
            max_urls_per_run=3,
            is_builtin=True,
        )
        session = _mock_monitoring_session(source_rows=[custom_existing])

        rows = await ensure_builtin_scraper_sources(session)
        self.assertEqual(len(rows), 9)
        self.assertEqual(session.add.call_count, 8)
        self.assertEqual(session.flush.await_count, 1)

        expomap_row = next(r for r in rows if r.source_key == "expomap_construction")
        self.assertFalse(expomap_row.is_enabled)
        self.assertEqual(expomap_row.max_urls_per_run, 3)


class TestPhase1UrlCanonicalizationAndSSRF(unittest.IsolatedAsyncioTestCase):
    """Тесты каноникализации URL и SSRF-валидатора validate_safe_public_url."""

    def test_canonicalize_url_strips_tracking_and_fragment_keeps_significant_query(self) -> None:
        raw = (
            "HTTPS://Example.COM:443/events/card?utm_source=tg&utm_medium=cpc"
            "&erid=2Vtzq&fbclid=1&yclid=2&gclid=3&ref=main&from=feed&_openstat=abc"
            "&id=123#registration"
        )
        self.assertEqual(
            canonicalize_url(raw),
            "https://example.com/events/card?id=123",
        )
        self.assertEqual(
            canonicalize_url("/events/123?id=42&utm_campaign=spring#top", base_url="https://SITE.RU/cat/"),
            "https://site.ru/events/123?id=42",
        )
        self.assertIsNone(canonicalize_url("file:///etc/passwd"))
        self.assertIsNone(canonicalize_url("javascript:alert(1)"))
        self.assertIsNone(canonicalize_url("#anchor-only"))

    async def test_validate_safe_public_url_blocks_internal_and_allows_public(self) -> None:
        blocked_urls = [
            "http://127.0.0.1/admin",
            "http://10.0.0.1/internal",
            "http://169.254.169.254/latest/meta-data/",
            "http://172.16.0.5:8080/",
            "http://192.168.1.1/",
            "http://[::1]/",
            "http://[::ffff:127.0.0.1]/",
            "http://localhost:8000/api",
            "http://backend.internal/health",
            "http://printer.local/",
            "file:///etc/passwd",
            "ftp://example.com/file.pdf",
        ]
        for bad_url in blocked_urls:
            with self.subTest(bad_url=bad_url), self.assertRaises(UnsafeUrlError):
                await validate_safe_public_url(bad_url)

        # DNS-rebinding защита: публичное имя резолвится во внутренний IP
        with (
            patch(
                "app.services.scraper.fetcher.socket.getaddrinfo",
                return_value=[(2, 1, 6, "", ("10.0.0.1", 0))],
            ),
            self.assertRaises(UnsafeUrlError),
        ):
            await validate_safe_public_url("https://rebind.example.com/event")

        # Валидный публичный хост проходит проверку
        with patch("app.services.scraper.fetcher.socket.getaddrinfo", return_value=_PUBLIC_ADDRINFO):
            safe = await validate_safe_public_url("https://expomap.ru/expo/mosbuild/")
            self.assertEqual(safe, "https://expomap.ru/expo/mosbuild/")


class TestPhase1DiscoveryAdapters(unittest.TestCase):
    """Тесты фильтрации ссылок всех исправленных источников, авто-экстрактора, XML/RSS и B2C/Geo фильтров."""

    def test_expomap_excludes_category_and_year_pages(self) -> None:
        src = next(s for s in CUSTOMER_SOURCES_REGISTRY if s.source_key == "expomap_construction")
        html = """
        <html><body>
          <a href="/expo/city/">Города</a>
          <a href="/expo/country/">Страны</a>
          <a href="/expo/theme/">Темы</a>
          <a href="/expo/venue/">Площадки</a>
          <a href="/expo/2026/">2026</a>
          <a href="/conference/city/">Конференции по городам</a>
          <a href="/expo/city/moscow/">Москва</a>
          <a href="/expo/mosbuild-2026/?utm_source=test">MosBuild 2026</a>
          <a href="/conference/stroitelnyi-forum-krt/">Строительный форум КРТ</a>
        </body></html>
        """
        urls = extract_filtered_card_urls(html, src)
        self.assertEqual(
            urls,
            [
                "https://expomap.ru/expo/mosbuild-2026/",
                "https://expomap.ru/conference/stroitelnyi-forum-krt/",
            ],
        )

    def test_helpinver_php_and_card_urls(self) -> None:
        src = next(s for s in CUSTOMER_SOURCES_REGISTRY if s.source_key == "helpinver")
        html = """
        <html><body>
          <a href="/events/">Все события</a>
          <a href="/about">О проекте</a>
          <a href="/events/rosbuild-2026.php">RosBuild 2026</a>
          <a href="/events/zodchestvo-forum/">Зодчество</a>
        </body></html>
        """
        urls = extract_filtered_card_urls(html, src)
        self.assertEqual(
            urls,
            [
                "https://helpinver.com/events/rosbuild-2026.php",
                "https://helpinver.com/events/zodchestvo-forum/",
            ],
        )

    def test_design_mate_html_and_zen_rss(self) -> None:
        src = next(s for s in CUSTOMER_SOURCES_REGISTRY if s.source_key == "design_mate")
        html = """
        <html><body>
          <a href="/read/go">Все события</a>
          <a href="/go/moskva/arch-summit-2026">Архитектурный саммит 2026</a>
          <a href="/go/moskva/spektakl-skazka">Детский спектакль 6+</a>
          <a href="/read/megapolis/dizain-sobytiya-noyabrya">Дизайн-события ноября</a>
        </body></html>
        """
        res_html = extract_discovery_candidates(html, src, base_url="https://design-mate.ru/read/go")
        self.assertEqual(res_html.rejected_b2c, 1)
        self.assertEqual(
            [c.url for c in res_html.candidates],
            [
                "https://design-mate.ru/go/moskva/arch-summit-2026",
                "https://design-mate.ru/read/megapolis/dizain-sobytiya-noyabrya",
            ],
        )
        self.assertTrue(res_html.candidates[1].is_digest)

        zen_rss = """<?xml version="1.0" encoding="utf-8"?>
        <rss version="2.0">
          <channel>
            <item>
              <title>Выставка интерьерного дизайна 2026</title>
              <link>https://design-mate.ru/go/moskva/interier-expo-2026?utm_source=zen</link>
              <description>Главная деловая выставка для дизайнеров и архитекторов.</description>
              <category>Дизайн</category>
              <pubDate>Mon, 16 Nov 2026 10:00:00 +0300</pubDate>
            </item>
            <item>
              <title>Концерт камерной музыки для всей семьи 6+</title>
              <link>https://design-mate.ru/go/moskva/chamber-concert-6plus</link>
              <description>Вечерний концерт классической музыки 6+.</description>
              <category>Музыка</category>
            </item>
          </channel>
        </rss>
        """
        res_rss = extract_discovery_candidates(zen_rss, src, base_url="https://design-mate.ru/zen")
        self.assertEqual(res_rss.rejected_b2c, 1)
        self.assertEqual(
            [c.url for c in res_rss.candidates],
            ["https://design-mate.ru/go/moskva/interier-expo-2026"],
        )

    def test_votkuda_b2c_prefilter_counts_and_b2b_override(self) -> None:
        src = next(s for s in CUSTOMER_SOURCES_REGISTRY if s.source_key == "votkuda")
        html = """
        <html><body>
          <article class="card">
            <h3><a href="/event/veselyi-spektakl-teremok/">Спектакль Теремок</a></h3>
            <p>Возрастной рейтинг 0+, представление детям.</p>
          </article>
          <article class="card">
            <h3><a href="/event/vystavka-zhivopisi-klassika/">Классическая живопись</a></h3>
            <p>Экскурсия по залам живописи и дегустация.</p>
          </article>
          <article class="card">
            <h3><a href="/event/ekskursiya-forum-stroiteley/">Экскурсия на строительный форум</a></h3>
            <p>Деловая программа для архитекторов и девелоперов.</p>
          </article>
          <article class="card">
            <h3><a href="/event/interier-design-summit/">Саммит дизайна и интерьера</a></h3>
            <p>Профессиональный B2B-саммит.</p>
          </article>
        </body></html>
        """
        result = extract_discovery_candidates(html, src)
        self.assertEqual(result.rejected_b2c, 2)
        self.assertEqual(
            [c.url for c in result.candidates],
            [
                "https://votkuda.ru/event/ekskursiya-forum-stroiteley/",
                "https://votkuda.ru/event/interier-design-summit/",
            ],
        )

    def test_archdaily_rss_geo_filter_and_xxe_safety(self) -> None:
        src = next(s for s in CUSTOMER_SOURCES_REGISTRY if s.source_key == "archdaily")
        rss_xml = """<?xml version="1.0" encoding="utf-8"?>
        <!DOCTYPE rss [
          <!ENTITY xxe SYSTEM "file:///etc/passwd">
        ]>
        <rss version="2.0">
          <channel>
            <item>
              <title>Venice Architecture Biennale 2026</title>
              <link>https://www.archdaily.com/101001/venice-biennale-2026</link>
              <description>International exhibition in Venice, Italy. Register online.</description>
              <category>Events</category>
            </item>
            <item>
              <title>Berlin Housing Summit</title>
              <link>https://www.archdaily.com/101002/berlin-housing-summit</link>
              <description>Urban development summit in Germany.</description>
              <category>Architecture</category>
            </item>
            <item>
              <title>Moscow Urban Forum 2026</title>
              <link>https://www.archdaily.com/101003/moscow-urban-forum-2026?utm_source=rss</link>
              <description>Major architecture and urbanism conference in Moscow, Russia.</description>
              <category>Russia</category>
            </item>
            <item>
              <title>Global Online Architecture Conference 2026</title>
              <link>https://www.archdaily.com/101004/global-online-architecture-conference</link>
              <description>Virtual webinar for architects and designers worldwide. &xxe;</description>
              <category>Online</category>
            </item>
          </channel>
        </rss>
        """
        result = extract_discovery_candidates(rss_xml, src)
        self.assertEqual(result.rejected_geo, 3)
        self.assertEqual(
            [c.url for c in result.candidates],
            [
                "https://www.archdaily.com/101003/moscow-urban-forum-2026",
            ],
        )

    def test_auto_extractor_without_regex_filters_boilerplate_and_pagination(self) -> None:
        custom_src = CustomerSourceConfig(
            source_key="new_ui_portal",
            display_name="Новый портал",
            catalog_urls=("https://events-portal.ru/catalog/",),
            card_url_patterns=(),
            exclude_url_patterns=(r"/archive/",),
        )
        html = """
        <html><body>
          <header><a href="/catalog/">Главная</a><a href="/login">Войти</a></header>
          <nav><a href="/about">О нас</a><a href="/contacts">Контакты</a></nav>
          <main>
            <a href="/events/forum-2026?id=123&utm_source=mail">Строительный форум 2026</a>
            <a href="/events/archive/old-2024">Архивный форум</a>
            <a href="/catalog/?page=2">Страница 2</a>
            <a href="/catalog/?PAGEN_1=3">Страница 3</a>
            <a href="/catalog/?month=11&year=2026">Ноябрь</a>
            <a href="/catalog/?sort=date">Сортировка</a>
            <a href="/tag/urban">Тег</a>
            <a href="/page/2">Пагинация</a>
            <a href="/search?q=bim">Поиск</a>
            <a href="https://t.me/events_channel">Telegram</a>
            <a href="/files/brochure.pdf">Брошюра PDF</a>
            <a href="/events/bim-congress">BIM Конгресс</a>
          </main>
          <aside><a href="/advertising">Реклама</a></aside>
          <footer><a href="/privacy">Политика</a></footer>
        </body></html>
        """
        urls = extract_filtered_card_urls(html, custom_src)
        self.assertEqual(
            urls,
            [
                "https://events-portal.ru/events/forum-2026?id=123",
                "https://events-portal.ru/events/bim-congress",
            ],
        )


class TestPhase1FetcherAndCaptchaFallback(unittest.IsolatedAsyncioTestCase):
    """Тесты порядка проверок в _fetch_raw_page_content: 403/хостадмин -> Jina, showcaptchafast -> ошибка без Jina."""

    async def test_403_and_hostadmin_fallback_to_jina_reader(self) -> None:
        req = httpx.Request("GET", "https://example.com/catalog/")

        for resp in (
            httpx.Response(403, content=b"Forbidden", request=req),
            httpx.Response(
                200,
                content="<html><body>Добро пожаловать на хостадмин.онлайн — заглушка хостинга для сайта.</body></html>".encode(),
                request=req,
            ),
        ):
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = False
            mock_client.get = AsyncMock(return_value=resp)

            with (
                patch("app.services.scraper.fetcher.socket.getaddrinfo", return_value=_PUBLIC_ADDRINFO),
                patch("app.services.scraper.fetcher.httpx.AsyncClient", return_value=mock_client),
                patch(
                    "app.services.scraper.fetcher._fetch_via_jina_reader",
                    new=AsyncMock(return_value="# Rendered MD"),
                ) as mock_jina,
            ):
                content, is_md = await _fetch_raw_page_content("https://example.com/catalog/")
                self.assertTrue(is_md)
                self.assertEqual(content, "# Rendered MD")
                self.assertEqual(mock_jina.await_count, 1)

    async def test_404_raises_http_status_error_without_jina(self) -> None:
        req = httpx.Request("GET", "https://example.com/missing")
        resp_404 = httpx.Response(404, content=b"Not Found", request=req)

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = False
        mock_client.get = AsyncMock(return_value=resp_404)

        with (
            patch("app.services.scraper.fetcher.socket.getaddrinfo", return_value=_PUBLIC_ADDRINFO),
            patch("app.services.scraper.fetcher.httpx.AsyncClient", return_value=mock_client),
            patch("app.services.scraper.fetcher._fetch_via_jina_reader", new=AsyncMock()) as mock_jina,
        ):
            with self.assertRaises(httpx.HTTPStatusError):
                await _fetch_raw_page_content("https://example.com/missing")
            self.assertEqual(mock_jina.await_count, 0)

    async def test_showcaptchafast_raises_without_calling_jina(self) -> None:
        req = httpx.Request("GET", "https://archdialog.timepad.ru/events/")
        captcha_html = (
            b"<html><body><script src='/showcaptchafast.js'></script>"
            b"<div>Please verify you are human</div></body></html>"
        )

        for status_code in (200, 403):
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = False
            mock_client.get = AsyncMock(
                return_value=httpx.Response(status_code, content=captcha_html, request=req)
            )
            with (
                patch("app.services.scraper.fetcher.socket.getaddrinfo", return_value=_PUBLIC_ADDRINFO),
                patch("app.services.scraper.fetcher.httpx.AsyncClient", return_value=mock_client),
                patch("app.services.scraper.fetcher._fetch_via_jina_reader", new=AsyncMock()) as mock_jina,
            ):
                with self.assertRaises(CaptchaBlockedError):
                    await _fetch_raw_page_content("https://archdialog.timepad.ru/events/")
                self.assertEqual(mock_jina.await_count, 0)

    async def test_jina_reader_validates_target_url_against_ssrf(self) -> None:
        mock_client = AsyncMock()
        with self.assertRaises(UnsafeUrlError):
            await _fetch_via_jina_reader(mock_client, "http://169.254.169.254/latest/meta-data/")
        self.assertEqual(mock_client.get.await_count, 0)

    async def test_http_catalog_scraper_merges_multiple_catalog_urls(self) -> None:
        src = next(s for s in CUSTOMER_SOURCES_REGISTRY if s.source_key == "design_mate")

        async def _fake_fetch(url: str, **kwargs):
            if url.endswith("/read/go"):
                html_go = (
                    "<html><body>"
                    "<a href='/go/moskva/arch-forum'>Архитектурный форум</a>"
                    "<a href='/go/moskva/balet-0'>Балет 0+</a>"
                    "</body></html>"
                )
                return html_go, False
            return (
                """<?xml version="1.0" encoding="utf-8"?>
                <feed xmlns="http://www.w3.org/2005/Atom">
                  <entry>
                    <title>Дизайн-конференция в Москве</title>
                    <link rel="alternate" href="https://design-mate.ru/go/moskva/design-conf?utm_source=zen"/>
                    <summary>Профессиональная конференция дизайна.</summary>
                  </entry>
                </feed>""",
                False,
            )

        scraper = HttpCatalogSourceScraper()
        with patch("app.services.scraper.fetcher._fetch_raw_page_content", new=AsyncMock(side_effect=_fake_fetch)):
            res = await scraper.discover_catalog(src)

        self.assertEqual(res.rejected_b2c, 1)
        self.assertEqual(
            [c.url for c in res.candidates],
            [
                "https://design-mate.ru/go/moskva/arch-forum",
                "https://design-mate.ru/go/moskva/design-conf",
            ],
        )


class TestPhase1MonitoringDryRunAndSeenUrls(unittest.IsolatedAsyncioTestCase):
    """Тесты dry_run=True (0 LLM/эмбеддингов/записей), recheck_attempts < 1 и manual_only."""

    async def test_dry_run_makes_zero_llm_embedding_and_db_writes(self) -> None:
        architime_cfg = next(s for s in CUSTOMER_SOURCES_REGISTRY if s.source_key == "architime")
        votkuda_cfg = next(s for s in CUSTOMER_SOURCES_REGISTRY if s.source_key == "votkuda")
        archdialog_cfg = next(s for s in CUSTOMER_SOURCES_REGISTRY if s.source_key == "archdialog")
        disabled_cfg = CustomerSourceConfig(
            source_key="expomap_design",
            display_name="Expomap — Дизайн",
            catalog_urls=("https://expomap.ru/expo/theme/mebel-inter-er-dekor/country/russia/",),
            is_enabled=False,
        )

        source_rows = [
            _make_source_row(architime_cfg, 1),
            _make_source_row(votkuda_cfg, 2),
            _make_source_row(archdialog_cfg, 3),
            _make_source_row(disabled_cfg, 4),
        ]

        # Заполняем seen_urls для проверки recheck_attempts < 1 и пропуска остальных
        seen_rows = [
            ScraperSeenUrl(
                url="https://www.architime.ru/activity/2026/ready.htm",
                source_key="architime",
                outcome="ingested_ready",
                recheck_attempts=0,
            ),
            ScraperSeenUrl(
                url="https://www.architime.ru/activity/2026/needs_recheck.htm",
                source_key="architime",
                outcome="ingested_needs_enrichment",
                recheck_attempts=0,
            ),
            ScraperSeenUrl(
                url="https://www.architime.ru/activity/2026/exhausted.htm",
                source_key="architime",
                outcome="ingested_needs_enrichment",
                recheck_attempts=1,
            ),
            ScraperSeenUrl(
                url="https://www.architime.ru/activity/2026/past.htm",
                source_key="architime",
                outcome="rejected_past",
                recheck_attempts=0,
            ),
            ScraperSeenUrl(
                url="https://www.architime.ru/activity/2026/retry_failed.htm",
                source_key="architime",
                outcome="failed",
                recheck_attempts=0,
            ),
        ]
        # needs_recheck.htm уже есть в events.source_urls (из первого прогона), но все равно должен попасть на 1 recheck!
        event_urls = [
            ["https://www.architime.ru/activity/2026/ready.htm"],
            ["https://www.architime.ru/activity/2026/needs_recheck.htm"],
        ]

        session = _mock_monitoring_session(
            source_rows=source_rows,
            event_urls=event_urls,
            seen_rows=seen_rows,
        )
        # Имитируем что все 9 builtin уже присутствуют, чтобы ensure_builtin не добавлял недостающие
        all_rows = list(source_rows) + [
            _make_source_row(
                CustomerSourceConfig(
                    source_key=s.source_key,
                    display_name=s.display_name,
                    catalog_urls=s.catalog_urls,
                    is_enabled=False,
                ),
                10 + i,
            )
            for i, s in enumerate(CUSTOMER_SOURCES_REGISTRY)
            if s.source_key not in {r.source_key for r in source_rows}
        ]
        session = _mock_monitoring_session(
            source_rows=all_rows,
            event_urls=event_urls,
            seen_rows=seen_rows,
        )

        class FakeDiscoveryScraper:
            async def discover_catalog(self, source: CustomerSourceConfig) -> DiscoveryResult:
                if source.source_key == "architime":
                    return DiscoveryResult(
                        candidates=[
                            DiscoveredCandidate(url="https://www.architime.ru/activity/2026/ready.htm", source_key="architime"),
                            DiscoveredCandidate(url="https://www.architime.ru/activity/2026/needs_recheck.htm", source_key="architime"),
                            DiscoveredCandidate(url="https://www.architime.ru/activity/2026/exhausted.htm", source_key="architime"),
                            DiscoveredCandidate(url="https://www.architime.ru/activity/2026/past.htm", source_key="architime"),
                            DiscoveredCandidate(url="https://www.architime.ru/activity/2026/retry_failed.htm", source_key="architime"),
                            DiscoveredCandidate(url="https://www.architime.ru/activity/2026/brand_new.htm", source_key="architime"),
                        ]
                    )
                if source.source_key == "votkuda":
                    return DiscoveryResult(
                        candidates=[
                            DiscoveredCandidate(url="https://votkuda.ru/event/urban-forum/", source_key="votkuda"),
                        ],
                        rejected_b2c=3,
                    )
                raise AssertionError(f"Неожиданный обход отключенного/manual источника: {source.source_key}")

            async def fetch_catalog_urls(self, source: CustomerSourceConfig) -> list[str]:
                res = await self.discover_catalog(source)
                return [c.url for c in res.candidates]

        with (
            patch.object(scraper_pkg, "fetch_url_dossier_text", new=AsyncMock()) as mock_fetch_card,
            patch.object(scraper_pkg, "ingest_event_from_text", new=AsyncMock()) as mock_ingest,
            patch.object(scraper_pkg, "get_embedding", new=AsyncMock()) as mock_emb,
            patch.object(scraper_pkg, "get_embeddings_batch", new=AsyncMock()) as mock_emb_batch,
            patch.object(scraper_pkg, "structured_llm_client", new=MagicMock()) as mock_llm,
        ):
            summary = await run_customer_sources_monitoring(
                session,
                catalog_scraper=FakeDiscoveryScraper(),
                dry_run=True,
                max_urls_per_source=5,
            )

            self.assertIsInstance(summary, ScrapingRunSummary)
            self.assertTrue(summary.dry_run)
            self.assertEqual(summary.checked_sources, 2)  # architime + votkuda (manual_only & disabled пропущены)
            self.assertEqual(summary.rejected_b2c_count, 3)
            self.assertEqual(summary.ingested_ready_count, 0)
            self.assertEqual(summary.needs_enrichment_count, 0)
            self.assertEqual(
                summary.candidate_urls_preview,
                [
                    "https://www.architime.ru/activity/2026/needs_recheck.htm",
                    "https://www.architime.ru/activity/2026/retry_failed.htm",
                    "https://www.architime.ru/activity/2026/brand_new.htm",
                    "https://votkuda.ru/event/urban-forum/",
                ],
            )
            self.assertEqual(summary.discovered_urls, 4)
            self.assertEqual(len(summary.per_source_report), 2)

            # 0 вызовов LLM, эмбеддингов, загрузки карточек и записи в БД
            self.assertEqual(mock_fetch_card.await_count, 0)
            self.assertEqual(mock_ingest.await_count, 0)
            self.assertEqual(mock_emb.await_count, 0)
            self.assertEqual(mock_emb_batch.await_count, 0)
            self.assertEqual(mock_llm.chat.completions.create.call_count, 0)
            self.assertEqual(session.add.call_count, 0)
            self.assertEqual(session.commit.await_count, 0)

    async def test_manual_only_source_raises_value_error(self) -> None:
        session = _mock_monitoring_session()
        with self.assertRaises(ValueError) as ctx:
            await run_customer_sources_monitoring(session, source_key="archdialog", dry_run=True)
        self.assertIn("ручного Умного импорта", str(ctx.exception))

    async def test_non_dry_run_updates_seen_urls_and_increments_recheck_attempts(self) -> None:
        architime_cfg = next(s for s in CUSTOMER_SOURCES_REGISTRY if s.source_key == "architime")
        seen_recheck = ScraperSeenUrl(
            id=10,
            url="https://www.architime.ru/activity/2026/needs_recheck.htm",
            source_key="architime",
            outcome="ingested_needs_enrichment",
            event_id=77,
            recheck_attempts=0,
        )
        source_rows = [_make_source_row(architime_cfg, 1)]
        session = _mock_monitoring_session(source_rows=source_rows, seen_rows=[seen_recheck])

        # При запросе select(ScraperSeenUrl).where(...) вернем существующую строку для needs_recheck
        async def _custom_execute(stmt):
            sql = str(stmt)
            res = MagicMock()
            if "FROM scraper_sources" in sql:
                res.scalars.return_value.all.return_value = list(source_rows)
            elif "FROM scraper_seen_urls" in sql:
                if "WHERE scraper_seen_urls.url =" in sql:
                    params = stmt.compile().params
                    url_param = next(iter(params.values()), "")
                    res.scalar_one_or_none.return_value = (
                        seen_recheck if "needs_recheck" in str(url_param) else None
                    )
                else:
                    res.scalars.return_value.all.return_value = [seen_recheck]
            else:
                res.scalars.return_value.all.return_value = []
                res.scalar_one_or_none.return_value = None
            return res

        session.execute = AsyncMock(side_effect=_custom_execute)

        class FakeOneSourceScraper:
            async def fetch_catalog_urls(self, source: CustomerSourceConfig) -> list[str]:
                return [
                    "https://www.architime.ru/activity/2026/needs_recheck.htm",
                    "https://www.architime.ru/activity/2026/new_ok.htm",
                ]

        fake_ev_ready = Event(id=88, canonical_title="Форум Готовый", data_status="ready")

        with (
            patch.object(scraper_pkg, "fetch_url_dossier_text", new=AsyncMock(return_value="Досье")),
            patch.object(scraper_pkg, "ingest_event_from_text", new=AsyncMock(return_value=fake_ev_ready)),
        ):
            summary = await run_customer_sources_monitoring(
                session,
                source_key="architime",
                catalog_scraper=FakeOneSourceScraper(),
                dry_run=False,
            )

        self.assertFalse(summary.dry_run)
        self.assertEqual(summary.ingested_ready_count, 2)
        self.assertEqual(seen_recheck.outcome, "ingested_ready")
        self.assertEqual(seen_recheck.recheck_attempts, 1)
        self.assertEqual(seen_recheck.event_id, 88)
        added_seen = [call.args[0] for call in session.add.call_args_list if isinstance(call.args[0], ScraperSeenUrl)]
        self.assertEqual(len(added_seen), 1)
        self.assertEqual(added_seen[0].url, "https://www.architime.ru/activity/2026/new_ok.htm")
        self.assertEqual(added_seen[0].outcome, "ingested_ready")
        self.assertEqual(added_seen[0].recheck_attempts, 0)


if __name__ == "__main__":
    unittest.main()
