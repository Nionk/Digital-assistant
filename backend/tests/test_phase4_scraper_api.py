import asyncio
import datetime
import socket
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import httpx
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

# Add backend directory to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import app.api.manager as manager_module
import app.main as main_module
from app.core import security as security_module
from app.core.database import async_session_maker, engine, get_async_session
from app.core.security import create_access_token, get_current_manager
from app.main import app
from app.models.models import Event, ScraperRun, ScraperSource, User
from app.schemas.manager import ScraperRunDetailOut
from app.services import monitoring_job as monitoring_job_module
from app.services import scraper as scraper_pkg
from app.services.scraper import (
    CUSTOMER_SOURCES_REGISTRY,
    CaptchaBlockedError,
    CustomerSourceConfig,
    DiscoveredCandidate,
    DiscoveryResult,
    OpenAICompatibleVisionOCRProvider,
    ScrapingRunSummary,
    is_scraper_busy,
    recover_stale_scraper_runs,
    run_customer_sources_monitoring,
    run_persisted_scraper_job,
    should_run_vision_ocr,
    start_scraper_run_record,
    try_enqueue_scraper_run,
)
from app.services.scraper import runner as runner_module
from app.services.telegram import StubTelegramTransport, set_telegram_transport

_PUBLIC_ADDRINFO = [(2, 1, 6, "", ("93.184.216.34", 0))]


class _InMemoryScraperStore:
    def __init__(self) -> None:
        self.sources: dict[str, ScraperSource] = {}
        self.runs: dict[int, ScraperRun] = {}
        self.next_source_id: int = 1
        self.next_run_id: int = 1

    def seed_builtin_sources(self) -> None:
        now = datetime.datetime.now(datetime.UTC)
        for cfg in CUSTOMER_SOURCES_REGISTRY:
            if cfg.source_key in self.sources:
                continue
            row = ScraperSource(
                id=self.next_source_id,
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
                created_at=now,
                updated_at=now,
            )
            self.next_source_id += 1
            self.sources[cfg.source_key] = row

    def add_run(self, run: ScraperRun) -> ScraperRun:
        now = datetime.datetime.now(datetime.UTC)
        if run.id is None:
            run.id = self.next_run_id
            self.next_run_id += 1
        if run.started_at is None:
            run.started_at = now
        if run.sources_total is None:
            run.sources_total = 0
        if run.sources_done is None:
            run.sources_done = 0
        if run.urls_discovered is None:
            run.urls_discovered = 0
        if run.events_created is None:
            run.events_created = 0
        if run.events_updated is None:
            run.events_updated = 0
        if run.rejected_b2c is None:
            run.rejected_b2c = 0
        if run.rejected_geo is None:
            run.rejected_geo = 0
        if run.rejected_past is None:
            run.rejected_past = 0
        if run.errors_count is None:
            run.errors_count = 0
        if run.source_logs is None:
            run.source_logs = []
        self.runs[run.id] = run
        return run


class _FakeScraperAsyncSession:
    def __init__(
        self,
        store: _InMemoryScraperStore,
        *,
        on_commit: list[dict[str, object]] | None = None,
    ) -> None:
        self.store = store
        self.new: set[object] = set()
        self.deleted: set[object] = set()
        self.on_commit = on_commit

    def add(self, obj: object) -> None:
        self.new.add(obj)
        now = datetime.datetime.now(datetime.UTC)
        if isinstance(obj, ScraperSource):
            if obj.id is None:
                obj.id = self.store.next_source_id
                self.store.next_source_id += 1
            if obj.created_at is None:
                obj.created_at = now
            if obj.updated_at is None:
                obj.updated_at = now
            self.store.sources[obj.source_key] = obj
        elif isinstance(obj, ScraperRun):
            self.store.add_run(obj)

    async def delete(self, obj: object) -> None:
        self.deleted.add(obj)
        if isinstance(obj, ScraperSource):
            self.store.sources.pop(obj.source_key, None)
        elif isinstance(obj, ScraperRun) and obj.id is not None:
            self.store.runs.pop(obj.id, None)

    async def flush(self) -> None:
        now = datetime.datetime.now(datetime.UTC)
        for obj in list(self.new):
            if isinstance(obj, ScraperSource):
                if obj.id is None:
                    obj.id = self.store.next_source_id
                    self.store.next_source_id += 1
                if obj.created_at is None:
                    obj.created_at = now
                if obj.updated_at is None:
                    obj.updated_at = now
                self.store.sources[obj.source_key] = obj
            elif isinstance(obj, ScraperRun):
                self.store.add_run(obj)

    async def commit(self) -> None:
        await self.flush()
        self.new.clear()
        self.deleted.clear()
        if self.on_commit is not None:
            for run in self.store.runs.values():
                self.on_commit.append(
                    {
                        "id": run.id,
                        "status": run.status,
                        "sources_total": run.sources_total,
                        "sources_done": run.sources_done,
                        "urls_discovered": run.urls_discovered,
                        "events_created": run.events_created,
                        "events_updated": run.events_updated,
                        "errors_count": run.errors_count,
                        "source_logs_len": len(run.source_logs or []),
                    }
                )

    async def rollback(self) -> None:
        self.new.clear()

    async def refresh(self, obj: object) -> None:
        if isinstance(obj, ScraperSource) and obj.updated_at is None:
            obj.updated_at = datetime.datetime.now(datetime.UTC)

    async def get(self, model: type[object], pk: int) -> object | None:
        if model is ScraperRun:
            return self.store.runs.get(pk)
        return None

    async def execute(self, stmt) -> MagicMock:
        sql = " ".join(str(stmt).split())
        res = MagicMock()
        try:
            params = stmt.compile().params
        except (SQLAlchemyError, AttributeError, TypeError):
            params = {}

        if "FROM scraper_sources" in sql:
            rows = sorted(self.store.sources.values(), key=lambda r: r.id or 0)
            if "WHERE scraper_sources.source_key =" in sql:
                key_param = next(iter(params.values()), None)
                match = self.store.sources.get(str(key_param)) if key_param is not None else None
                res.scalar_one_or_none.return_value = match
                res.scalars.return_value.all.return_value = [match] if match else []
            else:
                res.scalars.return_value.all.return_value = rows
                res.scalar_one_or_none.return_value = rows[0] if rows else None
            return res

        if "FROM scraper_runs" in sql:
            runs = list(self.store.runs.values())
            if "scraper_runs.status IN" in sql:
                runs = [r for r in runs if r.status in ("queued", "running")]
            if "ORDER BY scraper_runs.id DESC" in sql:
                runs = sorted(runs, key=lambda r: r.id or 0, reverse=True)
            else:
                runs = sorted(runs, key=lambda r: r.id or 0)
            limit_val = params.get("param_1")
            if isinstance(limit_val, int) and "LIMIT" in sql:
                runs = runs[:limit_val]
            if sql.startswith("SELECT scraper_runs.id FROM scraper_runs"):
                res.scalar_one_or_none.return_value = runs[0].id if runs else None
                res.scalars.return_value.all.return_value = [r.id for r in runs]
            else:
                res.scalars.return_value.all.return_value = runs
                res.scalar_one_or_none.return_value = runs[0] if runs else None
            return res

        res.scalars.return_value.all.return_value = []
        res.scalar_one_or_none.return_value = None
        return res


class _SessionFactory:
    def __init__(
        self,
        store: _InMemoryScraperStore,
        *,
        on_commit: list[dict[str, object]] | None = None,
    ) -> None:
        self.store = store
        self.on_commit = on_commit

    def __call__(self):
        session = _FakeScraperAsyncSession(self.store, on_commit=self.on_commit)

        class _Ctx:
            async def __aenter__(self_ctx):
                return session

            async def __aexit__(self_ctx, exc_type, exc, tb):
                return False

        return _Ctx()


class TestPhase4Block0Fixes(unittest.IsolatedAsyncioTestCase):
    """Тесты доисправлений по итогам ревью Фазы 3 (Блок 0)."""

    def test_price_regex_and_free_events_skip_vision_ocr(self) -> None:
        fake_imgs = [b"\x89PNG\r\n\x1a\nfake"]
        filler = "Подробная программа деловых сессий, круглых столов и выставочной экспозиции в Москве. " * 10

        # "45 000 р.", "45 тыс. р.", "45 т.р." -> OCR пропускается
        for price_phrase in (
            "Тариф Делегат — 45 000 р. с НДС. ",
            "Стоимость участия: 45 тыс. р. ",
            "Пакет участника: 45 т.р. ",
        ):
            txt = price_phrase + filler
            self.assertGreaterEqual(len(txt), 600)
            self.assertFalse(should_run_vision_ocr("", txt, fake_imgs), msg=price_phrase)

        # Защита от ложного срабатывания на обычных словах ("10 раз", "5 стр.")
        false_pos_txt = "Тариф участия обсуждался 10 раз на 5 стр. регламента. " + filler
        self.assertTrue(should_run_vision_ocr("", false_pos_txt, fake_imgs))

        # Бесплатные мероприятия пропускают лишний OCR
        for free_phrase in (
            "Участие бесплатное по предварительной регистрации. ",
            "Бесплатное участие для девелоперов и архитекторов. ",
            "Вход свободный при наличии бейджа. ",
            "Бесплатное посещение выставки и деловой программы. ",
        ):
            free_txt = free_phrase + filler
            self.assertGreaterEqual(len(free_txt), 600)
            self.assertFalse(should_run_vision_ocr("", free_txt, fake_imgs), msg=free_phrase)

        # Отрицание ("не бесплатное") не считается бесплатным
        neg_free_txt = "Участие не бесплатное, подробности у организаторов. " + filler
        self.assertTrue(should_run_vision_ocr("", neg_free_txt, fake_imgs))

    async def test_vision_ocr_provider_defaults_batch_3_and_max_tokens_4000(self) -> None:
        provider = OpenAICompatibleVisionOCRProvider(model="google/gemini-2.5-flash-lite")
        self.assertEqual(provider.batch_size, 3)
        self.assertEqual(provider.max_tokens, 4000)

        imgs = [b"\x89PNG\r\n\x1a\n" + bytes([i]) for i in range(6)]
        fake_resp = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="Распознанный текст"))],
            usage=SimpleNamespace(prompt_tokens=100, completion_tokens=50, total_tokens=150),
        )
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=fake_resp)

        with patch.object(scraper_pkg, "raw_openai_client", new=mock_client):
            out = await provider.extract_text_from_images(imgs)

        self.assertIn("Распознанный текст", out)
        self.assertEqual(mock_client.chat.completions.create.await_count, 2)
        for call in mock_client.chat.completions.create.await_args_list:
            self.assertEqual(call.kwargs["max_tokens"], 4000)
            img_parts = [p for p in call.kwargs["messages"][1]["content"] if p["type"] == "image_url"]
            self.assertEqual(len(img_parts), 3)

    async def test_upload_pdf_streaming_chunks_stops_early_with_413_and_closes_file(self) -> None:
        mock_mgr = User(
            id=1,
            email="mgr@skart.ru",
            password_hash="x",
            full_name="Менеджер",
        )
        read_calls: list[int] = []
        closed = False

        class _ChunkedUploadFile:
            def __init__(self) -> None:
                self._chunks = [
                    b"%PDF-1.4 " + b"A" * 300,
                    b"B" * 400,
                    b"C" * 500,  # На 2-м чанке 309 + 400 = 709 > 512 -> 3-й чанк даже не читается!
                ]
                self._idx = 0

            async def read(self, size: int = -1) -> bytes:
                read_calls.append(size)
                if self._idx >= len(self._chunks):
                    return b""
                chunk = self._chunks[self._idx]
                self._idx += 1
                return chunk

            async def close(self) -> None:
                nonlocal closed
                closed = True

        fake_file = _ChunkedUploadFile()
        mock_session = AsyncMock()
        with (
            patch.object(manager_module.settings, "SCRAPER_MAX_PDF_BYTES", 512),
            self.assertRaises(HTTPException) as ctx,
        ):
            await manager_module.upload_event_material(
                current_manager=mock_mgr,
                db=mock_session,
                file=fake_file,  # type: ignore[arg-type]
                raw_text=None,
                source_url=None,
            )
        self.assertEqual(getattr(ctx.exception, "status_code", None), 413)
        self.assertTrue(closed)
        self.assertEqual(len(read_calls), 2)
        self.assertTrue(all(sz == manager_module._UPLOAD_PDF_CHUNK_SIZE for sz in read_calls))


class TestPhase4RunnerAndRecovery(unittest.IsolatedAsyncioTestCase):
    """Тесты runner.py, recover_stale_scraper_runs, live-прогресса и monitoring_job."""

    def setUp(self) -> None:
        set_telegram_transport(StubTelegramTransport())
        manager_module._is_scraper_running = False

    def tearDown(self) -> None:
        set_telegram_transport(None)
        manager_module._is_scraper_running = False

    async def test_recover_stale_scraper_runs_and_lifespan_resilience(self) -> None:
        store = _InMemoryScraperStore()
        r1 = store.add_run(ScraperRun(status="running", target_source_key="all", triggered_by="manual"))
        r2 = store.add_run(ScraperRun(status="queued", target_source_key="architime", triggered_by="scheduler"))
        r3 = store.add_run(ScraperRun(status="completed", target_source_key="votkuda", triggered_by="manual"))

        session = _FakeScraperAsyncSession(store)
        recovered = await recover_stale_scraper_runs(session)  # type: ignore[arg-type]
        self.assertEqual(recovered, 2)
        self.assertEqual(r1.status, "failed")
        self.assertEqual(r1.error_message, "Прервано перезапуском сервера")
        self.assertIsNotNone(r1.finished_at)
        self.assertEqual(r2.status, "failed")
        self.assertEqual(r2.error_message, "Прервано перезапуском сервера")
        self.assertEqual(r3.status, "completed")

        # Lifespan безопасно переживает ошибку БД в recover_stale_scraper_runs
        mock_engine = MagicMock()
        mock_engine.dispose = AsyncMock()
        with (
            patch.object(main_module.settings, "ENABLE_SCHEDULER", False),
            patch.object(
                main_module,
                "recover_stale_scraper_runs",
                new=AsyncMock(side_effect=SQLAlchemyError("DB offline")),
            ),
            patch.object(main_module, "engine", new=mock_engine),
            patch.object(main_module.raw_openai_client, "close", new=AsyncMock()),
            patch.object(main_module.embedding_client, "close", new=AsyncMock()),
        ):
            async with main_module.lifespan(main_module.app):
                pass

    async def test_monitoring_splits_created_vs_updated_and_emits_progress(self) -> None:
        store = _InMemoryScraperStore()
        store.seed_builtin_sources()
        # Оставляем только 1 включенный источник для чистоты проверки
        for k, row in store.sources.items():
            row.is_enabled = k == "architime"

        class FakeTwoCardScraper:
            async def fetch_catalog_urls(self, source: CustomerSourceConfig) -> list[str]:
                return [
                    "https://www.architime.ru/activity/2026/new_one.htm",
                    "https://www.architime.ru/activity/2026/duplicate_two.htm",
                ]

        existing_ev = Event(
            id=50,
            canonical_title="Существующий форум",
            normalized_title="существующий форум",
            event_format="forum",
            city="Москва",
            is_online=False,
            start_date=datetime.date(2026, 12, 10),
            end_date=datetime.date(2026, 12, 11),
            summary="Описание существующего форума " * 15,
            themes=["архитектура"],
            source_urls=["https://other-site.ru/event"],
            data_status="ready",
        )

        async def _fake_llm(text: str):
            from app.schemas.event_ingestion import EventIngestionSchema

            is_dup = "DUP_MARKER" in text
            return EventIngestionSchema(
                canonical_title="Существующий форум" if is_dup else "Новый форум 2026",
                event_format="forum",
                city="Москва",
                country="Россия",
                is_online=False,
                start_date=datetime.date(2026, 12, 10),
                end_date=datetime.date(2026, 12, 11),
                summary="Подробное описание форума архитекторов и застройщиков в Москве. " * 6,
                themes=["архитектура"],
                full_regulation_markdown="Регламент мероприятия и условия участия. " * 25,
                tariffs=[],
                faq_cache=[],
            )

        async def _fake_find_dup(sess, schema):
            return existing_ev if "Существующий" in schema.canonical_title else None

        async def _fake_collect(cand, src):
            marker = "DUP_MARKER" if "duplicate_two" in cand.url else "NEW_MARKER"
            return [scraper_pkg.CollectedEventDossier(dossier_text=marker, source_urls=[cand.url])]

        progress_snapshots: list[tuple[dict[str, object], dict[str, int]]] = []

        def _on_prog(src_log: dict[str, object], totals: dict[str, int]) -> None:
            progress_snapshots.append((dict(src_log), dict(totals)))

        mock_session = AsyncMock()
        mock_session.new = set()
        mock_session.add = MagicMock()

        async def _exec(stmt):
            sql = str(stmt)
            res = MagicMock()
            if "FROM scraper_sources" in sql:
                res.scalars.return_value.all.return_value = list(store.sources.values())
            elif "FROM event_tariffs" in sql:
                res.scalars.return_value.all.return_value = []
                res.scalar.return_value = 0
            elif "SELECT count" in sql:
                res.scalar.return_value = 0
            else:
                res.scalars.return_value.all.return_value = []
                res.scalar_one_or_none.return_value = None
            return res

        mock_session.execute = AsyncMock(side_effect=_exec)

        with (
            patch.object(scraper_pkg, "collect_event_dossiers", new=AsyncMock(side_effect=_fake_collect)),
            patch("app.services.scraper.ingestion._extract_structured_event_via_llm", new=AsyncMock(side_effect=_fake_llm)),
            patch.object(scraper_pkg, "get_embedding", new=AsyncMock(return_value=[0.1] * 1024)),
            patch.object(scraper_pkg, "find_duplicate_event", new=AsyncMock(side_effect=_fake_find_dup)),
            patch.object(scraper_pkg, "invalidate_rag_cache", new=AsyncMock()),
            patch("app.services.scraper.ingestion._sync_event_chunks", new=AsyncMock()),
        ):
            summary = await run_customer_sources_monitoring(
                mock_session,
                source_key="architime",
                catalog_scraper=FakeTwoCardScraper(),
                dry_run=False,
                on_source_progress=_on_prog,
            )

        self.assertEqual(summary.events_created_count, 1)
        self.assertEqual(summary.events_updated_count, 1)
        self.assertEqual(len(progress_snapshots), 1)
        src_log, totals = progress_snapshots[0]
        self.assertEqual(src_log["events_created"], 1)
        self.assertEqual(src_log["events_updated"], 1)
        saved_events = src_log["saved_events"]
        self.assertIsInstance(saved_events, list)
        self.assertEqual(len(saved_events), 2)
        self.assertEqual([ev["action"] for ev in saved_events], ["created", "updated"])
        self.assertEqual(saved_events[0]["title"], "Новый форум 2026")
        self.assertEqual(saved_events[1]["event_id"], 50)
        self.assertEqual(totals["events_created"], 1)
        self.assertEqual(totals["events_updated"], 1)

    async def test_run_persisted_scraper_job_live_progress_completed_and_failed(self) -> None:
        store = _InMemoryScraperStore()
        commits_log: list[dict[str, object]] = []
        factory = _SessionFactory(store, on_commit=commits_log)

        async def _fake_monitoring(session, *, source_key=None, max_urls_per_source=None, dry_run=False, on_source_progress=None):
            if on_source_progress:
                await on_source_progress(
                    {"source_key": "architime", "discovered_total": 5, "events_created": 2, "events_updated": 1},
                    {
                        "sources_total": 2,
                        "sources_done": 1,
                        "urls_discovered": 5,
                        "events_created": 2,
                        "events_updated": 1,
                        "rejected_b2c": 1,
                        "rejected_geo": 0,
                        "rejected_past": 0,
                        "errors_count": 0,
                    },
                )
                await on_source_progress(
                    {"source_key": "votkuda", "discovered_total": 3, "events_created": 1, "events_updated": 0},
                    {
                        "sources_total": 2,
                        "sources_done": 2,
                        "urls_discovered": 8,
                        "events_created": 3,
                        "events_updated": 1,
                        "rejected_b2c": 2,
                        "rejected_geo": 1,
                        "rejected_past": 1,
                        "errors_count": 0,
                    },
                )
            return ScrapingRunSummary(
                checked_sources=2,
                discovered_urls=8,
                ingested_ready_count=3,
                needs_enrichment_count=1,
                needs_enrichment_titles=["Форум Без Цены"],
                failed_count=0,
                dry_run=dry_run,
                rejected_b2c_count=2,
                rejected_geo_count=1,
                rejected_past_count=1,
                events_created_count=3,
                events_updated_count=1,
                per_source_report=[
                    {"source_key": "architime", "discovered_total": 5, "events_created": 2, "events_updated": 1},
                    {"source_key": "votkuda", "discovered_total": 3, "events_created": 1, "events_updated": 0},
                ],
            )

        transport = StubTelegramTransport()
        set_telegram_transport(transport)

        async with factory() as s:
            run_row = await start_scraper_run_record(s, target_source_key="all", triggered_by="manual")
        run_id = run_row.id

        with (
            patch.object(runner_module, "async_session_maker", new=factory),
            patch.object(scraper_pkg, "run_customer_sources_monitoring", new=AsyncMock(side_effect=_fake_monitoring)),
        ):
            summary = await run_persisted_scraper_job(run_id, "all", dry_run=False)

        self.assertIsNotNone(summary)
        self.assertFalse(manager_module._is_scraper_running)
        final_run = store.runs[run_id]
        self.assertEqual(final_run.status, "completed")
        self.assertEqual(final_run.sources_total, 2)
        self.assertEqual(final_run.sources_done, 2)
        self.assertEqual(final_run.urls_discovered, 8)
        self.assertEqual(final_run.events_created, 3)
        self.assertEqual(final_run.events_updated, 1)
        self.assertEqual(final_run.rejected_b2c, 2)
        self.assertEqual(final_run.rejected_geo, 1)
        self.assertEqual(final_run.rejected_past, 1)
        self.assertIsNotNone(final_run.finished_at)
        self.assertEqual(len(final_run.source_logs), 2)
        # Проверяем промежуточные live-коммиты: queued -> running -> source 1 (sources_done=1) -> source 2 -> completed
        statuses_seen = [c["status"] for c in commits_log]
        self.assertIn("running", statuses_seen)
        self.assertTrue(any(c["status"] == "running" and c["sources_done"] == 1 for c in commits_log))
        self.assertEqual(len(transport.sent_messages), 1)

        # dry_run=True не шлет Telegram-уведомление
        async with factory() as s:
            dry_row = await start_scraper_run_record(s, target_source_key="all", triggered_by="manual")
        with (
            patch.object(runner_module, "async_session_maker", new=factory),
            patch.object(scraper_pkg, "run_customer_sources_monitoring", new=AsyncMock(side_effect=_fake_monitoring)),
        ):
            await run_persisted_scraper_job(dry_row.id, "all", dry_run=True)
        self.assertEqual(len(transport.sent_messages), 1)

        # При ошибке скрейпера статус -> failed и флаг сбрасывается
        async with factory() as s:
            err_row = await start_scraper_run_record(s, target_source_key="archdialog", triggered_by="manual")
        with (
            patch.object(runner_module, "async_session_maker", new=factory),
            patch.object(
                scraper_pkg,
                "run_customer_sources_monitoring",
                new=AsyncMock(side_effect=ValueError("Источник работает только в режиме ручного Умного импорта.")),
            ),
        ):
            failed_summary = await run_persisted_scraper_job(err_row.id, "archdialog", dry_run=False)
        self.assertIsNone(failed_summary)
        self.assertFalse(manager_module._is_scraper_running)
        self.assertEqual(store.runs[err_row.id].status, "failed")
        self.assertIn("ручного Умного импорта", store.runs[err_row.id].error_message or "")
        self.assertIsNotNone(store.runs[err_row.id].finished_at)

    async def test_monitoring_job_delegates_to_runner_with_scheduler_trigger(self) -> None:
        store = _InMemoryScraperStore()
        factory = _SessionFactory(store)
        mock_job = AsyncMock(return_value=None)

        with (
            patch.object(monitoring_job_module, "async_session_maker", new=factory),
            patch.object(monitoring_job_module, "run_persisted_scraper_job", new=mock_job),
        ):
            await monitoring_job_module.run_nightly_monitoring_job()

        mock_job.assert_awaited_once()
        run_id_arg, target_arg = mock_job.await_args.args
        self.assertEqual(target_arg, "all")
        self.assertEqual(store.runs[run_id_arg].triggered_by, "scheduler")
        self.assertFalse(await is_scraper_busy())

    async def test_run_persisted_scraper_job_handles_cancelled_error(self) -> None:
        store = _InMemoryScraperStore()
        factory = _SessionFactory(store)
        async with factory() as s:
            cancel_row = await start_scraper_run_record(
                s, target_source_key="architime", triggered_by="manual"
            )

        with (
            patch.object(runner_module, "async_session_maker", new=factory),
            patch.object(
                scraper_pkg,
                "run_customer_sources_monitoring",
                new=AsyncMock(side_effect=asyncio.CancelledError()),
            ),
            self.assertRaises(asyncio.CancelledError),
        ):
            await run_persisted_scraper_job(cancel_row.id, "architime", dry_run=False)

        self.assertFalse(manager_module._is_scraper_running)
        saved = store.runs[cancel_row.id]
        self.assertEqual(saved.status, "failed")
        self.assertIn("CancelledError", saved.error_message or "")
        self.assertIsNotNone(saved.finished_at)

    async def test_try_enqueue_scraper_run_atomic_concurrency(self) -> None:
        store = _InMemoryScraperStore()
        factory = _SessionFactory(store)

        async def _attempt(key: str, trigger: str):
            async with factory() as s:
                return await try_enqueue_scraper_run(
                    s, target_source_key=key, triggered_by=trigger
                )

        res1, res2 = await asyncio.gather(
            _attempt("all", "manual"),
            _attempt("architime", "scheduler"),
        )
        enqueued = [r for r in (res1, res2) if r[0] is not None]
        rejected = [r for r in (res1, res2) if r[0] is None]

        self.assertEqual(len(enqueued), 1)
        self.assertEqual(len(rejected), 1)
        self.assertEqual(len(store.runs), 1)
        self.assertEqual(rejected[0][1], enqueued[0][0].id)
        self.assertTrue(manager_module._is_scraper_running)

    async def test_cancelled_error_marks_run_failed_and_releases_lock(self) -> None:
        store = _InMemoryScraperStore()
        factory = _SessionFactory(store)

        async def _cancelled_monitoring(*args, **kwargs):
            raise asyncio.CancelledError()

        async with factory() as s:
            run_row = await start_scraper_run_record(s, target_source_key="all", triggered_by="manual")

        with (
            patch.object(runner_module, "async_session_maker", new=factory),
            patch.object(
                scraper_pkg,
                "run_customer_sources_monitoring",
                new=AsyncMock(side_effect=_cancelled_monitoring),
            ),
            self.assertRaises(asyncio.CancelledError),
        ):
            await run_persisted_scraper_job(run_row.id, "all", dry_run=False)

        self.assertFalse(manager_module._is_scraper_running)
        self.assertFalse(await is_scraper_busy())
        self.assertEqual(store.runs[run_row.id].status, "failed")
        self.assertEqual(store.runs[run_row.id].error_message, "Прогон прерван (CancelledError)")
        self.assertIsNotNone(store.runs[run_row.id].finished_at)

    async def test_try_enqueue_scraper_run_prevents_concurrent_race(self) -> None:
        store = _InMemoryScraperStore()
        factory = _SessionFactory(store)

        async def _enqueue(trigger: str):
            async with factory() as s:
                return await try_enqueue_scraper_run(
                    s,
                    target_source_key="all",
                    triggered_by=trigger,
                )

        res1, res2 = await asyncio.gather(_enqueue("manual"), _enqueue("scheduler"))
        created_rows = [r for r, _ in (res1, res2) if r is not None]
        rejected_ids = [active_id for r, active_id in (res1, res2) if r is None]

        self.assertEqual(len(created_rows), 1)
        self.assertEqual(len(rejected_ids), 1)
        self.assertEqual(rejected_ids[0], created_rows[0].id)
        self.assertEqual(len(store.runs), 1)


class TestPhase4ScraperSourcesAndRunsAPI(unittest.TestCase):
    """Тесты FastAPI-ручек /api/manager/scraper/sources, preview, run, runs, runs/latest."""

    def setUp(self) -> None:
        self.store = _InMemoryScraperStore()
        self.factory = _SessionFactory(self.store)
        self.mock_mgr = User(
            id=1,
            email="mgr@skart.ru",
            password_hash="fakehash",
            full_name="Менеджер",
            telegram_chat_id=111,
        )
        manager_module._is_scraper_running = False
        set_telegram_transport(StubTelegramTransport())
        app.dependency_overrides[get_current_manager] = lambda: self.mock_mgr

        async def _override_session():
            async with self.factory() as s:
                yield s

        app.dependency_overrides[get_async_session] = _override_session
        self.client = TestClient(app)

    def tearDown(self) -> None:
        app.dependency_overrides.clear()
        manager_module._is_scraper_running = False
        set_telegram_transport(None)

    def test_sources_and_runs_require_auth_401(self) -> None:
        app.dependency_overrides.pop(get_current_manager, None)
        with (
            patch.object(security_module.settings, "ENVIRONMENT", "prod"),
            patch.object(security_module.settings, "ALLOW_DEMO_AUTH_BYPASS", False),
        ):
            for method, path, body in (
                ("GET", "/api/manager/scraper/sources", None),
                ("POST", "/api/manager/scraper/sources", {"display_name": "Test", "catalog_urls": ["https://example.com"]}),
                ("PATCH", "/api/manager/scraper/sources/architime", {"is_enabled": False}),
                ("DELETE", "/api/manager/scraper/sources/custom", None),
                ("POST", "/api/manager/scraper/sources/preview", {"catalog_urls": ["https://example.com"]}),
                ("POST", "/api/manager/scraper/run", {"source_key": "all"}),
                ("GET", "/api/manager/scraper/runs", None),
                ("GET", "/api/manager/scraper/runs/latest", None),
            ):
                res = self.client.request(method, path, json=body)
                self.assertEqual(res.status_code, 401, msg=f"{method} {path}")

    def test_sources_crud_ssrf_regex_conflict_and_builtin_protection(self) -> None:
        # 1. GET /sources возвращает 9 builtin источников
        res_list = self.client.get("/api/manager/scraper/sources")
        self.assertEqual(res_list.status_code, 200)
        items = res_list.json()
        self.assertEqual(len(items), 9)
        self.assertTrue(all(item["is_builtin"] is True for item in items))
        archdialog = next(item for item in items if item["source_key"] == "archdialog")
        self.assertEqual(archdialog["adapter_type"], "manual_only")
        self.assertFalse(archdialog["is_enabled"])

        # 2. SSRF защита на POST (http://127.0.0.1/...) -> 400
        res_ssrf = self.client.post(
            "/api/manager/scraper/sources",
            json={
                "display_name": "Внутренний ресурс",
                "catalog_urls": ["http://127.0.0.1:8000/admin"],
            },
        )
        self.assertEqual(res_ssrf.status_code, 400)

        # 3. Битый regex и превышение лимитов (кол-во > 20 или длина > 300) отклоняются (422)
        res_bad_regex = self.client.post(
            "/api/manager/scraper/sources",
            json={
                "display_name": "Портал с битым regex",
                "catalog_urls": ["https://events.example.ru/"],
                "card_url_patterns": ["[unclosed"],
            },
        )
        self.assertEqual(res_bad_regex.status_code, 422)

        res_too_many_regex = self.client.post(
            "/api/manager/scraper/sources",
            json={
                "display_name": "Слишком много паттернов",
                "catalog_urls": ["https://events.example.ru/"],
                "card_url_patterns": [f"/event/{i}" for i in range(21)],
            },
        )
        self.assertEqual(res_too_many_regex.status_code, 422)

        res_too_long_regex = self.client.post(
            "/api/manager/scraper/sources/preview",
            json={
                "catalog_urls": ["https://events.example.ru/"],
                "exclude_url_patterns": ["a" * 301],
            },
        )
        self.assertEqual(res_too_long_regex.status_code, 422)

        # 4. Успешное создание по Варианту А (с авто-слагом и без regex)
        with patch("app.services.scraper.fetcher.socket.getaddrinfo", return_value=_PUBLIC_ADDRINFO):
            res_create = self.client.post(
                "/api/manager/scraper/sources",
                json={
                    "display_name": "СтройФорум Урал",
                    "catalog_urls": ["https://stroyforum-ural.ru/events/"],
                    "adapter_type": "html_list",
                    "b2b_filter_enabled": True,
                    "russia_online_only": True,
                },
            )
        self.assertEqual(res_create.status_code, 201, res_create.text)
        created = res_create.json()
        self.assertEqual(created["source_key"], "stroyforum_ural")
        self.assertFalse(created["is_builtin"])
        self.assertTrue(created["b2b_filter_enabled"])
        self.assertEqual(created["card_url_patterns"], [])

        # 5. Дубль source_key -> 409 Conflict
        with patch("app.services.scraper.fetcher.socket.getaddrinfo", return_value=_PUBLIC_ADDRINFO):
            res_dup = self.client.post(
                "/api/manager/scraper/sources",
                json={
                    "display_name": "Другое название",
                    "source_key": "stroyforum_ural",
                    "catalog_urls": ["https://stroyforum-ural.ru/events/"],
                },
            )
        self.assertEqual(res_dup.status_code, 409)

        # 6. PATCH обновляет is_enabled и max_urls_per_run
        res_patch = self.client.patch(
            "/api/manager/scraper/sources/stroyforum_ural",
            json={"is_enabled": False, "max_urls_per_run": 15},
        )
        self.assertEqual(res_patch.status_code, 200)
        self.assertFalse(res_patch.json()["is_enabled"])
        self.assertEqual(res_patch.json()["max_urls_per_run"], 15)

        # Нельзя включить авто-скан для manual_only archdialog
        res_arch = self.client.patch(
            "/api/manager/scraper/sources/archdialog",
            json={"is_enabled": True},
        )
        self.assertEqual(res_arch.status_code, 400)

        # 404 на несуществующий ключ
        res_404 = self.client.patch(
            "/api/manager/scraper/sources/missing_key",
            json={"is_enabled": False},
        )
        self.assertEqual(res_404.status_code, 404)

        # 7. DELETE запрещен для builtin -> 400, разрешен для пользовательского
        res_del_builtin = self.client.delete("/api/manager/scraper/sources/architime")
        self.assertEqual(res_del_builtin.status_code, 400)
        self.assertIn("нельзя удалить", res_del_builtin.json()["detail"].lower())

        res_del_custom = self.client.delete("/api/manager/scraper/sources/stroyforum_ural")
        self.assertEqual(res_del_custom.status_code, 200)
        self.assertTrue(res_del_custom.json()["deleted"])
        self.assertNotIn("stroyforum_ural", self.store.sources)

    def test_preview_endpoint_discovery_ssrf_and_controlled_error(self) -> None:
        # 1. SSRF -> 400
        res_ssrf = self.client.post(
            "/api/manager/scraper/sources/preview",
            json={"catalog_urls": ["http://169.254.169.254/latest/meta-data/"]},
        )
        self.assertEqual(res_ssrf.status_code, 400)

        # 2. Успешный предпросмотр использует только первый catalog_urls[0], максимум 10 примеров, 0 LLM
        seen_catalog_urls: list[tuple[str, ...]] = []

        async def _fake_discover(self_scraper, cfg: CustomerSourceConfig) -> DiscoveryResult:
            seen_catalog_urls.append(cfg.catalog_urls)
            cands = [
                DiscoveredCandidate(
                    url=f"https://portal.ru/events/{i}",
                    title=f"Событие {i}",
                    snippet=f"Описание {i}",
                    source_key=cfg.source_key,
                    is_digest=(i == 0),
                )
                for i in range(12)
            ]
            return DiscoveryResult(candidates=cands, rejected_b2c=4, rejected_geo=2)

        with (
            patch("app.services.scraper.fetcher.socket.getaddrinfo", return_value=_PUBLIC_ADDRINFO),
            patch.object(manager_module.HttpCatalogSourceScraper, "discover_catalog", new=_fake_discover),
            patch.object(scraper_pkg, "structured_llm_client", new=MagicMock()) as mock_llm,
        ):
            res_ok = self.client.post(
                "/api/manager/scraper/sources/preview",
                json={
                    "catalog_urls": [
                        "https://portal.ru/events/",
                        "https://portal.ru/conferences/",
                    ],
                    "b2b_filter_enabled": True,
                },
            )

        self.assertEqual(res_ok.status_code, 200)
        body = res_ok.json()
        self.assertEqual(seen_catalog_urls, [("https://portal.ru/events/",)])
        self.assertEqual(body["discovered_count"], 12)
        self.assertEqual(body["rejected_b2c"], 4)
        self.assertEqual(body["rejected_geo"], 2)
        self.assertEqual(body["checked_url"], "https://portal.ru/events/")
        self.assertEqual(body["total_catalog_urls"], 2)
        self.assertEqual(len(body["sample_candidates"]), 10)
        self.assertTrue(body["sample_candidates"][0]["is_digest"])
        self.assertIsNone(body["error"])
        self.assertEqual(mock_llm.chat.completions.create.call_count, 0)

        # 3. Контролируемая ошибка при CaptchaBlockedError без 500
        with (
            patch("app.services.scraper.fetcher.socket.getaddrinfo", return_value=_PUBLIC_ADDRINFO),
            patch.object(
                manager_module.HttpCatalogSourceScraper,
                "discover_catalog",
                new=AsyncMock(side_effect=CaptchaBlockedError("Защищено SmartCaptcha")),
            ),
        ):
            res_err = self.client.post(
                "/api/manager/scraper/sources/preview",
                json={"catalog_urls": ["https://portal.ru/events/"]},
            )
        self.assertEqual(res_err.status_code, 200)
        self.assertEqual(res_err.json()["discovered_count"], 0)
        self.assertEqual(res_err.json()["checked_url"], "https://portal.ru/events/")
        self.assertEqual(res_err.json()["total_catalog_urls"], 1)
        self.assertIn("SmartCaptcha", res_err.json()["error"])

    def test_run_and_runs_history_endpoints(self) -> None:
        # 0. При пустой БД /runs/latest возвращает null, /runs -> {"items": []}
        res_latest_empty = self.client.get("/api/manager/scraper/runs/latest")
        self.assertEqual(res_latest_empty.status_code, 200)
        self.assertIsNone(res_latest_empty.json())

        res_runs_empty = self.client.get("/api/manager/scraper/runs")
        self.assertEqual(res_runs_empty.status_code, 200)
        self.assertEqual(res_runs_empty.json(), {"items": []})

        # 1. manual_only -> 400
        res_manual = self.client.post("/api/manager/scraper/run", json={"source_key": "archdialog"})
        self.assertEqual(res_manual.status_code, 400)

        # 2. disabled источник -> 400
        self.store.seed_builtin_sources()
        self.store.sources["votkuda"].is_enabled = False
        res_disabled = self.client.post("/api/manager/scraper/run", json={"source_key": "votkuda"})
        self.assertEqual(res_disabled.status_code, 400)

        # 3. dry_run=True + max_urls_per_source=5 ставит задачу и возвращает run_id
        mock_worker = AsyncMock()
        with patch.object(manager_module, "_execute_background_monitoring", new=mock_worker):
            res_dry = self.client.post(
                "/api/manager/scraper/run",
                json={"source_key": "architime", "dry_run": True, "max_urls_per_source": 5},
            )
            self.assertEqual(res_dry.status_code, 200)
            dry_data = res_dry.json()
            self.assertEqual(dry_data["status"], "queued")
            self.assertTrue(dry_data["dry_run"])
            self.assertIsInstance(dry_data["run_id"], int)
            self.assertEqual(mock_worker.await_count, 1)
            self.assertEqual(mock_worker.await_args.kwargs["dry_run"], True)
            self.assertEqual(mock_worker.await_args.kwargs["max_urls_per_source"], 5)

            # 4. Повторный запуск при занятом флаге -> busy без запуска воркера
            res_busy = self.client.post("/api/manager/scraper/run", json={"source_key": "all"})
            self.assertEqual(res_busy.status_code, 200)
            self.assertIn("уже выполняется", res_busy.json()["message"])
            self.assertEqual(res_busy.json()["run_id"], dry_data["run_id"])
            self.assertEqual(mock_worker.await_count, 1)

        # 5. GET /runs и GET /runs/latest возвращают историю по id DESC
        manager_module._is_scraper_running = False
        completed_run = self.store.add_run(
            ScraperRun(
                status="completed",
                target_source_key="all",
                triggered_by="scheduler",
                sources_total=2,
                sources_done=2,
                urls_discovered=10,
                events_created=4,
                events_updated=2,
                rejected_b2c=3,
                rejected_geo=1,
                rejected_past=0,
                errors_count=0,
                source_logs=[
                    {
                        "source_key": "architime",
                        "display_name": "ARCHITIME",
                        "adapter_type": "html_list",
                        "catalog_urls": ["https://www.architime.ru/lecturexibition.htm"],
                        "discovered_total": 6,
                        "selected_new_count": 4,
                        "events_created": 3,
                        "events_updated": 1,
                        "rejected_b2c": 0,
                        "rejected_geo": 0,
                        "rejected_past": 0,
                        "errors_count": 0,
                        "candidate_urls": ["https://www.architime.ru/activity/2026/a.htm"],
                        "error": None,
                    }
                ],
                finished_at=datetime.datetime.now(datetime.UTC),
            )
        )

        res_runs = self.client.get("/api/manager/scraper/runs?limit=5")
        self.assertEqual(res_runs.status_code, 200)
        runs_items = res_runs.json()["items"]
        self.assertEqual(len(runs_items), 2)
        self.assertEqual(runs_items[0]["id"], completed_run.id)
        self.assertEqual(runs_items[0]["triggered_by"], "scheduler")
        self.assertFalse(runs_items[0]["dry_run"])
        self.assertEqual(runs_items[0]["source_logs"][0]["events_created"], 3)
        self.assertEqual(runs_items[1]["id"], dry_data["run_id"])
        self.assertEqual(runs_items[1]["triggered_by"], "manual_dry_run")
        self.assertTrue(runs_items[1]["dry_run"])

        res_latest = self.client.get("/api/manager/scraper/runs/latest")
        self.assertEqual(res_latest.status_code, 200)
        self.assertEqual(res_latest.json()["id"], completed_run.id)
        self.assertEqual(res_latest.json()["status"], "completed")
        self.assertFalse(res_latest.json()["dry_run"])


def _is_postgres_online() -> bool:
    """Проверяет доступность TCP-порта PostgreSQL (5432) на localhost или db."""
    for host in ("localhost", "127.0.0.1", "db"):
        try:
            with socket.create_connection((host, 5432), timeout=0.5):
                return True
        except OSError:
            continue
    return False


@unittest.skipUnless(_is_postgres_online(), "Требуется запущенный PostgreSQL")
class TestPhase4PostgresIntegration(unittest.IsolatedAsyncioTestCase):
    """Реальный интеграционный тест Фазы 4 с PostgreSQL (async_session_maker + JSONB)."""

    async def asyncSetUp(self) -> None:
        app.dependency_overrides.clear()
        manager_module._is_scraper_running = False
        set_telegram_transport(StubTelegramTransport())
        self.created_source_keys: list[str] = []
        self.created_run_ids: list[int] = []
        self.created_user_id: int | None = None

        async with async_session_maker() as s:
            mgr_res = await s.execute(select(User).order_by(User.id.asc()).limit(1))
            mgr = mgr_res.scalar_one_or_none()
            if mgr is None:
                mgr = User(
                    email=f"pg_test_mgr_{uuid4().hex[:6]}@skart.ru",
                    password_hash="fakehash",
                    full_name="PG Test Manager",
                )
                s.add(mgr)
                await s.commit()
                await s.refresh(mgr)
                self.created_user_id = mgr.id
            self.auth_headers = {
                "Authorization": f"Bearer {create_access_token({'sub': str(mgr.id)})}"
            }

        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
            timeout=30.0,
        )

    async def asyncTearDown(self) -> None:
        try:
            await self.client.aclose()
        finally:
            app.dependency_overrides.clear()
            manager_module._is_scraper_running = False
            set_telegram_transport(None)
            async with async_session_maker() as s:
                if self.created_run_ids:
                    await s.execute(
                        delete(ScraperRun).where(ScraperRun.id.in_(self.created_run_ids))
                    )
                if self.created_source_keys:
                    await s.execute(
                        delete(ScraperSource).where(
                            ScraperSource.source_key.in_(self.created_source_keys)
                        )
                    )
                if self.created_user_id is not None:
                    await s.execute(delete(User).where(User.id == self.created_user_id))
                await s.commit()
            await engine.dispose()

    async def test_postgres_scraper_source_crud_unique_and_onupdate(self) -> None:
        custom_key = f"pg_test_src_{uuid4().hex[:8]}"
        self.created_source_keys.append(custom_key)

        res_list = await self.client.get(
            "/api/manager/scraper/sources",
            headers=self.auth_headers,
        )
        self.assertEqual(res_list.status_code, 200, res_list.text)
        builtin_items = [item for item in res_list.json() if item["is_builtin"]]
        self.assertGreaterEqual(len(builtin_items), 9)

        with patch("app.services.scraper.fetcher.socket.getaddrinfo", return_value=_PUBLIC_ADDRINFO):
            res_create = await self.client.post(
                "/api/manager/scraper/sources",
                headers=self.auth_headers,
                json={
                    "source_key": custom_key,
                    "display_name": "PG Интеграционная площадка",
                    "catalog_urls": ["https://pg-events.example.ru/catalog/"],
                    "adapter_type": "html_list",
                    "b2b_filter_enabled": True,
                    "russia_online_only": True,
                },
            )
        self.assertEqual(res_create.status_code, 201, res_create.text)
        created = res_create.json()
        self.assertEqual(created["source_key"], custom_key)
        self.assertFalse(created["is_builtin"])
        created_updated_at = datetime.datetime.fromisoformat(created["updated_at"])

        # Дубликат source_key -> 409 Conflict и IntegrityError на уровне PostgreSQL
        with patch("app.services.scraper.fetcher.socket.getaddrinfo", return_value=_PUBLIC_ADDRINFO):
            res_dup = await self.client.post(
                "/api/manager/scraper/sources",
                headers=self.auth_headers,
                json={
                    "source_key": custom_key,
                    "display_name": "Дубликат",
                    "catalog_urls": ["https://pg-events.example.ru/catalog/"],
                },
            )
        self.assertEqual(res_dup.status_code, 409)

        async with async_session_maker() as s:
            s.add(
                ScraperSource(
                    source_key=custom_key,
                    display_name="Direct DB Duplicate",
                    catalog_urls=["https://pg-events.example.ru/"],
                )
            )
            with self.assertRaises(IntegrityError):
                await s.commit()
            await s.rollback()

        # Проверяем реальное обновление updated_at через onupdate=func.now() в PostgreSQL
        await asyncio.sleep(0.05)
        res_patch = await self.client.patch(
            f"/api/manager/scraper/sources/{custom_key}",
            headers=self.auth_headers,
            json={"max_urls_per_run": 17, "is_enabled": False},
        )
        self.assertEqual(res_patch.status_code, 200, res_patch.text)
        patched = res_patch.json()
        self.assertEqual(patched["max_urls_per_run"], 17)
        self.assertFalse(patched["is_enabled"])
        patched_updated_at = datetime.datetime.fromisoformat(patched["updated_at"])
        self.assertGreater(patched_updated_at, created_updated_at)

        # Удаление custom источника и защита builtin
        res_del_builtin = await self.client.delete(
            "/api/manager/scraper/sources/architime",
            headers=self.auth_headers,
        )
        self.assertEqual(res_del_builtin.status_code, 400)

        res_del = await self.client.delete(
            f"/api/manager/scraper/sources/{custom_key}",
            headers=self.auth_headers,
        )
        self.assertEqual(res_del.status_code, 200)
        self.assertTrue(res_del.json()["deleted"])

        async with async_session_maker() as s:
            check_res = await s.execute(
                select(ScraperSource).where(ScraperSource.source_key == custom_key)
            )
            self.assertIsNone(check_res.scalar_one_or_none())

    async def test_postgres_persisted_run_jsonb_dry_run_and_stale_recovery(self) -> None:
        async def _fake_monitoring(
            session,
            *,
            source_key=None,
            max_urls_per_source=None,
            dry_run=False,
            on_source_progress=None,
        ):
            src_log = {
                "source_key": "architime",
                "display_name": "ARCHITIME",
                "adapter_type": "html_list",
                "catalog_urls": ["https://www.architime.ru/lecturexibition.htm"],
                "discovered_total": 4,
                "selected_new_count": 2,
                "events_created": 0 if dry_run else 1,
                "events_updated": 0,
                "rejected_b2c": 1,
                "rejected_geo": 0,
                "rejected_past": 1,
                "errors_count": 0,
                "candidate_urls": ["https://www.architime.ru/activity/2026/test.htm"],
                "saved_events": (
                    []
                    if dry_run
                    else [
                        {
                            "event_id": 777,
                            "title": "PG Тест Форум",
                            "url": "https://www.architime.ru/activity/2026/test.htm",
                            "action": "created",
                            "data_status": "ready",
                            "start_date": "2026-12-10",
                            "city": "Москва",
                        }
                    ]
                ),
                "error": None,
            }
            if on_source_progress:
                await on_source_progress(
                    src_log,
                    {
                        "sources_total": 1,
                        "sources_done": 1,
                        "urls_discovered": 4,
                        "events_created": 0 if dry_run else 1,
                        "events_updated": 0,
                        "rejected_b2c": 1,
                        "rejected_geo": 0,
                        "rejected_past": 1,
                        "errors_count": 0,
                    },
                )
            return ScrapingRunSummary(
                checked_sources=1,
                discovered_urls=4,
                ingested_ready_count=0 if dry_run else 1,
                needs_enrichment_count=0,
                needs_enrichment_titles=[],
                failed_count=0,
                dry_run=dry_run,
                rejected_b2c_count=1,
                rejected_geo_count=0,
                rejected_past_count=1,
                events_created_count=0 if dry_run else 1,
                events_updated_count=0,
                per_source_report=[src_log],
            )

        # 1. Пробный прогон: start_scraper_run_record -> run_persisted_scraper_job -> JSONB source_logs в PG
        async with async_session_maker() as s:
            dry_run_row = await start_scraper_run_record(
                s,
                target_source_key="architime",
                triggered_by="manual_dry_run",
            )
            self.created_run_ids.append(dry_run_row.id)

        with patch.object(
            scraper_pkg,
            "run_customer_sources_monitoring",
            new=AsyncMock(side_effect=_fake_monitoring),
        ):
            summary = await run_persisted_scraper_job(
                dry_run_row.id,
                "architime",
                dry_run=True,
            )

        self.assertIsNotNone(summary)
        self.assertFalse(manager_module._is_scraper_running)

        async with async_session_maker() as s:
            loaded = await s.get(ScraperRun, dry_run_row.id)
            self.assertIsNotNone(loaded)
            assert loaded is not None
            self.assertEqual(loaded.status, "completed")
            self.assertEqual(loaded.triggered_by, "manual_dry_run")
            self.assertEqual(len(loaded.source_logs), 1)
            self.assertEqual(loaded.source_logs[0]["source_key"], "architime")
            dto = ScraperRunDetailOut.model_validate(loaded)
            self.assertTrue(dto.dry_run)

        # Проверяем через реальный API GET /runs/latest
        res_latest = await self.client.get(
            "/api/manager/scraper/runs/latest",
            headers=self.auth_headers,
        )
        self.assertEqual(res_latest.status_code, 200, res_latest.text)
        latest_data = res_latest.json()
        self.assertEqual(latest_data["id"], dry_run_row.id)
        self.assertTrue(latest_data["dry_run"])
        self.assertEqual(latest_data["source_logs"][0]["discovered_total"], 4)

        # 2. Зависание прогона -> recover_stale_scraper_runs переводит в failed в PostgreSQL
        async with async_session_maker() as s:
            stale_row = ScraperRun(
                status="running",
                target_source_key="all",
                triggered_by="manual",
            )
            s.add(stale_row)
            await s.commit()
            await s.refresh(stale_row)
            self.created_run_ids.append(stale_row.id)

            recovered = await recover_stale_scraper_runs(s)
            self.assertGreaterEqual(recovered, 1)

            refreshed = await s.get(ScraperRun, stale_row.id)
            assert refreshed is not None
            self.assertEqual(refreshed.status, "failed")
            self.assertEqual(refreshed.error_message, "Прервано перезапуском сервера")
            self.assertIsNotNone(refreshed.finished_at)
            self.assertFalse(ScraperRunDetailOut.model_validate(refreshed).dry_run)


class TestRagAndDossierCompletenessFixes(unittest.IsolatedAsyncioTestCase):
    """Тесты полноты извлечения PDF, сохранения первоисточников в регламент и RAG по summary/ценам."""

    def test_compact_pdf_preserves_all_pages_when_enabled(self) -> None:
        import pymupdf as fitz

        from app.services.scraper.pdf_reader import extract_relevant_pdf_text_sync

        doc = fitz.open()
        for text in (
            "Page 1 event dates November 25-29 Moscow.",
            "Page 2 general concept and designers overview text line enough to skip ocr.",
            "Page 3 background gallery list with special celebrity names without any tariff words.",
            "Page 4 VIP guests and media partners details and editorial team information.",
        ):
            page = doc.new_page()
            page.insert_text((50, 72), text)
        pdf_bytes = doc.tobytes()
        doc.close()

        default_text, _ = extract_relevant_pdf_text_sync(pdf_bytes)
        self.assertNotIn("celebrity names", default_text)
        self.assertIn("VIP guests", default_text)

        compact_text, _ = extract_relevant_pdf_text_sync(
            pdf_bytes, include_all_if_compact=True
        )
        self.assertIn("celebrity names", compact_text)
        self.assertIn("VIP guests", compact_text)

    async def test_ingest_appends_clean_source_materials_without_schema_org_blob(self) -> None:
        from app.schemas.event_ingestion import EventIngestionSchema

        raw_dossier = (
            "=== КАРТОЧКА АГРЕГАТОРА (https://expomap.ru/expo/test/) ===\n"
            "--- SCHEMA.ORG LD+JSON ---\n"
            '{"@context": "https://schema.org", "@type": "Event", "name": "Test"}\n\n'
            "Краткий анонс на агрегаторе.\n\n"
            "=== PDF-ДОКУМЕНТ (https://org.ru/brochure.pdf) ===\n"
            "Специальный интерьерный журнал WA выпускается российско-китайской командой тиражом 10000 экз. "
            "В выставке принимают участие более 100 компаний, а также VIP-гости и известные дизайнеры интерьеров."
        )
        compressed_schema = EventIngestionSchema(
            canonical_title="Выставка Интерьера 2026",
            event_format="forum",
            city="Москва",
            country="Россия",
            is_online=False,
            start_date=datetime.date(2026, 11, 25),
            end_date=datetime.date(2026, 11, 29),
            summary="Крупная профессиональная выставка дизайна и интерьера в Москве с участием более 100 компаний. "
            * 3,
            themes=["дизайн интерьера"],
            full_regulation_markdown="## Программа\nДеловая программа выставки в Москве.\n\n## Условия\nПо заявке.",
            tariffs=[],
            faq_cache=[],
        )

        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.execute = AsyncMock(
            return_value=MagicMock(scalar=MagicMock(return_value=0))
        )

        with (
            patch(
                "app.services.scraper.ingestion._extract_structured_event_via_llm",
                new=AsyncMock(return_value=compressed_schema),
            ),
            patch.object(
                scraper_pkg, "get_embedding", new=AsyncMock(return_value=[0.1] * 1024)
            ),
            patch.object(
                scraper_pkg, "find_duplicate_event", new=AsyncMock(return_value=None)
            ),
            patch("app.services.scraper.ingestion._sync_event_chunks", new=AsyncMock()),
        ):
            ev = await scraper_pkg.ingest_event_from_text(
                mock_session,
                raw_dossier,
                source_url="https://expomap.ru/expo/test/",
            )

        reg = ev.full_regulation_markdown or ""
        self.assertIn("российско-китайской командой", reg)
        self.assertIn("более 100 компаний", reg)
        self.assertNotIn("SCHEMA.ORG LD+JSON", reg)

    async def test_rag_includes_summary_and_on_request_price_grounding(self) -> None:
        from app.models.models import EventTariff
        from app.services.rag import RAGResponse, ask_regulation_question

        ev = Event(
            id=888,
            canonical_title="Интерьер Салон 2026",
            normalized_title="интерьер салон 2026",
            event_format="exhibition",
            city="Москва",
            is_online=False,
            venue="Гостиный Двор",
            start_date=datetime.date(2026, 11, 25),
            end_date=datetime.date(2026, 11, 29),
            summary="Проект с участием более 100 компаний-производителей мебели и декора.",
            full_regulation_markdown="## Программа\nДеловая программа и экспозиция.",
            themes=["дизайн"],
            source_urls=["https://example.ru"],
            data_status="ready",
        )
        tariff = EventTariff(
            id=12,
            event_id=888,
            tariff_name="Экспонент",
            participation_role="sponsor",
            base_price=None,
            is_vat_included=True,
            included_benefits="Участие со стендом",
        )
        ev.tariffs = [tariff]

        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.get = AsyncMock(
            side_effect=lambda model, pk: ev if model is Event else None
        )
        exec_empty = MagicMock()
        exec_empty.scalars.return_value.first.return_value = None
        exec_empty.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=exec_empty)

        captured_prompts: list[tuple[str, str]] = []

        async def _fake_rag_create(**kwargs):
            msgs = kwargs["messages"]
            sys_txt = msgs[0]["content"]
            usr_txt = msgs[1]["content"]
            captured_prompts.append((sys_txt, usr_txt))
            if "компаний" in usr_txt.lower():
                return RAGResponse(
                    is_answer_found=True,
                    answer_text="В проекте участвуют более 100 компаний-производителей.",
                    source_quote="более 100 компаний-производителей мебели и декора",
                )
            return RAGResponse(
                is_answer_found=True,
                answer_text="Стоимость по тарифу «Экспонент» предоставляется по запросу.",
                source_quote="Базовая стоимость: По запросу",
            )

        mock_rag_client = MagicMock()
        mock_rag_client.chat.completions.create = AsyncMock(side_effect=_fake_rag_create)

        with (
            patch("app.services.rag.settings.LLM_API_KEY", "test-key"),
            patch("app.services.rag.structured_llm_client", new=mock_rag_client),
        ):
            res_count = await ask_regulation_question(
                mock_session, selection_id=1, event_id=888, question_text="Сколько компаний?"
            )
            res_price = await ask_regulation_question(
                mock_session, selection_id=1, event_id=888, question_text="Какая цена?"
            )

        self.assertTrue(res_count.is_answer_found)
        self.assertIn("100 компаний", res_count.answer_text)
        self.assertTrue(res_price.is_answer_found)
        self.assertIn("По запросу", captured_prompts[1][0])
        self.assertIn("более 100 компаний", captured_prompts[0][0])


if __name__ == "__main__":
    unittest.main()
