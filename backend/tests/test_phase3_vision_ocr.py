import base64
import datetime
import os
import struct
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pymupdf as fitz
from fastapi.testclient import TestClient
from openai import APIError
from pydantic import ValidationError

# Add backend directory to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import Settings
from app.core.database import get_async_session
from app.core.security import get_current_manager
from app.main import app
from app.models.models import Event, ScraperSeenUrl, ScraperSource, User
from app.schemas.event_ingestion import EventIngestionSchema
from app.services import scraper as scraper_pkg
from app.services.scraper import (
    CUSTOMER_SOURCES_REGISTRY,
    CustomerSourceConfig,
    DiscoveredCandidate,
    OcrBudgetTracker,
    OpenAICompatibleVisionOCRProvider,
    build_vision_ocr_provider,
    collect_event_dossier,
    extract_relevant_pdf_text_sync,
    ingest_smart_event,
    run_customer_sources_monitoring,
    should_run_vision_ocr,
)


def _make_blank_raster_pdf(
    *,
    num_pages: int = 1,
    width: float = 595.0,
    height: float = 842.0,
) -> bytes:
    """Создает PDF-документ без текстового слоя (только векторные/графические элементы)."""
    doc = fitz.open()
    for idx in range(num_pages):
        page = doc.new_page(width=width, height=height)
        page.draw_rect(
            fitz.Rect(20, 20, max(30, width - 20), max(30, height - 20)),
            color=(0.2, 0.3, 0.5),
            width=2,
        )
        page.draw_circle(fitz.Point(100 + idx * 10, 100), 25, color=(0.8, 0.1, 0.1))
    data = doc.tobytes()
    doc.close()
    return data


def _make_mixed_pdf(page_texts: list[str]) -> bytes:
    doc = fitz.open()
    for txt in page_texts:
        page = doc.new_page(width=595, height=842)
        if txt:
            page.insert_textbox(fitz.Rect(40, 40, 555, 800), txt, fontsize=11)
        else:
            page.draw_rect(fitz.Rect(40, 40, 300, 200), color=(0.1, 0.1, 0.1))
    data = doc.tobytes()
    doc.close()
    return data


def _png_dimensions(png_bytes: bytes) -> tuple[int, int]:
    assert png_bytes.startswith(b"\x89PNG\r\n\x1a\n")
    width, height = struct.unpack(">II", png_bytes[16:24])
    return int(width), int(height)


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


def _valid_summary() -> str:
    return (
        "Крупнейший профессиональный строительный форум для девелоперов, архитекторов и "
        "инженеров в Москве. В программе сессии по комплексному развитию территорий, BIM-проектированию, "
        "тарифы делегатов и спикеров, деловые переговоры, выставка материалов и разбор практики "
        "регулирования жилого и коммерческого девелопмента в мегаполисах России."
    )


class TestPhase3ConfigAndProviderBuilder(unittest.TestCase):
    """Тесты конфигурации бюджетного OCR и фабрики build_vision_ocr_provider."""

    def test_settings_vision_ocr_normalization_and_bounds(self) -> None:
        base_kwargs = {
            "_env_file": None,
            "DATABASE_URL": "postgresql+asyncpg://user:pass@localhost:5432/db",
            "SECRET_KEY": "a" * 32,
        }
        with patch.dict(os.environ, {}, clear=True):
            s_default = Settings(**base_kwargs)
            self.assertIsNone(s_default.VISION_OCR_MODEL)
            self.assertEqual(s_default.VISION_OCR_MAX_PAGES_AUTO, 3)
            self.assertEqual(s_default.VISION_OCR_MAX_PAGES_MANUAL, 6)
            self.assertEqual(s_default.VISION_OCR_MAX_PAGES_PER_RUN, 20)
            self.assertEqual(s_default.SCRAPER_MAX_PDF_BYTES, 15 * 1024 * 1024)

            s_blank = Settings(**base_kwargs, VISION_OCR_MODEL="   ")
            self.assertIsNone(s_blank.VISION_OCR_MODEL)

            s_empty = Settings(**base_kwargs, VISION_OCR_MODEL="")
            self.assertIsNone(s_empty.VISION_OCR_MODEL)

            s_trimmed = Settings(**base_kwargs, VISION_OCR_MODEL="  google/gemini-2.5-flash-lite  ")
            self.assertEqual(s_trimmed.VISION_OCR_MODEL, "google/gemini-2.5-flash-lite")

            with self.assertRaises(ValidationError):
                Settings(**base_kwargs, VISION_OCR_MAX_PAGES_AUTO=0)
            with self.assertRaises(ValidationError):
                Settings(**base_kwargs, VISION_OCR_MAX_PAGES_MANUAL=21)
            with self.assertRaises(ValidationError):
                Settings(**base_kwargs, SCRAPER_MAX_PDF_BYTES=512)

    def test_build_vision_ocr_provider_never_falls_back_to_llm_model(self) -> None:
        with (
            patch.object(scraper_pkg.settings, "LLM_API_KEY", "live-key"),
            patch.object(scraper_pkg.settings, "LLM_MODEL", "deepseek/deepseek-chat"),
            patch.object(scraper_pkg.settings, "VISION_OCR_MODEL", None),
        ):
            self.assertIsNone(build_vision_ocr_provider())

        with (
            patch.object(scraper_pkg.settings, "LLM_API_KEY", "live-key"),
            patch.object(scraper_pkg.settings, "LLM_MODEL", "deepseek/deepseek-chat"),
            patch.object(scraper_pkg.settings, "VISION_OCR_MODEL", ""),
        ):
            self.assertIsNone(build_vision_ocr_provider())

        with (
            patch.object(scraper_pkg.settings, "LLM_API_KEY", ""),
            patch.object(scraper_pkg.settings, "VISION_OCR_MODEL", "google/gemini-2.5-flash-lite"),
        ):
            self.assertIsNone(build_vision_ocr_provider())

        with (
            patch.object(scraper_pkg.settings, "LLM_API_KEY", "live-key"),
            patch.object(scraper_pkg.settings, "LLM_MODEL", "deepseek/deepseek-chat"),
            patch.object(scraper_pkg.settings, "VISION_OCR_MODEL", "google/gemini-2.5-flash-lite"),
        ):
            provider = build_vision_ocr_provider()
            self.assertIsInstance(provider, OpenAICompatibleVisionOCRProvider)
            assert isinstance(provider, OpenAICompatibleVisionOCRProvider)
            self.assertEqual(provider.model, "google/gemini-2.5-flash-lite")


class TestPhase3PyMuPDFResizeAndBudgetGate(unittest.TestCase):
    """Тесты адаптивного ресайза в PyMuPDF, OcrBudgetTracker и should_run_vision_ocr."""

    def test_adaptive_resize_and_max_ocr_pages(self) -> None:
        large_pdf = _make_blank_raster_pdf(num_pages=5, width=3000.0, height=1800.0)
        text_large, images_large = extract_relevant_pdf_text_sync(
            large_pdf,
            max_ocr_pages=3,
            max_image_side_px=1280,
        )
        self.assertEqual(text_large, "")
        self.assertEqual(len(images_large), 3)
        for img in images_large:
            w, h = _png_dimensions(img)
            self.assertLessEqual(max(w, h), 1280)
            self.assertEqual(w, 1280)

        normal_pdf = _make_blank_raster_pdf(num_pages=2, width=595.0, height=842.0)
        _, images_normal = extract_relevant_pdf_text_sync(
            normal_pdf,
            max_ocr_pages=6,
            max_image_side_px=1280,
        )
        self.assertEqual(len(images_normal), 2)
        w_n, h_n = _png_dimensions(images_normal[0])
        self.assertLessEqual(max(w_n, h_n), 1280)

    def test_should_run_vision_ocr_budget_gate(self) -> None:
        fake_imgs = [b"\x89PNG\r\n\x1a\nfake"]

        # Нет картинок -> False
        self.assertFalse(should_run_vision_ocr("Любой текст", "Текст PDF", []))

        # Почти пустой pdf_text (< 200 симв.) -> True даже при богатом HTML
        rich_html = "Тариф Делегат стоит 50 000 руб. " * 30
        self.assertTrue(should_run_vision_ocr(rich_html, "Короткий текст", fake_imgs))

        # Текстовый PDF с обложкой-картинкой + явные цены и тарифы >= 600 симв. -> False
        pdf_txt_long = (
            "Официальный регламент архитектурного форума 2026 года. "
            "Тариф Делегат — 45 000 руб. с НДС, Early Bird скидка до 15 ноября. "
            + "Подробная программа деловых сессий и круглых столов. " * 15
        )
        self.assertGreaterEqual(len(pdf_txt_long), 600)
        self.assertFalse(should_run_vision_ocr("", pdf_txt_long, fake_imgs))

        # HTML содержит цену рядом с тарифом, а в PDF >= 200 симв. описания -> False
        pdf_desc = "Подробное описание площадки, адреса и расписания пленарных сессий. " * 5
        self.assertGreaterEqual(len(pdf_desc), 200)
        self.assertFalse(should_run_vision_ocr(rich_html, pdf_desc, fake_imgs))

        # Длинный текст, но без цен/тарифов -> True
        no_price_text = "Деловая программа форума урбанистики и архитектуры в Москве. " * 20
        self.assertTrue(should_run_vision_ocr("", no_price_text, fake_imgs))

        # Числа с руб без тарифных слов рядом (инвестиции далеко от "тариф") -> True
        unrelated_money = (
            "Общий объем инвестиций в инфраструктуру составил 500 000 000 руб. "
            + "Описание сессий, залов и архитектуры без прайса. " * 15
        )
        self.assertTrue(should_run_vision_ocr("", unrelated_money, fake_imgs))

        # Слишком короткий объединенный текст (< 600 симв.) даже с ценой -> True
        short_with_price = "Тариф Делегат: 30 000 ₽. " + ("Программа форума. " * 12)
        self.assertGreaterEqual(len(short_with_price), 200)
        self.assertLess(len(short_with_price), 600)
        self.assertTrue(should_run_vision_ocr("", short_with_price, fake_imgs))

    def test_ocr_budget_tracker_strict_limit(self) -> None:
        tracker = OcrBudgetTracker(remaining_pages=5)
        self.assertEqual(tracker.reserve(6, per_doc_limit=3), 3)
        self.assertEqual(tracker.remaining_pages, 2)
        self.assertEqual(tracker.used_pages, 3)

        self.assertEqual(tracker.reserve(4, per_doc_limit=3), 2)
        self.assertEqual(tracker.remaining_pages, 0)
        self.assertEqual(tracker.used_pages, 5)

        self.assertEqual(tracker.reserve(3, per_doc_limit=3), 0)
        self.assertEqual(tracker.remaining_pages, 0)
        self.assertEqual(tracker.used_pages, 5)


class TestPhase3OpenAIVisionProvider(unittest.IsolatedAsyncioTestCase):
    """Тесты OpenAICompatibleVisionOCRProvider: payload, MIME, usage и fallback."""

    async def test_payload_png_and_jpeg_and_success(self) -> None:
        png_bytes = b"\x89PNG\r\n\x1a\npngdata"
        jpeg_bytes = b"\xff\xd8\xff\xe0jpegdata"

        fake_resp = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content="| Тариф | Цена |\n| Делегат | 45 000 руб. |")
                )
            ],
            usage=SimpleNamespace(prompt_tokens=320, completion_tokens=45, total_tokens=365),
        )
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=fake_resp)

        provider = OpenAICompatibleVisionOCRProvider(model="google/gemini-2.5-flash-lite")
        with patch.object(scraper_pkg, "raw_openai_client", new=mock_client):
            result = await provider.extract_text_from_images([png_bytes, jpeg_bytes])

        self.assertIn("45 000 руб.", result)
        self.assertEqual(
            provider.last_usage,
            {"prompt_tokens": 320, "completion_tokens": 45, "total_tokens": 365},
        )
        mock_client.chat.completions.create.assert_awaited_once()
        call_kwargs = mock_client.chat.completions.create.call_args.kwargs
        self.assertEqual(call_kwargs["model"], "google/gemini-2.5-flash-lite")
        messages = call_kwargs["messages"]
        self.assertEqual(messages[0]["role"], "system")
        self.assertIn("OCR-экстрактор", messages[0]["content"])
        user_content = messages[1]["content"]
        self.assertEqual(user_content[0]["type"], "text")
        self.assertEqual(user_content[1]["type"], "image_url")
        self.assertEqual(
            user_content[1]["image_url"],
            {
                "url": f"data:image/png;base64,{base64.b64encode(png_bytes).decode('ascii')}",
                "detail": "auto",
            },
        )
        self.assertEqual(
            user_content[2]["image_url"],
            {
                "url": f"data:image/jpeg;base64,{base64.b64encode(jpeg_bytes).decode('ascii')}",
                "detail": "auto",
            },
        )

    async def test_graceful_fallback_on_api_error_and_timeout(self) -> None:
        png_bytes = b"\x89PNG\r\n\x1a\npngdata"
        req = httpx.Request("POST", "https://api.ru-openrouter.ru/v1/chat/completions")
        api_err = APIError("Gateway error", request=req, body=None)

        provider = OpenAICompatibleVisionOCRProvider(model="google/gemini-2.5-flash-lite")

        mock_err_client = MagicMock()
        mock_err_client.chat.completions.create = AsyncMock(side_effect=api_err)
        with patch.object(scraper_pkg, "raw_openai_client", new=mock_err_client):
            self.assertEqual(await provider.extract_text_from_images([png_bytes]), "")

        mock_timeout_client = MagicMock()
        mock_timeout_client.chat.completions.create = AsyncMock(side_effect=TimeoutError("timeout"))
        with patch.object(scraper_pkg, "raw_openai_client", new=mock_timeout_client):
            self.assertEqual(await provider.extract_text_from_images([png_bytes]), "")


class TestPhase3CrawlerMonitoringAndManualImport(unittest.IsolatedAsyncioTestCase):
    """Интеграционные тесты Phase 3 (на моках): 2-Hop краулер, monitoring.py, ingestion.py и /events/upload-pdf."""

    async def test_crawler_ocr_budget_exhausted_and_not_configured(self) -> None:
        expomap_src = next(s for s in CUSTOMER_SOURCES_REGISTRY if s.source_key == "expomap_construction")
        candidate = DiscoveredCandidate(
            url="https://expomap.ru/expo/scan-forum/",
            title="Scan Forum 2026",
            source_key="expomap_construction",
        )
        agg_html = """
        <html><body><main>
          <h1>Scan Forum 2026</h1>
          <p><a href="https://scan-forum.ru/">Официальный сайт</a></p>
        </main></body></html>
        """
        org_html = """
        <html><body><nav><a href="/files/tariffs_scan.pdf">Прайс PDF</a></nav></body></html>
        """
        scanned_pdf = _make_blank_raster_pdf(num_pages=4, width=1600, height=1200)

        async def _fake_fetch(url: str, **kwargs):
            if url == candidate.url:
                return agg_html, False
            if url == "https://scan-forum.ru/":
                return org_html, False
            raise AssertionError(f"Unexpected URL: {url}")

        # 1. Без настроенного OCR -> vision_ocr_not_configured
        with (
            patch("app.services.scraper.fetcher._fetch_raw_page_content", new=AsyncMock(side_effect=_fake_fetch)),
            patch("app.services.scraper.fetcher.fetch_pdf_bytes_safe", new=AsyncMock(return_value=scanned_pdf)),
            patch.object(scraper_pkg.settings, "LLM_API_KEY", ""),
        ):
            dossier_unconf = await collect_event_dossier(candidate, expomap_src, vision_ocr=None)

        self.assertIn("vision_ocr_not_configured", dossier_unconf.warnings)
        self.assertNotIn("РАСПОЗНАННЫЙ OCR ТЕКСТ PDF", dossier_unconf.dossier_text)

        # 2. С OCR и ограниченным бюджетом (1 страница осталась -> берет 1, второй документ -> budget_exhausted)
        budget = OcrBudgetTracker(remaining_pages=1)
        mock_ocr = MagicMock()
        mock_ocr.extract_text_from_images = AsyncMock(
            return_value="Тариф Делегат — 60 000 руб. с НДС."
        )

        with (
            patch("app.services.scraper.fetcher._fetch_raw_page_content", new=AsyncMock(side_effect=_fake_fetch)),
            patch("app.services.scraper.fetcher.fetch_pdf_bytes_safe", new=AsyncMock(return_value=scanned_pdf)),
            patch.object(scraper_pkg.settings, "LLM_API_KEY", ""),
        ):
            dossier_ok = await collect_event_dossier(
                candidate, expomap_src, vision_ocr=mock_ocr, ocr_budget=budget
            )
            dossier_exhausted = await collect_event_dossier(
                candidate, expomap_src, vision_ocr=mock_ocr, ocr_budget=budget
            )

        self.assertEqual(mock_ocr.extract_text_from_images.await_count, 1)
        sent_imgs = mock_ocr.extract_text_from_images.call_args.args[0]
        self.assertEqual(len(sent_imgs), 1)
        self.assertIn("=== РАСПОЗНАННЫЙ OCR ТЕКСТ PDF ===", dossier_ok.dossier_text)
        self.assertIn("60 000 руб.", dossier_ok.dossier_text)
        self.assertEqual(budget.used_pages, 1)
        self.assertEqual(budget.remaining_pages, 0)
        self.assertIn("vision_ocr_budget_exhausted", dossier_exhausted.warnings)

    async def test_monitoring_vision_ocr_pages_used_and_backward_compat_mocks(self) -> None:
        votkuda_cfg = next(s for s in CUSTOMER_SOURCES_REGISTRY if s.source_key == "votkuda")
        src_cfg = CustomerSourceConfig(**{**votkuda_cfg.__dict__, "b2b_filter_enabled": False})
        src_row = _make_source_row(src_cfg, 1)
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

        class FakeCatalogScraper:
            async def fetch_catalog_urls(self, source: CustomerSourceConfig) -> list[str]:
                return [
                    "https://votkuda.ru/event/scan-1/",
                    "https://votkuda.ru/event/scan-2/",
                ]

        scanned_pdf = _make_blank_raster_pdf(num_pages=4)
        agg_html = (
            "<html><body><main><h1>Форум</h1>"
            "<a href='https://org-scan.ru/'>Официальный сайт</a></main></body></html>"
        )
        org_html = "<html><body><nav><a href='/price.pdf'>Прайс</a></nav></body></html>"

        async def _fake_fetch_page(url: str, **kwargs):
            if "votkuda.ru" in url:
                return agg_html, False
            return org_html, False

        mock_ocr = MagicMock()
        mock_ocr.extract_text_from_images = AsyncMock(
            return_value="Тариф Делегат 50 000 руб."
        )
        fake_ev = Event(id=1, canonical_title="Форум", data_status="ready")

        # 1. Прогон с реальным 2-Hop и лимитом VISION_OCR_MAX_PAGES_PER_RUN=4 (3 стр. + 1 стр.)
        with (
            patch("app.services.scraper.fetcher._fetch_raw_page_content", new=AsyncMock(side_effect=_fake_fetch_page)),
            patch("app.services.scraper.fetcher.fetch_pdf_bytes_safe", new=AsyncMock(return_value=scanned_pdf)),
            patch.object(scraper_pkg.settings, "LLM_API_KEY", ""),
            patch.object(scraper_pkg.settings, "VISION_OCR_MAX_PAGES_PER_RUN", 4),
            patch.object(scraper_pkg.settings, "VISION_OCR_MAX_PAGES_AUTO", 3),
            patch.object(scraper_pkg, "build_vision_ocr_provider", return_value=mock_ocr),
            patch.object(scraper_pkg, "ingest_event_from_text", new=AsyncMock(return_value=fake_ev)),
        ):
            summary = await run_customer_sources_monitoring(
                session,
                source_key="votkuda",
                catalog_scraper=FakeCatalogScraper(),
                dry_run=False,
            )

        self.assertEqual(summary.vision_ocr_pages_used, 4)
        self.assertEqual(mock_ocr.extract_text_from_images.await_count, 2)
        first_batch_len = len(mock_ocr.extract_text_from_images.await_args_list[0].args[0])
        second_batch_len = len(mock_ocr.extract_text_from_images.await_args_list[1].args[0])
        self.assertEqual((first_batch_len, second_batch_len), (3, 1))

        # 2. Обратная совместимость: замоканная старая 2-arg collect_event_dossiers не падает с TypeError
        stored_seen.clear()

        async def _legacy_collect_dossiers(cand, src):
            return [scraper_pkg.CollectedEventDossier(dossier_text="Legacy", source_urls=[cand.url])]

        with (
            patch.object(
                scraper_pkg,
                "collect_event_dossiers",
                new=AsyncMock(side_effect=_legacy_collect_dossiers),
            ),
            patch.object(scraper_pkg, "ingest_event_from_text", new=AsyncMock(return_value=fake_ev)),
        ):
            compat_summary = await run_customer_sources_monitoring(
                session,
                source_key="votkuda",
                catalog_scraper=FakeCatalogScraper(),
                dry_run=False,
            )
        self.assertEqual(compat_summary.ingested_ready_count, 2)
        self.assertEqual(compat_summary.vision_ocr_pages_used, 0)

    async def test_ingest_smart_event_warnings_and_ocr_mock(self) -> None:
        scanned_pdf = _make_blank_raster_pdf(num_pages=2)
        parsed_schema = EventIngestionSchema(
            canonical_title="Форум Строителей 2026",
            event_format="forum",
            city="Москва",
            country="Россия",
            is_online=False,
            start_date=datetime.date(2026, 12, 10),
            end_date=datetime.date(2026, 12, 11),
            summary=_valid_summary(),
            themes=["строительство"],
            full_regulation_markdown="Полный текст регламента форума. " * 30,
            tariffs=[],
            faq_cache=[],
        )

        async def _fake_execute(stmt):
            res = MagicMock()
            res.scalars.return_value.all.return_value = []
            res.scalar.return_value = 0
            return res

        session = AsyncMock()
        session.add = MagicMock()
        session.execute = AsyncMock(side_effect=_fake_execute)

        # 1. Выключенный OCR + текстовая заметка -> warning vision_ocr_not_configured
        with (
            patch.object(scraper_pkg.settings, "VISION_OCR_MODEL", None),
            patch(
                "app.services.scraper.ingestion._extract_structured_event_via_llm",
                new=AsyncMock(return_value=parsed_schema),
            ),
            patch.object(scraper_pkg, "get_embedding", new=AsyncMock(return_value=[0.1] * 1024)),
            patch.object(scraper_pkg, "find_duplicate_event", new=AsyncMock(return_value=None)),
            patch("app.services.scraper.ingestion._sync_event_chunks", new=AsyncMock()),
        ):
            ev_no_ocr = await ingest_smart_event(
                session,
                raw_text="Форум Строителей 2026 в Москве.",
                pdf_bytes=scanned_pdf,
            )

        self.assertIn("vision_ocr_not_configured", ev_no_ocr.missing_data_warnings)
        self.assertNotIn("pdf_scanned_pages_not_recognized", ev_no_ocr.missing_data_warnings)

        # 2. С моком OCR -> текст из OCR попадает в LLM-3 досье
        mock_ocr = MagicMock()
        mock_ocr.extract_text_from_images = AsyncMock(
            return_value="Тариф Спикер — 140 000 руб. с НДС."
        )
        captured_dossiers: list[str] = []

        async def _capture_llm(text: str) -> EventIngestionSchema:
            captured_dossiers.append(text)
            return parsed_schema

        with (
            patch(
                "app.services.scraper.ingestion._extract_structured_event_via_llm",
                new=AsyncMock(side_effect=_capture_llm),
            ),
            patch.object(scraper_pkg, "get_embedding", new=AsyncMock(return_value=[0.1] * 1024)),
            patch.object(scraper_pkg, "find_duplicate_event", new=AsyncMock(return_value=None)),
            patch("app.services.scraper.ingestion._sync_event_chunks", new=AsyncMock()),
        ):
            ev_with_ocr = await ingest_smart_event(
                session,
                pdf_bytes=scanned_pdf,
                vision_ocr=mock_ocr,
            )

        self.assertEqual(mock_ocr.extract_text_from_images.await_count, 1)
        self.assertIn("=== РАСПОЗНАННЫЙ OCR ТЕКСТ PDF ===", captured_dossiers[0])
        self.assertIn("140 000 руб.", captured_dossiers[0])
        self.assertNotIn("vision_ocr_not_configured", ev_with_ocr.missing_data_warnings)

        # 3. Смешанный PDF (1-я стр. обложка-картинка, 2-я стр. текст с тарифом и >= 600 симв.) -> OCR не вызывается
        mixed_pdf = _make_mixed_pdf(
            [
                "",
                (
                    "Official Forum Program and Delegate Tariff Package: 45 000 RUB with VAT, "
                    "Early Bird discount before December 1. "
                    + "Detailed conference schedule and plenary sessions for urban development. " * 8
                ),
            ]
        )
        mock_ocr_skip = MagicMock()
        mock_ocr_skip.extract_text_from_images = AsyncMock(return_value="should not be called")

        with (
            patch(
                "app.services.scraper.ingestion._extract_structured_event_via_llm",
                new=AsyncMock(return_value=parsed_schema),
            ),
            patch.object(scraper_pkg, "get_embedding", new=AsyncMock(return_value=[0.1] * 1024)),
            patch.object(scraper_pkg, "find_duplicate_event", new=AsyncMock(return_value=None)),
            patch("app.services.scraper.ingestion._sync_event_chunks", new=AsyncMock()),
        ):
            await ingest_smart_event(
                session,
                pdf_bytes=mixed_pdf,
                vision_ocr=mock_ocr_skip,
            )
        self.assertEqual(mock_ocr_skip.extract_text_from_images.await_count, 0)

    def test_upload_pdf_endpoint_413_limit_and_success(self) -> None:
        import app.api.manager as manager_module

        mock_mgr = User(
            id=1,
            email="mgr@skart.ru",
            password_hash="fakehash",
            full_name="Менеджер",
            telegram_chat_id=111,
        )
        app.dependency_overrides[get_current_manager] = lambda: mock_mgr

        async def _override_session():
            mock_session = AsyncMock()
            mock_session.scalar.return_value = 2
            yield mock_session

        app.dependency_overrides[get_async_session] = _override_session
        client = TestClient(app)

        try:
            with patch.object(manager_module.settings, "SCRAPER_MAX_PDF_BYTES", 1024):
                oversized_res = client.post(
                    "/api/manager/events/upload-pdf",
                    files={"file": ("big.pdf", b"%PDF-1.4 " + b"X" * 2048, "application/pdf")},
                )
            self.assertEqual(oversized_res.status_code, 413)

            ok_event = Event(id=77, canonical_title="Форум из PDF", data_status="ready")
            with (
                patch.object(manager_module.settings, "SCRAPER_MAX_PDF_BYTES", 1024 * 1024),
                patch.object(manager_module, "ingest_smart_event", new=AsyncMock(return_value=ok_event)),
            ):
                ok_res = client.post(
                    "/api/manager/events/upload-pdf",
                    files={"file": ("brochure.pdf", b"%PDF-1.4 sample", "application/pdf")},
                )
            self.assertEqual(ok_res.status_code, 200)
            self.assertEqual(ok_res.json()["event_id"], 77)
            self.assertEqual(ok_res.json()["tariffs_count"], 2)
        finally:
            app.dependency_overrides.clear()


if __name__ == "__main__":
    unittest.main()
