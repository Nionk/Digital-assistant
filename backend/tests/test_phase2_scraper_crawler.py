import datetime
import sys
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pymupdf as fitz

# Add backend directory to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.models.models import Event, ScraperSeenUrl, ScraperSource
from app.schemas.event_ingestion import EventIngestionSchema
from app.services import scraper as scraper_pkg
from app.services.scraper import (
    CUSTOMER_SOURCES_REGISTRY,
    CandidateTriageDecision,
    CaptchaBlockedError,
    CollectedEventDossier,
    CustomerSourceConfig,
    DiscoveredCandidate,
    EventRejectedError,
    OcrBudgetTracker,
    OrganizerLinksSelection,
    UnsafeUrlError,
    collect_event_dossier,
    collect_event_dossiers,
    extract_discovery_candidates,
    fetch_pdf_bytes_safe,
    ingest_event_from_text,
    is_russia_or_online_event,
    run_customer_sources_monitoring,
    triage_discovery_candidate,
)
from app.services.scraper import fetcher as fetcher_mod
from app.services.scraper.crawler import (
    _convert_organizer_html_to_markdown,
    _discover_official_site_and_card_pdfs,
    _extract_organizer_candidate_links,
    _score_organizer_link,
    is_document_candidate_url,
)
from app.services.scraper.fetcher import resolve_cloud_pdf_urls
from app.services.scraper.sources import _is_obvious_b2c, _passes_russia_online_geo

_PUBLIC_ADDRINFO = [(2, 1, 6, "", ("93.184.216.34", 0))]


def _make_sample_pdf_bytes(page1_text: str, page2_text: str | None = None) -> bytes:
    doc = fitz.open()
    p1 = doc.new_page()
    p1.insert_text((50, 72), page1_text)
    if page2_text:
        p2 = doc.new_page()
        p2.insert_text((50, 72), page2_text)
    data = doc.tobytes()
    doc.close()
    return data


def _make_long_pdf_bytes(marker: str) -> bytes:
    """PDF с текстовым слоем >= 50 символов на странице (иначе страница считается сканом)."""
    return _make_sample_pdf_bytes(f"{marker}. Подробное описание условий участия, тарифов и регламента форума.")


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


def _valid_summary(prefix: str = "Ключевой отраслевой форум для архитекторов и девелоперов.") -> str:
    return (
        f"{prefix} Участники обсуждают комплексное развитие территорий, проектирование жилых "
        "и коммерческих кластеров, цифровые BIM-стандарты, инженерные решения, экономику проектов "
        "и взаимодействие с профильными институтами развития и городскими администрациями."
    )


class TestPhase2ReviewFixes(unittest.IsolatedAsyncioTestCase):
    """Тесты исправлений Фазы 1 (Блок 0)."""

    def test_archdaily_rejects_online_platform_and_global_webinars_allows_rf(self) -> None:
        archdaily_src = next(s for s in CUSTOMER_SOURCES_REGISTRY if s.source_key == "archdaily")
        rss_xml = """<?xml version="1.0" encoding="utf-8"?>
        <rss version="2.0">
          <channel>
            <item>
              <title>ATN Summit: From an Online Platform</title>
              <link>https://www.archdaily.com/102001/atn-summit-online-platform</link>
              <description>Physical summit on digital workflows in Zurich, Switzerland.</description>
              <category>Events</category>
            </item>
            <item>
              <title>Global Online Architecture Webinar 2026</title>
              <link>https://www.archdaily.com/102002/global-online-webinar</link>
              <description>Free virtual webinar for architects worldwide.</description>
              <category>Online</category>
            </item>
            <item>
              <title>Saint Petersburg Urban Design Conference</title>
              <link>https://www.archdaily.com/102003/spb-urban-conf</link>
              <description>Annual architecture conference in Saint Petersburg, Russia.</description>
              <category>Architecture</category>
            </item>
          </channel>
        </rss>
        """
        result = extract_discovery_candidates(rss_xml, archdaily_src)
        self.assertEqual(result.rejected_geo, 2)
        self.assertEqual(
            [c.url for c in result.candidates],
            ["https://www.archdaily.com/102003/spb-urban-conf"],
        )
        # Для глобальных источников _ONLINE_TITLE_RE удален: "From an Online Platform" не проходит
        self.assertFalse(
            _passes_russia_online_geo(
                "ATN Summit: From an Online Platform",
                "Conference in Switzerland",
                "Events",
                allow_global_online=True,
            )
        )
        self.assertTrue(
            _passes_russia_online_geo(
                "Global Online Architecture Webinar",
                "Virtual webinar for architects",
                "Events",
                allow_global_online=True,
            )
        )

    def test_card_context_4_links_and_duplicate_anchor_preserves_real_title(self) -> None:
        src = next(s for s in CUSTOMER_SOURCES_REGISTRY if s.source_key == "votkuda")
        html = """
        <html><body>
          <article class="card">
            <a class="card__media" href="/event/arch-forum-msk/">Бесплатно</a>
            <div class="card__body">
              <h3 class="card__title"><a href="/event/arch-forum-msk/">Московский архитектурный форум 2026</a></h3>
              <a class="card__venue" href="/venue/manege">ЦВЗ Манеж</a>
              <a class="card__tag" href="/tag/architecture">Архитектура</a>
              <p class="card__meta">18 ноября, деловая программа для девелоперов</p>
            </div>
          </article>
          <article class="card">
            <a class="card__media" href="/event/design-conf-spb/">Подробнее</a>
            <h3 class="card__title"><a href="/event/design-conf-spb/">Конференция интерьерного дизайна</a></h3>
          </article>
        </body></html>
        """
        res = extract_discovery_candidates(html, src)
        self.assertEqual(
            [c.url for c in res.candidates],
            [
                "https://votkuda.ru/event/arch-forum-msk/",
                "https://votkuda.ru/event/design-conf-spb/",
            ],
        )
        self.assertEqual(res.candidates[0].title, "Московский архитектурный форум 2026")
        self.assertIn("ЦВЗ Манеж", res.candidates[0].snippet)
        self.assertEqual(res.candidates[1].title, "Конференция интерьерного дизайна")

    def test_age_tag_6plus_with_design_is_still_b2c_unless_strong_b2b(self) -> None:
        self.assertTrue(_is_obvious_b2c("Детский кружок дизайн и архитектура 6+"))
        self.assertTrue(_is_obvious_b2c("Мастер-класс интерьер 12+"))
        self.assertFalse(_is_obvious_b2c("Международный архитектурный форум (6+)"))
        self.assertFalse(_is_obvious_b2c("B2B конференция по дизайну 0+"))

    async def test_seen_url_trailing_slash_updates_single_row_and_recheck_attempts(self) -> None:
        votkuda_cfg = next(s for s in CUSTOMER_SOURCES_REGISTRY if s.source_key == "votkuda")
        src_row = _make_source_row(CustomerSourceConfig(**{**votkuda_cfg.__dict__, "b2b_filter_enabled": False}), 1)
        stored_rows: dict[str, ScraperSeenUrl] = {}

        async def _execute(stmt):
            sql = str(stmt)
            res = MagicMock()
            if "FROM scraper_sources" in sql:
                res.scalars.return_value.all.return_value = [src_row]
            elif "FROM scraper_seen_urls" in sql:
                if "WHERE scraper_seen_urls.url =" in sql:
                    params = stmt.compile().params
                    u_param = str(next(iter(params.values()), ""))
                    res.scalar_one_or_none.return_value = stored_rows.get(u_param)
                else:
                    res.scalars.return_value.all.return_value = list(stored_rows.values())
            else:
                res.scalars.return_value.all.return_value = []
                res.scalar_one_or_none.return_value = None
            return res

        session = AsyncMock()
        session.new = set()
        session.execute = AsyncMock(side_effect=_execute)

        def _add(obj):
            if isinstance(obj, ScraperSeenUrl):
                stored_rows[obj.url] = obj

        session.add = MagicMock(side_effect=_add)

        class Run1Scraper:
            async def fetch_catalog_urls(self, source: CustomerSourceConfig) -> list[str]:
                return ["https://votkuda.ru/event/foo/"]

        class Run2Scraper:
            async def fetch_catalog_urls(self, source: CustomerSourceConfig) -> list[str]:
                return ["https://votkuda.ru/event/foo"]

        ev_needs = Event(id=10, canonical_title="Форум Foo", data_status="needs_enrichment")
        ev_ready = Event(id=10, canonical_title="Форум Foo", data_status="ready")

        with (
            patch.object(
                scraper_pkg,
                "collect_event_dossier",
                new=AsyncMock(
                    return_value=CollectedEventDossier(
                        dossier_text="Досье",
                        source_urls=["https://votkuda.ru/event/foo/"],
                    )
                ),
            ),
            patch.object(scraper_pkg, "ingest_event_from_text", new=AsyncMock(return_value=ev_needs)),
        ):
            await run_customer_sources_monitoring(
                session,
                source_key="votkuda",
                catalog_scraper=Run1Scraper(),
                dry_run=False,
            )

        self.assertEqual(len(stored_rows), 1)
        self.assertIn("https://votkuda.ru/event/foo", stored_rows)
        self.assertEqual(stored_rows["https://votkuda.ru/event/foo"].recheck_attempts, 0)
        self.assertEqual(stored_rows["https://votkuda.ru/event/foo"].outcome, "ingested_needs_enrichment")

        with (
            patch.object(
                scraper_pkg,
                "collect_event_dossier",
                new=AsyncMock(
                    return_value=CollectedEventDossier(
                        dossier_text="Обогащенное досье",
                        source_urls=["https://votkuda.ru/event/foo"],
                    )
                ),
            ),
            patch.object(scraper_pkg, "ingest_event_from_text", new=AsyncMock(return_value=ev_ready)),
        ):
            await run_customer_sources_monitoring(
                session,
                source_key="votkuda",
                catalog_scraper=Run2Scraper(),
                dry_run=False,
            )

        self.assertEqual(len(stored_rows), 1)
        row = stored_rows["https://votkuda.ru/event/foo"]
        self.assertEqual(row.outcome, "ingested_ready")
        self.assertEqual(row.recheck_attempts, 1)


class TestPhase2SafePdfDownload(unittest.IsolatedAsyncioTestCase):
    """Тесты безопасного потокового скачивания PDF fetch_pdf_bytes_safe."""

    async def test_fetch_pdf_bytes_safe_success_and_octet_stream(self) -> None:
        pdf_payload = _make_sample_pdf_bytes(
            "Forum Brochure 2026: tariffs, speaker package, Early Bird 50000 rub."
        )

        def _handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/direct.pdf"):
                return httpx.Response(
                    200,
                    content=pdf_payload,
                    headers={
                        "Content-Type": "application/pdf",
                        "Content-Length": str(len(pdf_payload)),
                    },
                )
            return httpx.Response(
                200,
                content=pdf_payload,
                headers={"Content-Type": "application/octet-stream"},
            )

        real_async_client = httpx.AsyncClient
        transport = httpx.MockTransport(_handler)

        def _client_factory(**kwargs):
            kwargs["transport"] = transport
            return real_async_client(**kwargs)

        with (
            patch("app.services.scraper.fetcher.socket.getaddrinfo", return_value=_PUBLIC_ADDRINFO),
            patch("app.services.scraper.fetcher.httpx.AsyncClient", side_effect=_client_factory),
        ):
            data1 = await fetch_pdf_bytes_safe("https://example.ru/files/direct.pdf")
            data2 = await fetch_pdf_bytes_safe("https://example.ru/files/brochure.pdf")

        self.assertEqual(data1, pdf_payload)
        self.assertEqual(data2, pdf_payload)

    async def test_fetch_pdf_bytes_safe_blocks_oversized_content_length_and_streaming(self) -> None:
        class _ChunkStream(httpx.AsyncByteStream):
            async def __aiter__(self):
                yield b"%PDF-1.4 "
                for _ in range(10):
                    yield b"A" * 512

        def _handler(request: httpx.Request) -> httpx.Response:
            if "by-header" in request.url.path:
                return httpx.Response(
                    200,
                    content=b"%PDF-1.4 short",
                    headers={
                        "Content-Type": "application/pdf",
                        "Content-Length": "9999999",
                    },
                )
            # Без Content-Length: потоковые чанки превышают max_bytes
            return httpx.Response(
                200,
                stream=_ChunkStream(),
                headers={"Content-Type": "application/pdf"},
            )

        real_async_client = httpx.AsyncClient
        transport = httpx.MockTransport(_handler)

        def _client_factory(**kwargs):
            kwargs["transport"] = transport
            return real_async_client(**kwargs)

        with (
            patch("app.services.scraper.fetcher.socket.getaddrinfo", return_value=_PUBLIC_ADDRINFO),
            patch("app.services.scraper.fetcher.httpx.AsyncClient", side_effect=_client_factory),
        ):
            with self.assertRaises(ValueError) as ctx_header:
                await fetch_pdf_bytes_safe("https://example.ru/by-header.pdf", max_bytes=1024)
            self.assertIn("лимит", str(ctx_header.exception))

            with self.assertRaises(ValueError) as ctx_stream:
                await fetch_pdf_bytes_safe("https://example.ru/by-stream.pdf", max_bytes=1024)
            self.assertIn("Потоковое скачивание", str(ctx_stream.exception))

    async def test_fetch_pdf_bytes_safe_blocks_non_pdf_and_ssrf_redirect(self) -> None:
        def _handler(request: httpx.Request) -> httpx.Response:
            if "html-page" in request.url.path:
                return httpx.Response(
                    200,
                    content=b"<html><body>Not a PDF</body></html>",
                    headers={"Content-Type": "text/html; charset=utf-8"},
                )
            if "fake-magic" in request.url.path:
                return httpx.Response(
                    200,
                    content=b"<html>Not a PDF magic</html>",
                    headers={"Content-Type": "application/pdf"},
                )
            if "redirect-ssrf" in request.url.path:
                return httpx.Response(
                    302,
                    headers={"Location": "http://127.0.0.1/secret.pdf"},
                )
            return httpx.Response(404)

        real_async_client = httpx.AsyncClient
        transport = httpx.MockTransport(_handler)

        def _client_factory(**kwargs):
            kwargs["transport"] = transport
            return real_async_client(**kwargs)

        with (
            patch("app.services.scraper.fetcher.socket.getaddrinfo", return_value=_PUBLIC_ADDRINFO),
            patch("app.services.scraper.fetcher.httpx.AsyncClient", side_effect=_client_factory),
        ):
            with self.assertRaises(ValueError):
                await fetch_pdf_bytes_safe("https://example.ru/html-page.pdf")

            with self.assertRaises(ValueError):
                await fetch_pdf_bytes_safe("https://example.ru/fake-magic.pdf")

            with self.assertRaises(UnsafeUrlError):
                await fetch_pdf_bytes_safe("https://example.ru/redirect-ssrf.pdf")


class TestPhase2CrawlerAndTriage(unittest.IsolatedAsyncioTestCase):
    """Тесты 2-Hop краулера, дайджеста и дешевого LLM-триажа."""

    async def test_crawler_ignores_aggregator_footer_mediakit_captures_org_nav_and_pdf(self) -> None:
        expomap_src = next(s for s in CUSTOMER_SOURCES_REGISTRY if s.source_key == "expomap_construction")
        candidate = DiscoveredCandidate(
            url="https://expomap.ru/expo/mosbuild-2026/",
            title="MosBuild 2026",
            source_key="expomap_construction",
        )
        agg_html = """
        <html><body>
          <header><nav><a href="/mediakit_header.pdf">Медиакит</a></nav></header>
          <main>
            <script type="application/ld+json">
              {"@type": "Event", "url": "https://expomap.ru/expo/mosbuild-2026/", "offers": {"url": "https://mosbuild-official.ru/"}}
            </script>
            <h1>MosBuild 2026</h1>
            <p>Крупнейшая строительная выставка в Москве, Крокус Экспо.</p>
            <a href="https://vk.com/mosbuild">VK</a>
            <a href="https://yandex.ru/maps/213/moscow">Карта</a>
            <a href="https://top.mail.ru/rating">Счетчик</a>
          </main>
          <footer><a href="/files/mediakit_2026.pdf">Медиакит портала 2026</a></footer>
        </body></html>
        """
        org_home_html = """
        <html><body>
          <header>
            <nav>
              <a href="/tariffs">Тарифы и участие</a>
              <a href="/program">Программа форума</a>
              <a href="/files/price_2026.pdf">Прайс-лист КП PDF</a>
            </nav>
          </header>
          <main><h1>MosBuild Official</h1><p>Форум и выставка строительных технологий.</p></main>
          <footer><a href="/privacy">Политика</a></footer>
        </body></html>
        """
        org_tariffs_html = """
        <html><body>
          <main>
            <h2>Тарифы делегата и спикера</h2>
            <p>Пакет Делегат: 45 000 руб. с НДС. Пакет Спикер: 150 000 руб.</p>
          </main>
        </body></html>
        """
        pdf_bytes = _make_sample_pdf_bytes(
            "Commercial Proposal MosBuild 2026: architecture and construction forum.",
            "Sponsor tariff package price: 300 000 RUB, Early Bird discount 15% before Dec 1.",
        )

        fetched_urls: list[str] = []

        async def _fake_fetch_page(url: str, **kwargs):
            fetched_urls.append(url)
            if url == "https://expomap.ru/expo/mosbuild-2026/":
                return agg_html, False
            if url == "https://mosbuild-official.ru/":
                return org_home_html, False
            if url == "https://mosbuild-official.ru/tariffs":
                return org_tariffs_html, False
            if url == "https://mosbuild-official.ru/program":
                return "<html><body><main><p>Пленарная сессия в 10:00</p></main></body></html>", False
            raise AssertionError(f"Неожиданный URL: {url}")

        downloaded_pdfs: list[str] = []

        async def _fake_fetch_pdf(url: str, **kwargs):
            downloaded_pdfs.append(url)
            return pdf_bytes

        mock_llm = MagicMock()
        mock_llm.chat.completions.create = AsyncMock(
            return_value=OrganizerLinksSelection(
                html_subpage_urls=["https://mosbuild-official.ru/tariffs"],
                pdf_urls=["https://mosbuild-official.ru/files/price_2026.pdf"],
            )
        )

        with (
            patch("app.services.scraper.fetcher._fetch_raw_page_content", new=AsyncMock(side_effect=_fake_fetch_page)),
            patch("app.services.scraper.fetcher.fetch_pdf_bytes_safe", new=AsyncMock(side_effect=_fake_fetch_pdf)),
            patch.object(scraper_pkg.settings, "LLM_API_KEY", "test-key"),
            patch.object(scraper_pkg, "structured_llm_client", new=mock_llm),
        ):
            dossier = await collect_event_dossier(candidate, expomap_src)

        self.assertEqual(dossier.official_site_url, "https://mosbuild-official.ru/")
        self.assertEqual(downloaded_pdfs, ["https://mosbuild-official.ru/files/price_2026.pdf"])
        self.assertNotIn("mediakit_2026.pdf", dossier.dossier_text)
        self.assertNotIn("mediakit_header.pdf", dossier.dossier_text)
        self.assertIn("45 000 руб", dossier.dossier_text)
        self.assertIn("300 000 RUB", dossier.dossier_text)
        self.assertEqual(
            dossier.source_urls,
            [
                "https://expomap.ru/expo/mosbuild-2026/",
                "https://mosbuild-official.ru/",
                "https://mosbuild-official.ru/tariffs",
                "https://mosbuild-official.ru/files/price_2026.pdf",
            ],
        )

    async def test_crawler_resilient_to_403_and_captcha_on_official_site(self) -> None:
        architime_src = next(s for s in CUSTOMER_SOURCES_REGISTRY if s.source_key == "architime")
        candidate = DiscoveredCandidate(
            url="https://www.architime.ru/activity/2026/arch_forum.htm",
            title="АрхФорум",
            source_key="architime",
        )
        agg_html = """
        <html><body>
          <main>
            <h1>АрхФорум 2026</h1>
            <p>Официальный сайт: <a href="https://archforum-blocked.ru/">archforum-blocked.ru</a></p>
            <p>Москва, 20 ноября 2026.</p>
          </main>
        </body></html>
        """

        async def _fake_fetch(url: str, **kwargs):
            if "architime.ru" in url:
                return agg_html, False
            raise CaptchaBlockedError("Protected by SmartCaptcha")

        with patch("app.services.scraper.fetcher._fetch_raw_page_content", new=AsyncMock(side_effect=_fake_fetch)):
            dossier = await collect_event_dossier(candidate, architime_src)

        self.assertIn("АрхФорум 2026", dossier.dossier_text)
        self.assertIn("official_site_unreachable", dossier.warnings)
        self.assertEqual(dossier.source_urls, ["https://www.architime.ru/activity/2026/arch_forum.htm"])

    async def test_crawler_digest_splits_h2_h3_filters_b2c_and_keeps_top3_b2b(self) -> None:
        dm_src = next(s for s in CUSTOMER_SOURCES_REGISTRY if s.source_key == "design_mate")
        candidate = DiscoveredCandidate(
            url="https://design-mate.ru/read/megapolis/events-november-2026",
            title="Дайджест событий ноября",
            source_key="design_mate",
            is_digest=True,
        )
        digest_html = """
        <html><body>
          <header><a href="/mediakit.pdf">Медиакит</a></header>
          <article>
            <p>Подборка главных событий месяца.</p>
            <h2>Детский спектакль-сказка 6+</h2>
            <p>Веселое театральное представление 6+ для всей семьи в выходные.</p>
            <h2>Форум интерьерного дизайна и архитектуры 2026</h2>
            <p>Деловая программа для архитекторов и студий дизайна, тарифы участия от 25 000 руб.
               <a href="https://interior-forum.ru/">Сайт форума</a>
            </p>
            <h2>Конференция девелоперов и урбанистов КРТ</h2>
            <p>Профессиональный конгресс по урбанистике, BIM и девелопменту в Москве.
               <a href="https://krt-conf.ru/">Регистрация</a>
            </p>
            <h2>Выставка промышленного дизайна</h2>
            <p>Профессиональная выставка предметов интерьера и материалов для дизайнеров.
               <a href="https://promdesign-expo.ru/">Официальный сайт</a>
            </p>
            <h2>Саммит строительных технологий и инженерии</h2>
            <p>Крупнейший B2B саммит по строительству, девелопменту, проектированию и тарифам спикеров.
               <a href="https://build-tech-summit.ru/">Перейти на сайт</a>
            </p>
          </article>
          <footer><a href="/privacy">Политика</a></footer>
        </body></html>
        """

        with patch(
            "app.services.scraper.fetcher._fetch_raw_page_content",
            new=AsyncMock(return_value=(digest_html, False)),
        ):
            dossier = await collect_event_dossier(candidate, dm_src)

        self.assertNotIn("спектакль-сказка", dossier.dossier_text.lower())
        self.assertNotIn("mediakit.pdf", dossier.dossier_text)
        # Ровно до 3 самых релевантных B2B-секций
        section_headings = [line for line in dossier.dossier_text.splitlines() if line.startswith("## ")]
        self.assertEqual(len(section_headings), 3)
        self.assertIn("https://", dossier.dossier_text)
        self.assertEqual(dossier.source_urls, [candidate.url])

    async def test_triage_fail_open_without_key_and_stops_before_2hop_and_llm3(self) -> None:
        votkuda_cfg = next(s for s in CUSTOMER_SOURCES_REGISTRY if s.source_key == "votkuda")
        cand_b2c = DiscoveredCandidate(
            url="https://votkuda.ru/event/poster-art/",
            title="Выставка советского плаката",
            snippet="Экспозиция афиш и живописи в галерее",
            source_key="votkuda",
        )
        cand_geo = DiscoveredCandidate(
            url="https://votkuda.ru/event/milan-trip/",
            title="Миланская неделя дизайна — выездной тур",
            snippet="Поездка в Милан, Италия",
            source_key="votkuda",
        )

        # Без LLM_API_KEY триаж не падает и пропускает
        with patch.object(scraper_pkg.settings, "LLM_API_KEY", ""):
            res_no_key = await triage_discovery_candidate(cand_b2c, votkuda_cfg)
            self.assertTrue(res_no_key.is_b2b_target)
            self.assertTrue(res_no_key.is_russia_or_online)

        src_row = _make_source_row(votkuda_cfg, 1)
        stored_seen: dict[str, ScraperSeenUrl] = {}

        async def _execute(stmt):
            sql = str(stmt)
            res = MagicMock()
            if "FROM scraper_sources" in sql:
                res.scalars.return_value.all.return_value = [src_row]
            elif "FROM scraper_seen_urls" in sql:
                if "WHERE scraper_seen_urls.url =" in sql:
                    params = stmt.compile().params
                    u_param = str(next(iter(params.values()), ""))
                    res.scalar_one_or_none.return_value = stored_seen.get(u_param)
                else:
                    res.scalars.return_value.all.return_value = list(stored_seen.values())
            else:
                res.scalars.return_value.all.return_value = []
                res.scalar_one_or_none.return_value = None
            return res

        session = AsyncMock()
        session.new = set()
        session.execute = AsyncMock(side_effect=_execute)
        session.add = MagicMock(
            side_effect=lambda obj: stored_seen.__setitem__(obj.url, obj)
            if isinstance(obj, ScraperSeenUrl)
            else None
        )

        class FakeVotkudaDiscovery:
            async def discover_catalog(self, source: CustomerSourceConfig):
                from app.services.scraper import DiscoveryResult

                return DiscoveryResult(candidates=[cand_b2c, cand_geo])

            async def fetch_catalog_urls(self, source: CustomerSourceConfig) -> list[str]:
                return [cand_b2c.url, cand_geo.url]

        async def _fake_triage(cand: DiscoveredCandidate, source: CustomerSourceConfig) -> CandidateTriageDecision:
            if "poster-art" in cand.url:
                return CandidateTriageDecision(
                    is_b2b_target=False,
                    is_russia_or_online=True,
                    reason="Художественная выставка плакатов (B2C)",
                )
            return CandidateTriageDecision(
                is_b2b_target=True,
                is_russia_or_online=False,
                reason="Мероприятие в Италии, вне РФ",
            )

        with (
            patch.object(scraper_pkg, "triage_discovery_candidate", new=AsyncMock(side_effect=_fake_triage)),
            patch.object(scraper_pkg, "collect_event_dossier", new=AsyncMock()) as mock_2hop,
            patch.object(scraper_pkg, "ingest_event_from_text", new=AsyncMock()) as mock_llm3,
            patch.object(scraper_pkg, "get_embedding", new=AsyncMock()) as mock_emb,
        ):
            summary = await run_customer_sources_monitoring(
                session,
                source_key="votkuda",
                catalog_scraper=FakeVotkudaDiscovery(),
                dry_run=False,
            )

        self.assertEqual(mock_2hop.await_count, 0)
        self.assertEqual(mock_llm3.await_count, 0)
        self.assertEqual(mock_emb.await_count, 0)
        self.assertEqual(summary.rejected_b2c_count, 1)
        self.assertEqual(summary.rejected_geo_count, 1)
        self.assertEqual(stored_seen["https://votkuda.ru/event/poster-art"].outcome, "rejected_b2c")
        self.assertEqual(stored_seen["https://votkuda.ru/event/milan-trip"].outcome, "rejected_geo")

    async def test_crawler_deterministic_fallback_without_llm_key_and_dossier_budget(self) -> None:
        helpinver_src = next(s for s in CUSTOMER_SOURCES_REGISTRY if s.source_key == "helpinver")
        candidate = DiscoveredCandidate(
            url="https://helpinver.com/events/big-forum/",
            title="Большой строительный форум",
            source_key="helpinver",
        )
        huge_body = "Описание события. " * 3000  # ~54 000 символов!
        agg_html = f"""
        <html><body><main>
          <h1>Большой строительный форум</h1>
          <p>{huge_body}</p>
          <p><a href="https://bigforum-official.ru/">Официальный сайт мероприятия</a></p>
        </main></body></html>
        """
        org_home_html = f"""
        <html><body>
          <nav>
            <a href="/tariffs">Тарифы участия</a>
            <a href="/privacy">Политика конфиденциальности</a>
            <a href="/files/reglament.pdf">Регламент PDF</a>
          </nav>
          <main><p>{'Текст главной страницы. ' * 2000}</p></main>
        </body></html>
        """
        org_tariffs_html = (
            "<html><body><main><h2>Пакеты</h2>"
            "<p>Тариф Делегат Стоимостью 55 000 руб.</p></main></body></html>"
        )
        pdf_bytes = _make_sample_pdf_bytes(
            "Forum regulation and speaker tariffs: Speaker package 120 000 RUB, Early Bird discount."
        )

        async def _fake_fetch(url: str, **kwargs):
            if url == candidate.url:
                return agg_html, False
            if url == "https://bigforum-official.ru/":
                return org_home_html, False
            if url == "https://bigforum-official.ru/tariffs":
                return org_tariffs_html, False
            raise AssertionError(f"Неожиданная загрузка: {url}")

        with (
            patch("app.services.scraper.fetcher._fetch_raw_page_content", new=AsyncMock(side_effect=_fake_fetch)),
            patch("app.services.scraper.fetcher.fetch_pdf_bytes_safe", new=AsyncMock(return_value=pdf_bytes)),
            patch.object(scraper_pkg.settings, "LLM_API_KEY", ""),
        ):
            dossier = await collect_event_dossier(candidate, helpinver_src)

        self.assertLessEqual(len(dossier.dossier_text), scraper_pkg.MAX_DOSSIER_CHARS)
        self.assertIn("55 000 руб", dossier.dossier_text)
        self.assertIn("120 000 RUB", dossier.dossier_text)
        self.assertEqual(
            dossier.source_urls,
            [
                "https://helpinver.com/events/big-forum/",
                "https://bigforum-official.ru/",
                "https://bigforum-official.ru/tariffs",
                "https://bigforum-official.ru/files/reglament.pdf",
            ],
        )


class TestPhase2IngestionGeoPastAndReadyProtection(unittest.IsolatedAsyncioTestCase):
    """Тесты geo/past фильтров в ingestion.py ДО эмбеддингов и защиты ready-карточек."""

    def test_is_russia_or_online_event_variants(self) -> None:
        base_kw: dict[str, object] = {
            "canonical_title": "Тестовое событие",
            "event_format": "forum",
            "start_date": datetime.date(2026, 12, 10),
            "end_date": datetime.date(2026, 12, 10),
            "summary": _valid_summary(),
            "themes": ["архитектура"],
            "full_regulation_markdown": "Регламент " * 100,
        }
        self.assertTrue(
            is_russia_or_online_event(
                EventIngestionSchema(city="Москва", country="Россия", is_online=False, **base_kw)
            )
        )
        self.assertTrue(
            is_russia_or_online_event(
                EventIngestionSchema(city="г. СПб", country=None, is_online=False, **base_kw)
            )
        )
        self.assertFalse(
            is_russia_or_online_event(
                EventIngestionSchema(city="Гент", country="Бельгия", is_online=False, **base_kw)
            )
        )
        self.assertFalse(
            is_russia_or_online_event(
                EventIngestionSchema(city="Милан", country="Италия", is_online=False, **base_kw)
            )
        )
        self.assertFalse(
            is_russia_or_online_event(
                EventIngestionSchema(city="Копенгаген", country="Дания", is_online=False, **base_kw)
            )
        )
        self.assertFalse(
            is_russia_or_online_event(
                EventIngestionSchema(city="Алжир", country="Алжир", is_online=False, **base_kw)
            )
        )
        self.assertTrue(
            is_russia_or_online_event(
                EventIngestionSchema(city=None, country=None, is_online=True, **base_kw),
                allow_online=True,
            )
        )
        # Для archdaily (allow_online=False) глобальный онлайн отклоняется, но российский онлайн проходит
        self.assertFalse(
            is_russia_or_online_event(
                EventIngestionSchema(city=None, country=None, is_online=True, **base_kw),
                allow_online=False,
            )
        )
        self.assertTrue(
            is_russia_or_online_event(
                EventIngestionSchema(city=None, country="Россия", is_online=True, **base_kw),
                allow_online=False,
            )
        )

    async def test_past_and_foreign_rejected_before_get_embedding_and_db_write(self) -> None:
        past_schema = EventIngestionSchema(
            canonical_title="Прошедший форум в Москве",
            event_format="forum",
            city="Москва",
            country="Россия",
            is_online=False,
            start_date=datetime.date(2025, 10, 1),
            end_date=datetime.date(2025, 10, 2),
            summary=_valid_summary(),
            themes=["строительство"],
            full_regulation_markdown="Регламент " * 100,
        )
        foreign_schema = EventIngestionSchema(
            canonical_title="Milan Design Forum",
            event_format="forum",
            city="Милан",
            country="Италия",
            is_online=False,
            start_date=datetime.date(2026, 12, 15),
            end_date=datetime.date(2026, 12, 16),
            summary=_valid_summary(),
            themes=["дизайн"],
            full_regulation_markdown="Регламент " * 100,
        )

        session = AsyncMock()
        session.add = MagicMock()

        with (
            patch(
                "app.services.scraper.ingestion._extract_structured_event_via_llm",
                new=AsyncMock(return_value=past_schema),
            ),
            patch.object(scraper_pkg, "get_embedding", new=AsyncMock()) as mock_emb,
        ):
            with self.assertRaises(EventRejectedError) as ctx_past:
                await ingest_event_from_text(
                    session,
                    "Прошедший форум",
                    source_url="https://expomap.ru/expo/old/",
                    reject_past=True,
                    enforce_russia_online=True,
                )
            self.assertEqual(ctx_past.exception.outcome, "rejected_past")
            self.assertEqual(mock_emb.await_count, 0)
            self.assertEqual(session.add.call_count, 0)

        with (
            patch(
                "app.services.scraper.ingestion._extract_structured_event_via_llm",
                new=AsyncMock(return_value=foreign_schema),
            ),
            patch.object(scraper_pkg, "get_embedding", new=AsyncMock()) as mock_emb,
        ):
            with self.assertRaises(EventRejectedError) as ctx_geo:
                await ingest_event_from_text(
                    session,
                    "Миланский форум",
                    source_url="https://architime.ru/activity/2026/milan.htm",
                    reject_past=True,
                    enforce_russia_online=True,
                )
            self.assertEqual(ctx_geo.exception.outcome, "rejected_geo")
            self.assertEqual(mock_emb.await_count, 0)
            self.assertEqual(session.add.call_count, 0)

    async def test_monitoring_records_rejected_past_and_rejected_geo_in_seen_urls(self) -> None:
        architime_cfg = next(s for s in CUSTOMER_SOURCES_REGISTRY if s.source_key == "architime")
        src_row = _make_source_row(architime_cfg, 1)
        stored_seen: dict[str, ScraperSeenUrl] = {}

        async def _execute(stmt):
            sql = str(stmt)
            res = MagicMock()
            if "FROM scraper_sources" in sql:
                res.scalars.return_value.all.return_value = [src_row]
            elif "FROM scraper_seen_urls" in sql:
                if "WHERE scraper_seen_urls.url =" in sql:
                    params = stmt.compile().params
                    u_param = str(next(iter(params.values()), ""))
                    res.scalar_one_or_none.return_value = stored_seen.get(u_param)
                else:
                    res.scalars.return_value.all.return_value = list(stored_seen.values())
            else:
                res.scalars.return_value.all.return_value = []
                res.scalar_one_or_none.return_value = None
            return res

        session = AsyncMock()
        session.new = set()
        session.execute = AsyncMock(side_effect=_execute)
        session.add = MagicMock(
            side_effect=lambda obj: stored_seen.__setitem__(obj.url, obj)
            if isinstance(obj, ScraperSeenUrl)
            else None
        )

        class FakeArchitimeDiscovery:
            async def fetch_catalog_urls(self, source: CustomerSourceConfig) -> list[str]:
                return [
                    "https://www.architime.ru/activity/2025/past.htm",
                    "https://www.architime.ru/activity/2026/gent.htm",
                ]

        async def _fake_ingest(session_arg, text_arg, **kwargs):
            src_u = kwargs.get("source_url", "")
            if "past.htm" in src_u:
                raise EventRejectedError("rejected_past", "Дата окончания в прошлом")
            raise EventRejectedError("rejected_geo", "Бельгия вне РФ")

        with (
            patch.object(
                scraper_pkg,
                "collect_event_dossier",
                new=AsyncMock(
                    side_effect=lambda cand, src: CollectedEventDossier(
                        dossier_text="Досье",
                        source_urls=[cand.url],
                    )
                ),
            ),
            patch.object(scraper_pkg, "ingest_event_from_text", new=AsyncMock(side_effect=_fake_ingest)),
        ):
            summary = await run_customer_sources_monitoring(
                session,
                source_key="architime",
                catalog_scraper=FakeArchitimeDiscovery(),
                dry_run=False,
            )

        self.assertEqual(summary.rejected_past_count, 1)
        self.assertEqual(summary.rejected_geo_count, 1)
        self.assertEqual(summary.failed_count, 0)
        self.assertEqual(
            stored_seen["https://www.architime.ru/activity/2025/past.htm"].outcome,
            "rejected_past",
        )
        self.assertEqual(
            stored_seen["https://www.architime.ru/activity/2026/gent.htm"].outcome,
            "rejected_geo",
        )

    async def test_re_enrich_ready_event_never_downgrades_and_updates_last_scraped_at(self) -> None:
        old_ts = datetime.datetime(2026, 11, 1, 12, 0, tzinfo=datetime.UTC)
        existing_ready = Event(
            id=42,
            canonical_title="Строительный форум КРТ 2026",
            normalized_title="строительный форум крт 2026",
            event_format="forum",
            city="Москва",
            is_online=False,
            start_date=datetime.date(2026, 12, 20),
            end_date=datetime.date(2026, 12, 21),
            summary=_valid_summary(),
            full_regulation_markdown="Короткий старый текст.",  # < 600 символов, но ранее статус уже ready!
            themes=["КРТ"],
            source_urls=["https://expomap.ru/expo/krt-2026/"],
            data_status="ready",
            is_active=True,
            last_scraped_at=old_ts,
        )

        # Повторный прогон принес обновление без тарифов и с коротким регламентом
        incoming_schema = EventIngestionSchema(
            canonical_title="Строительный форум КРТ 2026",
            event_format="forum",
            city="Москва",
            country="Россия",
            is_online=False,
            start_date=datetime.date(2026, 12, 20),
            end_date=datetime.date(2026, 12, 21),
            summary=_valid_summary(),
            themes=["девелопмент"],
            full_regulation_markdown="Дополнение без подробностей.",
            tariffs=[],
            faq_cache=[],
        )

        session = AsyncMock()
        tariffs_res = MagicMock()
        tariffs_res.scalar.return_value = 0  # Симулируем ситуацию, когда quality gate вернул бы needs_enrichment
        session.execute = AsyncMock(return_value=tariffs_res)

        with (
            patch(
                "app.services.scraper.ingestion._extract_structured_event_via_llm",
                new=AsyncMock(return_value=incoming_schema),
            ),
            patch.object(scraper_pkg, "get_embedding", new=AsyncMock(return_value=[0.1] * 1024)),
            patch.object(scraper_pkg, "find_duplicate_event", new=AsyncMock(return_value=existing_ready)),
            patch.object(scraper_pkg, "invalidate_rag_cache", new=AsyncMock()),
            patch("app.services.scraper.ingestion._sync_event_chunks", new=AsyncMock()),
        ):
            updated = await ingest_event_from_text(
                session,
                "Обновленный текст",
                source_url="https://expomap.ru/expo/krt-2026/",
                extra_source_urls=["https://krt-official.ru/", "https://krt-official.ru/tariffs"],
            )

        self.assertEqual(updated.data_status, "ready")
        self.assertTrue(updated.is_active)
        self.assertGreater(updated.last_scraped_at, old_ts)
        self.assertEqual(
            updated.source_urls,
            [
                "https://expomap.ru/expo/krt-2026/",
                "https://krt-official.ru/",
                "https://krt-official.ru/tariffs",
            ],
        )


class TestPhase2AuditCleanupFixes(unittest.IsolatedAsyncioTestCase):
    """Тесты 4 исправлений строгого ревью Фазы 2: WAF в Jina, location.url, раздельный 2-Hop дайджестов, fail-closed триажа."""

    async def test_jina_waf_block_raises_captcha_blocked_error(self) -> None:
        from app.services.scraper.fetcher import _fetch_raw_page_content

        req = httpx.Request("GET", "https://r.jina.ai/https://archi.ru/events")
        waf_resp = httpx.Response(
            200,
            text="Checking your browser before accessing the website... HostAdmin.online waf@hostadmin.online",
            request=req,
        )
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = False
        mock_client.get = AsyncMock(return_value=waf_resp)

        with (
            patch("app.services.scraper.fetcher.socket.getaddrinfo", return_value=_PUBLIC_ADDRINFO),
            patch("app.services.scraper.fetcher.httpx.AsyncClient", return_value=mock_client),
            self.assertRaises(CaptchaBlockedError),
        ):
            await _fetch_raw_page_content("https://archi.ru/events", use_jina_reader=True)

    async def test_ld_json_location_url_does_not_override_strong_event_site(self) -> None:
        expomap_src = next(s for s in CUSTOMER_SOURCES_REGISTRY if s.source_key == "expomap_construction")
        candidate = DiscoveredCandidate(
            url="https://expomap.ru/expo/test-expo/",
            title="Test Expo",
            source_key="expomap_construction",
        )
        agg_html = """
        <html><body><main>
          <script type="application/ld+json">
            {
              "@type": "Event",
              "url": "https://expomap.ru/expo/test-expo/",
              "location": {"@type": "Place", "name": "Крокус Экспо", "url": "https://crocus-expo.ru/"}
            }
          </script>
          <p><a href="https://real-forum-site.ru/">Официальный сайт форума</a></p>
        </main></body></html>
        """
        org_html = "<html><body><main><p>Официальный сайт</p></main></body></html>"

        async def _fake_fetch(url: str, **kwargs):
            if url == candidate.url:
                return agg_html, False
            if url == "https://real-forum-site.ru/":
                return org_html, False
            raise AssertionError(f"Выбран неверный URL организатора: {url}")

        with patch("app.services.scraper.fetcher._fetch_raw_page_content", new=AsyncMock(side_effect=_fake_fetch)):
            dossier = await collect_event_dossier(candidate, expomap_src)

        self.assertEqual(dossier.official_site_url, "https://real-forum-site.ru/")
        self.assertEqual(dossier.source_urls, [candidate.url, "https://real-forum-site.ru/"])

    async def test_collect_event_dossiers_splits_digest_and_runs_2hop_per_section(self) -> None:
        dm_src = next(s for s in CUSTOMER_SOURCES_REGISTRY if s.source_key == "design_mate")
        candidate = DiscoveredCandidate(
            url="https://design-mate.ru/read/megapolis/digest-nov",
            title="Дайджест ноября",
            source_key="design_mate",
            is_digest=True,
        )
        digest_html = """
        <html><body><article>
          <h2>Форум дизайна в Екатеринбурге</h2>
          <p>Деловая программа для архитекторов. <a href="https://forumdesign.ru/ekb">Сайт</a></p>
          <h2>Конференция урбанистов в Казани</h2>
          <p>Профессиональный конгресс по развитию городов. <a href="https://kazan-urban.ru/">Сайт</a></p>
        </article></body></html>
        """

        async def _fake_fetch(url: str, **kwargs):
            if url == candidate.url:
                return digest_html, False
            if "forumdesign.ru" in url:
                return "<html><body><main><p>Тариф Делегат 35 000 руб.</p></main></body></html>", False
            if "kazan-urban.ru" in url:
                return "<html><body><main><p>Участие бесплатное для застройщиков.</p></main></body></html>", False
            raise AssertionError(f"Неожиданный URL: {url}")

        with (
            patch("app.services.scraper.fetcher._fetch_raw_page_content", new=AsyncMock(side_effect=_fake_fetch)),
            patch.object(scraper_pkg.settings, "LLM_API_KEY", ""),
        ):
            dossiers = await collect_event_dossiers(candidate, dm_src)

        self.assertEqual(len(dossiers), 2)
        self.assertEqual(dossiers[0].official_site_url, "https://forumdesign.ru/ekb")
        self.assertIn("35 000 руб", dossiers[0].dossier_text)
        self.assertNotIn("kazan-urban", dossiers[0].dossier_text)
        self.assertEqual(dossiers[1].official_site_url, "https://kazan-urban.ru/")
        self.assertIn("Участие бесплатное", dossiers[1].dossier_text)

    async def test_triage_fail_closed_on_api_error_when_key_present(self) -> None:
        votkuda_cfg = next(s for s in CUSTOMER_SOURCES_REGISTRY if s.source_key == "votkuda")
        cand = DiscoveredCandidate(
            url="https://votkuda.ru/event/unknown/",
            title="Непонятная выставка",
            source_key="votkuda",
        )
        mock_llm = MagicMock()
        mock_llm.chat.completions.create = AsyncMock(side_effect=TimeoutError("gateway timeout"))

        with (
            patch.object(scraper_pkg.settings, "LLM_API_KEY", "live-key"),
            patch.object(scraper_pkg, "structured_llm_client", new=mock_llm),
            self.assertRaises(TimeoutError),
        ):
            await triage_discovery_candidate(cand, votkuda_cfg)


class TestPhase2CloudDocumentsAndRedirects(unittest.IsolatedAsyncioTestCase):
    """Облачные документы (Яндекс.Диск / Google Drive), футер, анкеты, редиректы сокращателей, /download?id=."""

    @staticmethod
    def _agg_html(official_url: str, *, extra_links: str = "") -> str:
        return f"""
        <html><body><main>
          <script type="application/ld+json">
            {{"@type": "Event", "url": "https://expomap.ru/expo/cloud-forum/", "offers": {{"url": "{official_url}"}}}}
          </script>
          <h1>Cloud Forum 2026</h1>
          <p>Крупная B2B выставка в Москве.</p>
          {extra_links}
        </main></body></html>
        """

    @staticmethod
    def _candidate() -> DiscoveredCandidate:
        return DiscoveredCandidate(
            url="https://expomap.ru/expo/cloud-forum/",
            title="Cloud Forum 2026",
            source_key="expomap_construction",
        )

    @staticmethod
    def _expomap_source() -> CustomerSourceConfig:
        return next(s for s in CUSTOMER_SOURCES_REGISTRY if s.source_key == "expomap_construction")

    @staticmethod
    @contextmanager
    def _mock_http(handler, *, private_hosts: tuple[str, ...] = ()):
        real_async_client = httpx.AsyncClient
        transport = httpx.MockTransport(handler)

        def _client_factory(**kwargs):
            kwargs["transport"] = transport
            return real_async_client(**kwargs)

        def _addrinfo(host, *args, **kwargs):
            if host in private_hosts:
                return [(2, 1, 6, "", ("10.0.0.5", 0))]
            return _PUBLIC_ADDRINFO

        with (
            patch("app.services.scraper.fetcher.socket.getaddrinfo", side_effect=_addrinfo),
            patch("app.services.scraper.fetcher.httpx.AsyncClient", side_effect=_client_factory),
        ):
            yield

    # ---------- классификация ----------

    def test_is_document_candidate_url_classification(self) -> None:
        positives = [
            "https://x.ru/files/Price.PDF",
            "https://disk.yandex.ru/i/AbCdEf",
            "https://disk.yandex.ru/d/AbCdEf/sub-folder",
            "https://disk.yandex.com/d/AbCdEf",
            "https://disk.yandex.kz/i/AbCdEf",
            "https://yadi.sk/i/AbCdEf",
            "https://yadi.sk/d/AbCdEf",
            "https://drive.google.com/file/d/1AbCdEfGhIjK/view?usp=sharing",
            "https://drive.google.com/open?id=1AbCdEfGhIjK",
        ]
        negatives = [
            "https://disk.yandex.ru/",
            "https://disk.yandex.ru/client/disk",
            "https://docs.google.com/forms/d/e/1FAIpQLSabc/viewform",
            "https://docs.google.com/spreadsheets/d/1AbCdEfGhIjK/edit",
            "https://drive.google.com/drive/folders/1AbCdEfGhIjK",
            "https://drive.google.com/open?id=short",
            "https://x.ru/download?id=1",
            "https://x.ru/tariffs",
        ]
        for url in positives:
            with self.subTest(url=url):
                self.assertTrue(is_document_candidate_url(url))
        for url in negatives:
            with self.subTest(url=url):
                self.assertFalse(is_document_candidate_url(url))

    def test_social_and_form_domains_are_never_official_sites(self) -> None:
        from app.services.scraper.sources import _SOCIAL_DOMAINS

        for dom in ("max.ru", "tenchat.ru", "vc.ru", "habr.com", "telegra.ph"):
            self.assertIn(dom, _SOCIAL_DOMAINS)

        junk_md = (
            "[Анкета — официальный сайт](https://docs.google.com/forms/d/e/1FAIpQLSabc/viewform)\n"
            "[Регистрация](https://forms.yandex.ru/u/abc123/)\n"
            "[Опрос](https://forms.gle/xyz)\n"
            "[Канал агрегатора — сайт](https://max.ru/expomap)\n"
            "[Лид-форма](https://expolead.ru/event/1)\n"
            "[tenchat](https://tenchat.ru/a) [vc](https://vc.ru/b)\n"
            "[habr](https://habr.com/c) [telegraph](https://telegra.ph/d)"
        )
        official, pdfs = _discover_official_site_and_card_pdfs(junk_md, self._candidate(), self._expomap_source())
        self.assertIsNone(official)
        self.assertEqual(pdfs, [])

        official2, _ = _discover_official_site_and_card_pdfs(
            junk_md + "\n[Официальный сайт форума](https://real-org.ru/)",
            self._candidate(),
            self._expomap_source(),
        )
        self.assertEqual(official2, "https://real-org.ru/")

    # ---------- резолвер облака ----------

    async def test_yandex_file_link_accepts_only_small_pdf_and_uses_public_api(self) -> None:
        seen: list[httpx.Request] = []

        def _handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            key = request.url.params.get("public_key", "")
            if key.endswith("/PDFOK1"):
                return httpx.Response(
                    200,
                    json={
                        "type": "file",
                        "name": "Условия.pdf",
                        "mime_type": "application/pdf",
                        "size": 1000,
                        "file": "https://downloader.disk.yandex.ru/disk/tok/uslovia.pdf",
                    },
                )
            if key.endswith("/IMAGE1"):
                return httpx.Response(
                    200,
                    json={
                        "type": "file",
                        "name": "photo.png",
                        "mime_type": "image/png",
                        "size": 10,
                        "file": "https://downloader.disk.yandex.ru/disk/tok/photo.png",
                    },
                )
            if key.endswith("/BIGPDF1"):
                return httpx.Response(
                    200,
                    json={
                        "type": "file",
                        "name": "huge.pdf",
                        "mime_type": "application/pdf",
                        "size": 99 * 1024 * 1024,
                        "file": "https://downloader.disk.yandex.ru/disk/tok/huge.pdf",
                    },
                )
            return httpx.Response(404)

        with self._mock_http(_handler):
            ok = await resolve_cloud_pdf_urls("https://disk.yandex.ru/i/PDFOK1")
            short = await resolve_cloud_pdf_urls("https://yadi.sk/i/PDFOK1")
            image = await resolve_cloud_pdf_urls("https://disk.yandex.ru/i/IMAGE1")
            big = await resolve_cloud_pdf_urls("https://disk.yandex.ru/i/BIGPDF1", max_bytes=15 * 1024 * 1024)

        self.assertEqual(ok, ["https://downloader.disk.yandex.ru/disk/tok/uslovia.pdf"])
        self.assertEqual(short, ok)
        self.assertEqual(image, [])
        self.assertEqual(big, [])
        self.assertEqual({r.url.host for r in seen}, {"cloud-api.yandex.net"})
        self.assertEqual(seen[0].url.path, "/v1/disk/public/resources")
        self.assertEqual(seen[0].url.params["public_key"], "https://disk.yandex.ru/i/PDFOK1")
        self.assertEqual(seen[0].url.params["limit"], "20")

    async def test_yandex_dir_link_picks_top_two_relevant_pdfs_and_skips_images(self) -> None:
        download_requests: list[httpx.Request] = []

        def _handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/download"):
                download_requests.append(request)
                return httpx.Response(
                    200, json={"href": "https://downloader.disk.yandex.ru/disk/tok/buklet.pdf"}
                )
            return httpx.Response(
                200,
                json={
                    "type": "dir",
                    "name": "Docs",
                    "_embedded": {
                        "items": [
                            {
                                "type": "file",
                                "name": "photo.jpg",
                                "mime_type": "image/jpeg",
                                "size": 1,
                                "path": "/photo.jpg",
                                "file": "https://downloader.disk.yandex.ru/photo.jpg",
                            },
                            {
                                "type": "file",
                                "name": "random.pdf",
                                "mime_type": "application/pdf",
                                "size": 10,
                                "path": "/random.pdf",
                                "file": "https://downloader.disk.yandex.ru/random.pdf",
                            },
                            {
                                "type": "file",
                                "name": "БУКЛЕТ ДП.pdf",
                                "mime_type": "application/pdf",
                                "size": 10,
                                "path": "/БУКЛЕТ ДП.pdf",
                            },
                            {
                                "type": "file",
                                "name": "УСЛОВИЯ УЧАСТИЯ ВЫСТАВКА 2026.pdf",
                                "mime_type": "application/pdf",
                                "size": 10,
                                "path": "/УСЛОВИЯ УЧАСТИЯ ВЫСТАВКА 2026.pdf",
                                "file": "https://downloader.disk.yandex.ru/uslovia.pdf",
                            },
                            {
                                "type": "file",
                                "name": "тариф огромный.pdf",
                                "mime_type": "application/pdf",
                                "size": 99 * 1024 * 1024,
                                "path": "/big.pdf",
                                "file": "https://downloader.disk.yandex.ru/big.pdf",
                            },
                            {"type": "dir", "name": "Вложенная папка", "path": "/sub"},
                        ]
                    },
                },
            )

        with self._mock_http(_handler):
            urls = await resolve_cloud_pdf_urls("https://disk.yandex.ru/d/FOLDER1")

        self.assertEqual(
            urls,
            [
                "https://downloader.disk.yandex.ru/disk/tok/buklet.pdf",
                "https://downloader.disk.yandex.ru/uslovia.pdf",
            ],
        )
        self.assertEqual(len(download_requests), 1)
        self.assertEqual(download_requests[0].url.params["path"], "/БУКЛЕТ ДП.pdf")
        self.assertEqual(download_requests[0].url.params["public_key"], "https://disk.yandex.ru/d/FOLDER1")

    async def test_yandex_api_soft_failures_return_empty_list_with_warning(self) -> None:
        for status in (403, 404, 429):
            with self.subTest(status=status):
                with (
                    self._mock_http(lambda _req, s=status: httpx.Response(s)),
                    self.assertLogs("app.services.scraper.fetcher", level="WARNING") as logs,
                ):
                    urls = await resolve_cloud_pdf_urls("https://disk.yandex.ru/i/GONE123")
                self.assertEqual(urls, [])
                self.assertTrue(any(str(status) in line for line in logs.output))

    async def test_yandex_resolver_blocks_private_file_links_and_redirects(self) -> None:
        requested_hosts: list[str] = []

        def _file_handler(private_file: str):
            def _handler(request: httpx.Request) -> httpx.Response:
                requested_hosts.append(request.url.host)
                return httpx.Response(
                    200,
                    json={
                        "type": "file",
                        "name": "x.pdf",
                        "mime_type": "application/pdf",
                        "size": 10,
                        "file": private_file,
                    },
                )

            return _handler

        with self._mock_http(_file_handler("http://127.0.0.1/secret.pdf")):
            self.assertEqual(await resolve_cloud_pdf_urls("https://disk.yandex.ru/i/EVILIP1"), [])

        with self._mock_http(_file_handler("https://evil.example/x.pdf"), private_hosts=("evil.example",)):
            self.assertEqual(await resolve_cloud_pdf_urls("https://disk.yandex.ru/i/EVILDNS"), [])
        self.assertEqual(set(requested_hosts), {"cloud-api.yandex.net"})

        def _redirect_handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(302, headers={"Location": "http://127.0.0.1/internal"})

        with self._mock_http(_redirect_handler), self.assertRaises(UnsafeUrlError):
            await resolve_cloud_pdf_urls("https://disk.yandex.ru/i/REDIR12")

    async def test_yandex_dir_skips_unsafe_item_but_keeps_safe_sibling(self) -> None:
        def _handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "type": "dir",
                    "_embedded": {
                        "items": [
                            {
                                "type": "file",
                                "name": "тарифы evil.pdf",
                                "mime_type": "application/pdf",
                                "size": 1,
                                "file": "http://169.254.169.254/latest/meta-data",
                            },
                            {
                                "type": "file",
                                "name": "программа.pdf",
                                "mime_type": "application/pdf",
                                "size": 1,
                                "file": "https://downloader.disk.yandex.ru/program.pdf",
                            },
                        ]
                    },
                },
            )

        with self._mock_http(_handler):
            urls = await resolve_cloud_pdf_urls("https://disk.yandex.ru/d/MIXED12")
        self.assertEqual(urls, ["https://downloader.disk.yandex.ru/program.pdf"])

    async def test_google_drive_links_resolve_to_export_download_and_plain_urls_pass_through(self) -> None:
        expected = "https://drive.google.com/uc?export=download&id=1AbCdEfGhIjKlM"
        self.assertEqual(
            await resolve_cloud_pdf_urls("https://drive.google.com/file/d/1AbCdEfGhIjKlM/view?usp=sharing"),
            [expected],
        )
        self.assertEqual(
            await resolve_cloud_pdf_urls("https://drive.google.com/open?id=1AbCdEfGhIjKlM"), [expected]
        )
        self.assertEqual(
            await resolve_cloud_pdf_urls("https://example.ru/files/a.pdf"), ["https://example.ru/files/a.pdf"]
        )

    # ---------- краулер: облако, лимит по факту успеха ----------

    async def test_crawler_cloud_links_keep_original_url_and_dead_link_does_not_burn_quota(self) -> None:
        candidate = self._candidate()
        org_home = (
            "<html><body><header><nav>"
            '<a href="https://disk.yandex.ru/i/DEAD">Прайс и тарифы</a>'
            '<a href="https://disk.yandex.ru/i/AAAA">Условия участия</a>'
            '<a href="https://disk.yandex.ru/d/BBBB">Презентация</a>'
            '<a href="https://disk.yandex.ru/i/CCCC">Буклет</a>'
            "</nav></header><main><p>Главная</p></main></body></html>"
        )
        cdn = {
            "https://disk.yandex.ru/i/DEAD": [],
            "https://disk.yandex.ru/i/AAAA": ["https://downloader.disk.yandex.ru/tok/a.pdf"],
            "https://disk.yandex.ru/d/BBBB": [
                "https://downloader.disk.yandex.ru/tok/b1.pdf",
                "https://downloader.disk.yandex.ru/tok/b2.pdf",
            ],
            "https://disk.yandex.ru/i/CCCC": ["https://downloader.disk.yandex.ru/tok/c.pdf"],
        }
        pdf_payloads = {
            "https://downloader.disk.yandex.ru/tok/a.pdf": _make_long_pdf_bytes("UNIQUE_ALPHA participation conditions"),
            "https://downloader.disk.yandex.ru/tok/b1.pdf": _make_long_pdf_bytes("UNIQUE_BETA presentation one"),
            "https://downloader.disk.yandex.ru/tok/b2.pdf": _make_long_pdf_bytes("UNIQUE_GAMMA presentation two"),
            "https://downloader.disk.yandex.ru/tok/c.pdf": _make_long_pdf_bytes("UNIQUE_DELTA booklet"),
        }
        resolve_calls: list[str] = []
        download_calls: list[str] = []

        async def _fake_fetch(url: str, **kwargs):
            if url == candidate.url:
                return self._agg_html("https://real-org.ru/"), False
            if url == "https://real-org.ru/":
                return org_home, False
            raise AssertionError(f"Неожиданный URL: {url}")

        async def _fake_resolve(url: str, **kwargs):
            resolve_calls.append(url)
            return cdn[url]

        async def _fake_pdf(url: str, **kwargs):
            download_calls.append(url)
            return pdf_payloads[url]

        with (
            patch("app.services.scraper.fetcher._fetch_raw_page_content", new=AsyncMock(side_effect=_fake_fetch)),
            patch("app.services.scraper.fetcher.resolve_cloud_pdf_urls", new=AsyncMock(side_effect=_fake_resolve)),
            patch("app.services.scraper.fetcher.fetch_pdf_bytes_safe", new=AsyncMock(side_effect=_fake_pdf)),
            patch.object(scraper_pkg.settings, "LLM_API_KEY", ""),
        ):
            dossier = await collect_event_dossier(candidate, self._expomap_source(), vision_ocr=None)

        self.assertEqual(
            resolve_calls,
            ["https://disk.yandex.ru/i/DEAD", "https://disk.yandex.ru/i/AAAA", "https://disk.yandex.ru/d/BBBB"],
        )
        self.assertEqual(
            download_calls,
            [
                "https://downloader.disk.yandex.ru/tok/a.pdf",
                "https://downloader.disk.yandex.ru/tok/b1.pdf",
                "https://downloader.disk.yandex.ru/tok/b2.pdf",
            ],
        )
        self.assertEqual(
            dossier.source_urls,
            [
                candidate.url,
                "https://real-org.ru/",
                "https://disk.yandex.ru/i/AAAA",
                "https://disk.yandex.ru/d/BBBB",
            ],
        )
        self.assertNotIn("downloader.disk.yandex.ru", "\n".join(dossier.source_urls))
        self.assertNotIn("downloader.disk.yandex.ru", dossier.dossier_text)
        for marker in ("UNIQUE_ALPHA", "UNIQUE_BETA", "UNIQUE_GAMMA"):
            self.assertIn(marker, dossier.dossier_text)
        self.assertNotIn("UNIQUE_DELTA", dossier.dossier_text)
        self.assertIn("pdf_download_failed", dossier.warnings)

    async def test_crawler_blocks_ssrf_file_link_from_yandex_api_end_to_end(self) -> None:
        candidate = self._candidate()
        org_home = (
            "<html><body><nav>"
            '<a href="https://disk.yandex.ru/i/EVIL1">Условия участия</a>'
            "</nav></body></html>"
        )

        async def _fake_fetch(url: str, **kwargs):
            if url == candidate.url:
                return self._agg_html("https://real-org.ru/"), False
            return org_home, False

        def _api_handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "type": "file",
                    "name": "Условия.pdf",
                    "mime_type": "application/pdf",
                    "size": 10,
                    "file": "http://127.0.0.1:8080/internal.pdf",
                },
            )

        pdf_mock = AsyncMock(return_value=b"%PDF-never")
        with (
            self._mock_http(_api_handler),
            patch("app.services.scraper.fetcher._fetch_raw_page_content", new=AsyncMock(side_effect=_fake_fetch)),
            patch("app.services.scraper.fetcher.fetch_pdf_bytes_safe", new=pdf_mock),
            patch.object(scraper_pkg.settings, "LLM_API_KEY", ""),
        ):
            dossier = await collect_event_dossier(candidate, self._expomap_source(), vision_ocr=None)

        self.assertEqual(pdf_mock.await_count, 0)
        self.assertNotIn("https://disk.yandex.ru/i/EVIL1", dossier.source_urls)
        self.assertIn("pdf_download_failed", dossier.warnings)

    async def test_crawler_resolves_google_drive_and_ignores_google_forms(self) -> None:
        candidate = self._candidate()
        drive_url = "https://drive.google.com/file/d/1AbCdEfGhIjKlM/view?usp=sharing"
        org_home = (
            "<html><body><nav>"
            f'<a href="{drive_url}">Презентация</a>'
            '<a href="https://docs.google.com/forms/d/e/1FAIpQLSabc/viewform">Анкета участника</a>'
            "</nav></body></html>"
        )
        downloaded: list[str] = []
        pdf_bytes = _make_long_pdf_bytes("UNIQUE_DRIVE presentation of the forum")

        async def _fake_fetch(url: str, **kwargs):
            if url == candidate.url:
                return self._agg_html("https://real-org.ru/"), False
            if url == "https://real-org.ru/":
                return org_home, False
            raise AssertionError(f"Неожиданный URL: {url}")

        async def _fake_pdf(url: str, **kwargs):
            downloaded.append(url)
            return pdf_bytes

        with (
            patch("app.services.scraper.fetcher._fetch_raw_page_content", new=AsyncMock(side_effect=_fake_fetch)),
            patch("app.services.scraper.fetcher.fetch_pdf_bytes_safe", new=AsyncMock(side_effect=_fake_pdf)),
            patch.object(scraper_pkg.settings, "LLM_API_KEY", ""),
        ):
            dossier = await collect_event_dossier(candidate, self._expomap_source(), vision_ocr=None)

        self.assertEqual(downloaded, ["https://drive.google.com/uc?export=download&id=1AbCdEfGhIjKlM"])
        self.assertIn(drive_url, dossier.source_urls)
        self.assertIn("UNIQUE_DRIVE", dossier.dossier_text)
        self.assertEqual(dossier.official_site_url, "https://real-org.ru/")
        self.assertFalse(any("forms" in u for u in dossier.source_urls))

    async def test_source_cookies_are_sent_only_to_card_host_documents(self) -> None:
        src = next(s for s in CUSTOMER_SOURCES_REGISTRY if s.source_key == "helpinver")
        self.assertTrue(src.required_cookies)
        candidate = DiscoveredCandidate(
            url="https://helpinver.com/events/cloud-forum/", title="Cloud Forum", source_key="helpinver"
        )
        agg_html = self._agg_html(
            "https://real-org.ru/",
            extra_links=(
                '<a href="https://helpinver.com/files/regulation.pdf">Регламент</a>'
                '<a href="https://disk.yandex.ru/i/AAAA">Условия</a>'
            ),
        )
        calls: list[tuple[str, object]] = []

        async def _fake_fetch(url: str, **kwargs):
            if url == candidate.url:
                return agg_html, False
            return "<html><body><main><p>Главная организатора</p></main></body></html>", False

        async def _fake_resolve(url: str, **kwargs):
            return ["https://downloader.disk.yandex.ru/tok/a.pdf"] if "yandex" in url else [url]

        async def _fake_pdf(url: str, **kwargs):
            calls.append((url, kwargs.get("cookies")))
            return _make_long_pdf_bytes(f"text for {url}")

        with (
            patch("app.services.scraper.fetcher._fetch_raw_page_content", new=AsyncMock(side_effect=_fake_fetch)),
            patch("app.services.scraper.fetcher.resolve_cloud_pdf_urls", new=AsyncMock(side_effect=_fake_resolve)),
            patch("app.services.scraper.fetcher.fetch_pdf_bytes_safe", new=AsyncMock(side_effect=_fake_pdf)),
            patch.object(scraper_pkg.settings, "LLM_API_KEY", ""),
        ):
            await collect_event_dossier(candidate, src, vision_ocr=None)

        by_url = dict(calls)
        self.assertEqual(by_url["https://helpinver.com/files/regulation.pdf"], dict(src.required_cookies))
        self.assertIsNone(by_url["https://downloader.disk.yandex.ru/tok/a.pdf"])

    async def test_fetchers_scope_cookies_to_origin_host_not_redirect_targets(self) -> None:
        seen: list[tuple[str, str | None]] = []
        pdf_payload = _make_sample_pdf_bytes("cookie scope check")

        def _handler(request: httpx.Request) -> httpx.Response:
            seen.append((request.url.host, request.headers.get("cookie")))
            if request.url.host == "expomap.ru" and request.url.path == "/redirect.pdf":
                return httpx.Response(302, headers={"Location": "https://cdn.other.ru/f.pdf"})
            return httpx.Response(200, content=pdf_payload, headers={"Content-Type": "application/pdf"})

        with self._mock_http(_handler):
            await fetch_pdf_bytes_safe("https://expomap.ru/direct.pdf", cookies={"beget": "begetok"})
            await fetch_pdf_bytes_safe("https://expomap.ru/redirect.pdf", cookies={"beget": "begetok"})

        self.assertEqual(seen[0], ("expomap.ru", "beget=begetok"))
        self.assertEqual(seen[1], ("expomap.ru", "beget=begetok"))
        self.assertEqual(seen[2], ("cdn.other.ru", None))

    # ---------- футер ----------

    def test_footer_keeps_only_document_and_regulation_links_but_footer_text_is_dropped(self) -> None:
        org_url = "https://real-org.ru/"
        html = """
        <html><body>
          <header><nav><a href="/tariffs">Тарифы</a></nav></header>
          <main><p>Основной контент</p></main>
          <footer>
            <p>© 2026 ООО Ромашка. Все права защищены. FOOTER_JUNK_TEXT</p>
            <a href="/files/public-offer.pdf">Публичная оферта</a>
            <a href="https://disk.yandex.ru/d/OFFER1">Публичная оферта (Яндекс.Диск)</a>
            <a href="/terms-of-participation">Условия участия</a>
            <a href="/privacy">Политика конфиденциальности</a>
            <a href="/files/privacy-policy.pdf">Политика обработки персональных данных</a>
            <a href="https://dev-studio.ru/">Разработка сайта — Студия</a>
            <a href="/contacts">Контакты</a>
            <a href="https://max.ru/org">Мы в MAX</a>
          </footer>
        </body></html>
        """
        urls = {c.url for c in _extract_organizer_candidate_links(html, is_markdown=False, organizer_url=org_url)}
        self.assertEqual(
            urls,
            {
                "https://real-org.ru/tariffs",
                "https://real-org.ru/files/public-offer.pdf",
                "https://disk.yandex.ru/d/OFFER1",
                "https://real-org.ru/terms-of-participation",
            },
        )
        md = _convert_organizer_html_to_markdown(html, base_url=org_url)
        self.assertNotIn("FOOTER_JUNK_TEXT", md)
        self.assertNotIn("Политика конфиденциальности", md)

    # ---------- редиректы сокращателей ----------

    async def test_shortener_redirect_updates_effective_organizer_url_and_finds_subpages(self) -> None:
        candidate = self._candidate()
        org_home = (
            '<html><body><header><nav><a href="/tariffs">Тарифы участия</a></nav></header>'
            "<main><p>Главная реального сайта</p></main></body></html>"
        )
        fetched: list[str] = []

        async def _fake_fetch(url: str, *, resolved_url_out: list[str] | None = None, **kwargs):
            fetched.append(url)
            if url == candidate.url:
                return self._agg_html("https://clck.ru/AbCdE"), False
            if url == "https://clck.ru/AbCdE":
                if resolved_url_out is not None:
                    resolved_url_out[:] = ["https://real-org.ru/"]
                return org_home, False
            if url == "https://real-org.ru/tariffs":
                return "<html><body><main><p>Тариф Делегат 77 000 руб.</p></main></body></html>", False
            raise AssertionError(f"Неожиданный URL: {url}")

        with (
            patch("app.services.scraper.fetcher._fetch_raw_page_content", new=AsyncMock(side_effect=_fake_fetch)),
            patch.object(scraper_pkg.settings, "LLM_API_KEY", ""),
        ):
            dossier = await collect_event_dossier(candidate, self._expomap_source(), vision_ocr=None)

        self.assertIn("https://real-org.ru/tariffs", fetched)
        self.assertEqual(dossier.official_site_url, "https://real-org.ru/")
        self.assertEqual(
            dossier.source_urls,
            [candidate.url, "https://clck.ru/AbCdE", "https://real-org.ru/", "https://real-org.ru/tariffs"],
        )
        self.assertIn("77 000 руб", dossier.dossier_text)

    async def test_shortener_redirect_to_social_or_form_does_not_search_subpages(self) -> None:
        candidate = self._candidate()
        for blocked_final in ("https://max.ru/expomap", "https://docs.google.com/forms/d/e/1FAIpQLSabc/viewform"):
            with self.subTest(final=blocked_final):

                async def _fake_fetch(url: str, *, resolved_url_out: list[str] | None = None, _final=blocked_final, **kwargs):
                    if url == candidate.url:
                        return self._agg_html("https://clck.ru/Zz9"), False
                    if url == "https://clck.ru/Zz9":
                        if resolved_url_out is not None:
                            resolved_url_out[:] = [_final]
                        return '<html><body><nav><a href="/tariffs">Тарифы</a></nav></body></html>', False
                    raise AssertionError(f"Подстраница не должна загружаться: {url}")

                with (
                    patch(
                        "app.services.scraper.fetcher._fetch_raw_page_content",
                        new=AsyncMock(side_effect=_fake_fetch),
                    ),
                    patch.object(scraper_pkg.settings, "LLM_API_KEY", ""),
                ):
                    dossier = await collect_event_dossier(candidate, self._expomap_source(), vision_ocr=None)

                self.assertIsNone(dossier.official_site_url)
                self.assertEqual(dossier.source_urls, [candidate.url])
                self.assertIn("official_site_redirected_to_blocked_domain", dossier.warnings)

    async def test_legacy_fetch_mock_without_new_kwargs_still_works(self) -> None:
        candidate = self._candidate()

        async def _legacy_fetch(url: str, *, encoding: str = "utf-8", use_jina_reader: bool = False, cookies=None):
            if url == candidate.url:
                return self._agg_html("https://legacy-org.ru/"), False
            if url == "https://legacy-org.ru/":
                return '<html><body><nav><a href="/tariffs">Тарифы</a></nav></body></html>', False
            if url == "https://legacy-org.ru/tariffs":
                return "<html><body><main><p>Тариф 11 000 руб.</p></main></body></html>", False
            raise AssertionError(f"Неожиданный URL: {url}")

        with (
            patch("app.services.scraper.fetcher._fetch_raw_page_content", new=AsyncMock(side_effect=_legacy_fetch)),
            patch.object(scraper_pkg.settings, "LLM_API_KEY", ""),
        ):
            dossier = await collect_event_dossier(candidate, self._expomap_source(), vision_ocr=None)

        self.assertEqual(dossier.official_site_url, "https://legacy-org.ru/")
        self.assertIn("11 000 руб", dossier.dossier_text)

    async def test_fetch_raw_page_content_publishes_resolved_url_after_redirect_and_jina(self) -> None:
        long_html = "<html><body><main><p>" + ("Реальный сайт организатора. " * 40) + "</p></main></body></html>"

        def _handler(request: httpx.Request) -> httpx.Response:
            if request.url.host == "clck.ru":
                return httpx.Response(302, headers={"Location": "https://real-org.ru/"})
            if request.url.host == "r.jina.ai":
                return httpx.Response(200, text="# Markdown страницы\n" + ("Текст. " * 50))
            return httpx.Response(200, content=long_html.encode("utf-8"), headers={"Content-Type": "text/html"})

        redirected: list[str] = []
        jina_resolved: list[str] = []
        with self._mock_http(_handler):
            content, is_md = await fetcher_mod._fetch_raw_page_content(
                "https://clck.ru/AbCdE", resolved_url_out=redirected
            )
            _, jina_is_md = await fetcher_mod._fetch_raw_page_content(
                "https://spa-site.ru/", use_jina_reader=True, resolved_url_out=jina_resolved
            )
        self.assertFalse(is_md)
        self.assertIn("Реальный сайт", content)
        self.assertEqual(redirected, ["https://real-org.ru/"])
        self.assertTrue(jina_is_md)
        self.assertEqual(jina_resolved, ["https://spa-site.ru/"])

    # ---------- скрипты скачивания без .pdf ----------

    async def test_fetch_raw_page_content_hands_over_pdf_bytes_of_download_script(self) -> None:
        pdf_payload = _make_sample_pdf_bytes("download script payload")
        html_page = "<html><body><main><p>" + ("Обычная HTML страница. " * 40) + "</p></main></body></html>"

        def _handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/download":
                return httpx.Response(200, content=pdf_payload, headers={"Content-Type": "application/pdf"})
            if request.url.path == "/get_file.php":
                return httpx.Response(
                    200, content=pdf_payload, headers={"Content-Type": "application/octet-stream"}
                )
            return httpx.Response(200, content=html_page.encode("utf-8"), headers={"Content-Type": "text/html"})

        with self._mock_http(_handler):
            sink: list[bytes] = []
            result = await fetcher_mod._fetch_raw_page_content(
                "https://real-org.ru/download?id=99", pdf_bytes_out=sink
            )
            self.assertEqual(result, ("", False))
            self.assertEqual(sink, [pdf_payload])

            sink_magic: list[bytes] = []
            result_magic = await fetcher_mod._fetch_raw_page_content(
                "https://real-org.ru/get_file.php?x=1", pdf_bytes_out=sink_magic
            )
            self.assertEqual(result_magic, ("", False))
            self.assertEqual(sink_magic, [pdf_payload])

            sink_big: list[bytes] = []
            with self.assertRaises(ValueError):
                await fetcher_mod._fetch_raw_page_content(
                    "https://real-org.ru/download?id=99", pdf_bytes_out=sink_big, max_pdf_bytes=64
                )
            self.assertEqual(sink_big, [])

            sink_html: list[bytes] = []
            html_content, html_is_md = await fetcher_mod._fetch_raw_page_content(
                "https://real-org.ru/page", pdf_bytes_out=sink_html
            )
            self.assertFalse(html_is_md)
            self.assertIn("Обычная HTML страница", html_content)
            self.assertEqual(sink_html, [])

    async def _run_download_script_crawl(self, pdf_payload: bytes, **crawl_kwargs):
        candidate = self._candidate()
        org_home = (
            "<html><body><header><nav>"
            '<a href="/download?id=99">Скачать презентацию</a>'
            "</nav></header><main><p>Главная</p></main></body></html>"
        )

        async def _fake_fetch(
            url: str,
            *,
            pdf_bytes_out: list[bytes] | None = None,
            resolved_url_out: list[str] | None = None,
            **kwargs,
        ):
            if url == candidate.url:
                return self._agg_html("https://real-org.ru/"), False
            if url == "https://real-org.ru/":
                return org_home, False
            if url == "https://real-org.ru/download?id=99":
                assert pdf_bytes_out is not None
                pdf_bytes_out.append(pdf_payload)
                return "", False
            raise AssertionError(f"Неожиданный URL: {url}")

        pdf_mock = AsyncMock(return_value=b"%PDF-never")
        with (
            patch("app.services.scraper.fetcher._fetch_raw_page_content", new=AsyncMock(side_effect=_fake_fetch)),
            patch("app.services.scraper.fetcher.fetch_pdf_bytes_safe", new=pdf_mock),
            patch.object(scraper_pkg.settings, "LLM_API_KEY", ""),
        ):
            dossier = await collect_event_dossier(candidate, self._expomap_source(), **crawl_kwargs)
        self.assertEqual(pdf_mock.await_count, 0)
        return dossier

    async def test_crawler_processes_download_script_pdf_via_pymupdf(self) -> None:
        dossier = await self._run_download_script_crawl(
            _make_long_pdf_bytes("UNIQUE_SCRIPT presentation tariffs 90 000 RUB"), vision_ocr=None
        )
        self.assertIn("UNIQUE_SCRIPT", dossier.dossier_text)
        self.assertIn("https://real-org.ru/download?id=99", dossier.source_urls)
        self.assertNotIn("=== ПОДСТРАНИЦА ОРГАНИЗАТОРА (https://real-org.ru/download?id=99)", dossier.dossier_text)
        self.assertNotIn("%PDF", dossier.dossier_text)
        self.assertNotIn("\ufffd", dossier.dossier_text)

    async def test_crawler_processes_scanned_download_script_pdf_via_vision_ocr_budget(self) -> None:
        doc = fitz.open()
        page = doc.new_page(width=595, height=842)
        page.draw_rect(fitz.Rect(40, 40, 300, 200), color=(0.1, 0.1, 0.1))
        scanned = doc.tobytes()
        doc.close()

        mock_ocr = MagicMock()
        mock_ocr.extract_text_from_images = AsyncMock(return_value="Тариф Делегат — 66 000 руб.")
        budget = OcrBudgetTracker(remaining_pages=5)
        dossier = await self._run_download_script_crawl(scanned, vision_ocr=mock_ocr, ocr_budget=budget)

        self.assertEqual(mock_ocr.extract_text_from_images.await_count, 1)
        self.assertEqual(budget.used_pages, 1)
        self.assertIn("66 000 руб.", dossier.dossier_text)
        self.assertIn("https://real-org.ru/download?id=99", dossier.source_urls)

    def test_download_script_links_get_moderate_score_bonus(self) -> None:
        plain = _score_organizer_link("https://real-org.ru/page?id=1", "Ссылка", is_pdf=False, in_nav_or_header=False)
        script = _score_organizer_link(
            "https://real-org.ru/download?id=1", "Скачать", is_pdf=False, in_nav_or_header=False
        )
        self.assertEqual(plain, 0)
        self.assertEqual(script, 3)
        cloud = _score_organizer_link(
            "https://disk.yandex.ru/i/AAAA", "Условия", is_pdf=True, in_nav_or_header=False
        )
        direct = _score_organizer_link(
            "https://real-org.ru/files/x.pdf", "Условия", is_pdf=True, in_nav_or_header=False
        )
        self.assertGreaterEqual(cloud, direct - 1)
        self.assertGreater(cloud, 10)


if __name__ == "__main__":
    unittest.main()
