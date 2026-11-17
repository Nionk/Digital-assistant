import datetime
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import httpx
from sqlalchemy import delete, select

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.database import async_session_maker, engine
from app.core.security import create_access_token
from app.main import app
from app.models.models import Event, ScraperSeenUrl, User
from app.services.manager_workspace import list_catalog_events
from app.services.monitoring_job import archive_past_events
from app.services.scraper import (
    CollectedEventDossier,
    CustomerSourceConfig,
    DiscoveredCandidate,
    EventRejectedError,
    ingest_event_from_text,
)
from app.services.scraper.ingestion import _get_app_today
from app.services.scraper.monitoring import (
    _compute_dossier_hash,
    _ingest_source_candidates,
    _load_seen_urls_map,
    _should_skip_url,
    _url_lookup_key,
)


class ArchiveHashPreDedupTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.created_event_ids: list[int] = []
        self.created_seen_urls: list[str] = []
        self.token = create_access_token({"sub": "1"})
        self.auth_headers = {"Authorization": f"Bearer {self.token}"}

        async with async_session_maker() as s:
            u = await s.get(User, 1)
            if u is None:
                s.add(
                    User(
                        id=1,
                        email="manager@test.local",
                        password_hash="stub",
                        full_name="Test Manager",
                    )
                )
                await s.commit()

    async def asyncTearDown(self) -> None:
        async with async_session_maker() as s:
            if self.created_seen_urls:
                await s.execute(
                    delete(ScraperSeenUrl).where(ScraperSeenUrl.url.in_(self.created_seen_urls))
                )
            if self.created_event_ids:
                await s.execute(
                    delete(Event).where(Event.id.in_(self.created_event_ids))
                )
            await s.commit()
        await engine.dispose()

    async def test_archive_event_hides_from_catalog_and_blocks_resurrection(self) -> None:
        unique_url = f"https://example.com/events/archive-{uuid4().hex}"
        url_key = _url_lookup_key(unique_url)
        self.created_seen_urls.append(url_key)
        today = _get_app_today()

        async with async_session_maker() as s:
            ev = Event(
                canonical_title=f"Архивный Форум Строй {uuid4().hex[:8]}",
                normalized_title="архивный форум строй",
                event_format="forum",
                city="Москва",
                is_online=False,
                start_date=today + datetime.timedelta(days=20),
                end_date=today + datetime.timedelta(days=21),
                summary="Краткое описание форума для проверки архивации.",
                full_regulation_markdown="Регламент мероприятия.",
                themes=["строительство"],
                source_urls=[unique_url],
                data_status="needs_enrichment",
                is_active=False,
            )
            s.add(ev)
            await s.commit()
            await s.refresh(ev)
            self.created_event_ids.append(ev.id)
            ev_id = ev.id

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            resp = await client.post(
                f"/api/manager/events/{ev_id}/archive",
                headers=self.auth_headers,
            )
            self.assertEqual(resp.status_code, 200)
            body = resp.json()
            self.assertEqual(body["event_id"], ev_id)
            self.assertEqual(body["status"], "archived")

        async with async_session_maker() as s:
            loaded = await s.get(Event, ev_id)
            assert loaded is not None
            self.assertFalse(loaded.is_active)
            self.assertEqual(loaded.data_status, "archived")

            catalog = await list_catalog_events(s)
            self.assertNotIn(ev_id, {item.event_id for item in catalog.events})

            seen_res = await s.execute(
                select(ScraperSeenUrl).where(ScraperSeenUrl.url == url_key)
            )
            seen_row = seen_res.scalar_one_or_none()
            assert seen_row is not None
            self.assertEqual(seen_row.outcome, "ignored")
            self.assertEqual(seen_row.event_id, ev_id)

            seen_map = await _load_seen_urls_map(s)
            self.assertTrue(_should_skip_url(url_key, seen_map, set()))

            # Защита от зомби-возврата с другого агрегатора через find_duplicate_event
            fake_schema = AsyncMock()
            fake_schema.canonical_title = loaded.canonical_title
            fake_schema.start_date = loaded.start_date
            fake_schema.end_date = loaded.end_date
            fake_schema.city = loaded.city
            fake_schema.is_online = False
            fake_schema.country = "Россия"
            fake_schema.full_regulation_markdown = "Подробный текст регламента" * 20
            fake_schema.summary = "Описание" * 20
            fake_schema.themes = ["строительство"]
            fake_schema.tariffs = []
            fake_schema.missing_data_warnings = []

            with (
                patch(
                    "app.services.scraper.ingestion._extract_structured_event_via_llm",
                    new=AsyncMock(return_value=fake_schema),
                ),
                patch(
                    "app.services.scraper.get_embedding",
                    new=AsyncMock(return_value=[0.0] * 1024),
                ),
            ):
                with self.assertRaises(EventRejectedError) as ctx:
                    await ingest_event_from_text(
                        s,
                        "Текст с другого агрегатора",
                        source_url="https://another-agg.ru/event/999",
                        reject_past=True,
                    )
                self.assertEqual(ctx.exception.outcome, "ignored")

    async def test_archive_past_events_archives_only_expired(self) -> None:
        today = _get_app_today()
        async with async_session_maker() as s:
            past_ev = Event(
                canonical_title=f"Прошедший Форум {uuid4().hex[:8]}",
                normalized_title="прошедший форум",
                event_format="forum",
                city="Москва",
                is_online=False,
                start_date=today - datetime.timedelta(days=10),
                end_date=today - datetime.timedelta(days=5),
                summary="Описание прошедшего события.",
                themes=[],
                source_urls=[],
                data_status="ready",
                is_active=True,
            )
            future_ev = Event(
                canonical_title=f"Будущий Форум {uuid4().hex[:8]}",
                normalized_title="будущий форум",
                event_format="forum",
                city="Москва",
                is_online=False,
                start_date=today + datetime.timedelta(days=10),
                end_date=today + datetime.timedelta(days=11),
                summary="Описание будущего события.",
                themes=[],
                source_urls=[],
                data_status="ready",
                is_active=True,
            )
            s.add_all([past_ev, future_ev])
            await s.commit()
            await s.refresh(past_ev)
            await s.refresh(future_ev)
            self.created_event_ids.extend([past_ev.id, future_ev.id])

            archived_cnt = await archive_past_events(s, grace_days=1)
            self.assertGreaterEqual(archived_cnt, 1)

            await s.refresh(past_ev)
            await s.refresh(future_ev)
            self.assertFalse(past_ev.is_active)
            self.assertEqual(past_ev.data_status, "archived")
            self.assertTrue(future_ev.is_active)
            self.assertEqual(future_ev.data_status, "ready")

    async def test_content_hash_skips_llm_and_ocr_when_unchanged(self) -> None:
        unique_url = f"https://example.com/events/hash-{uuid4().hex}"
        url_key = _url_lookup_key(unique_url)
        self.created_seen_urls.append(url_key)

        dossier = CollectedEventDossier(
            dossier_text="=== ДАННЫЕ С АГРЕГАТОРА ===\nТекст программы без тарифов.",
            source_urls=[unique_url, f"{unique_url}/program.pdf"],
        )
        initial_hash = _compute_dossier_hash([dossier])

        async with async_session_maker() as s:
            s.add(
                ScraperSeenUrl(
                    url=url_key,
                    source_key="test_src",
                    outcome="ingested_needs_enrichment",
                    event_id=None,
                    recheck_attempts=0,
                    content_hash=initial_hash,
                )
            )
            await s.commit()

            seen_map = await _load_seen_urls_map(s)
            src = CustomerSourceConfig(
                source_key="test_src",
                display_name="Test Source",
                catalog_urls=("https://example.com/catalog",),
            )
            ingest_mock = AsyncMock()
            ocr_mock = AsyncMock()
            ocr_mock.extract_text_from_images = AsyncMock(return_value="")

            with (
                patch(
                    "app.services.scraper.collect_event_dossiers",
                    new=AsyncMock(return_value=[dossier]),
                ),
                patch("app.services.scraper.ingest_event_from_text", new=ingest_mock),
            ):
                await _ingest_source_candidates(
                    s,
                    src,
                    [DiscoveredCandidate(url=unique_url, source_key="test_src")],
                    set(),
                    seen_map=seen_map,
                    vision_ocr=ocr_mock,
                )

            self.assertEqual(ingest_mock.call_count, 0)
            self.assertEqual(ocr_mock.extract_text_from_images.call_count, 0)
            self.assertEqual(seen_map[url_key].recheck_attempts, 1)

    async def test_pre_dedup_skips_crawler_and_llm_for_ready_event(self) -> None:
        today = _get_app_today()
        unique_suffix = uuid4().hex[:8]
        ready_title = f"Международный Форум Девелоперов {unique_suffix}"
        cand_url = f"https://other-aggregator.ru/events/{uuid4().hex}"
        url_key = _url_lookup_key(cand_url)
        self.created_seen_urls.append(url_key)

        async with async_session_maker() as s:
            ev = Event(
                canonical_title=ready_title,
                normalized_title=ready_title.lower(),
                event_format="forum",
                city="Москва",
                is_online=False,
                start_date=today + datetime.timedelta(days=15),
                end_date=today + datetime.timedelta(days=16),
                summary="Готовое событие в БД." * 20,
                themes=["девелопмент"],
                source_urls=[f"https://primary.ru/ev/{unique_suffix}"],
                data_status="ready",
                is_active=True,
            )
            s.add(ev)
            await s.commit()
            await s.refresh(ev)
            self.created_event_ids.append(ev.id)
            ready_id = ev.id

            src = CustomerSourceConfig(
                source_key="test_src",
                display_name="Test Source",
                catalog_urls=("https://other-aggregator.ru/catalog",),
            )
            crawler_mock = AsyncMock()
            ingest_mock = AsyncMock()
            seen_map: dict = {}
            known_urls: set[str] = set()

            with (
                patch("app.services.scraper.collect_event_dossiers", new=crawler_mock),
                patch("app.services.scraper.ingest_event_from_text", new=ingest_mock),
            ):
                await _ingest_source_candidates(
                    s,
                    src,
                    [
                        DiscoveredCandidate(
                            url=cand_url,
                            source_key="test_src",
                            title=f"{ready_title} 2026",
                        )
                    ],
                    known_urls,
                    seen_map=seen_map,
                )

            self.assertEqual(crawler_mock.call_count, 0)
            self.assertEqual(ingest_mock.call_count, 0)
            self.assertIn(url_key, known_urls)
            self.assertEqual(seen_map[url_key].outcome, "ingested_ready")

            seen_res = await s.execute(
                select(ScraperSeenUrl).where(ScraperSeenUrl.url == url_key)
            )
            seen_row = seen_res.scalar_one_or_none()
            assert seen_row is not None
            self.assertEqual(seen_row.event_id, ready_id)

    async def test_refresh_event_endpoint_hash_skip_and_force(self) -> None:
        today = _get_app_today()
        unique_url = f"https://example.com/events/refresh-{uuid4().hex}"
        url_key = _url_lookup_key(unique_url)
        self.created_seen_urls.append(url_key)

        dossier = CollectedEventDossier(
            dossier_text="=== ДАННЫЕ С АГРЕГАТОРА ===\nАктуальная программа форума.",
            source_urls=[unique_url],
        )
        content_hash = _compute_dossier_hash([dossier])

        async with async_session_maker() as s:
            ev = Event(
                canonical_title=f"Форум Обновления {uuid4().hex[:8]}",
                normalized_title="форум обновления",
                event_format="forum",
                city="Москва",
                is_online=False,
                start_date=today + datetime.timedelta(days=30),
                end_date=today + datetime.timedelta(days=31),
                summary="Описание.",
                themes=[],
                source_urls=[unique_url],
                data_status="ready",
                is_active=True,
            )
            s.add(ev)
            await s.commit()
            await s.refresh(ev)
            self.created_event_ids.append(ev.id)
            ev_id = ev.id

            s.add(
                ScraperSeenUrl(
                    url=url_key,
                    source_key="manual",
                    outcome="ingested_ready",
                    event_id=ev_id,
                    content_hash=content_hash,
                )
            )
            await s.commit()

        ingest_mock = AsyncMock()
        with (
            patch("app.api.manager.validate_safe_public_url", new=AsyncMock()),
            patch("app.api.manager.collect_event_dossier", new=AsyncMock(return_value=dossier)),
            patch("app.api.manager.ingest_event_from_text", new=ingest_mock),
        ):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://testserver",
            ) as client:
                r1 = await client.post(
                    f"/api/manager/events/{ev_id}/refresh",
                    json={"force": False},
                    headers=self.auth_headers,
                )
                self.assertEqual(r1.status_code, 200)
                self.assertIn(r1.json()["status"], ("queued", "running"))

                import asyncio
                s1_body: dict = {}
                for _ in range(40):
                    s1 = await client.get(
                        f"/api/manager/events/{ev_id}/refresh/status",
                        headers=self.auth_headers,
                    )
                    self.assertEqual(s1.status_code, 200)
                    s1_body = s1.json()
                    if s1_body["status"] in ("completed", "failed"):
                        break
                    await asyncio.sleep(0.05)

                self.assertEqual(s1_body.get("status"), "completed")
                self.assertFalse(s1_body.get("updated"))
                self.assertEqual(ingest_mock.call_count, 0)

                async with async_session_maker() as s2:
                    loaded_ev = await s2.get(Event, ev_id)
                ingest_mock.return_value = loaded_ev

                r2 = await client.post(
                    f"/api/manager/events/{ev_id}/refresh",
                    json={"force": True},
                    headers=self.auth_headers,
                )
                self.assertEqual(r2.status_code, 200)
                self.assertIn(r2.json()["status"], ("queued", "running"))

                s2_body: dict = {}
                for _ in range(40):
                    s2_resp = await client.get(
                        f"/api/manager/events/{ev_id}/refresh/status",
                        headers=self.auth_headers,
                    )
                    self.assertEqual(s2_resp.status_code, 200)
                    s2_body = s2_resp.json()
                    if s2_body["status"] in ("completed", "failed"):
                        break
                    await asyncio.sleep(0.05)

                self.assertEqual(s2_body.get("status"), "completed")
                self.assertTrue(s2_body.get("updated"))
                self.assertEqual(ingest_mock.call_count, 1)
