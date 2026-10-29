import sys
import time
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select, func
from app.core.database import async_session_maker, engine
from app.models.models import Client, Event, EventTariff, Selection, SelectionItem
from app.schemas.manager import ClientQueryExtracted, MatchRequestIn
from app.services.matcher import (
    build_fts_or_query,
    build_tariff_option,
    get_scored_candidates,
    build_bundles,
    run_client_matching_pipeline,
)
from tests.test_d08_d09_d10 import is_postgres_online


class TestD07Matcher(unittest.IsolatedAsyncioTestCase):
    async def asyncTearDown(self) -> None:
        await engine.dispose()

    def test_01_fts_query_builder_and_fallback(self) -> None:
        # 1. Standard Cyrillic & Latin keywords
        p1 = ClientQueryExtracted(
            total_budget_max=300000.0,
            themes_keywords=["КРТ", "строительство и девелопмент", "PropTech-2026!"],
            semantic_search_query="Конференции по КРТ и строительству",
        )
        q1 = build_fts_or_query(p1)
        self.assertIn("КРТ", q1)
        self.assertIn("строительство и девелопмент", q1)
        self.assertIn("PropTech-2026", q1)
        self.assertIn(" OR ", q1)

        # 2. Empty keywords -> falls back to words from semantic_search_query
        p_empty = ClientQueryExtracted(
            total_budget_max=300000.0,
            themes_keywords=[],
            semantic_search_query="Форумы по недвижимости и урбанистике",
        )
        q_empty = build_fts_or_query(p_empty)
        self.assertIn("Форумы", q_empty)
        self.assertIn("недвижимости", q_empty)
        self.assertIn(" OR ", q_empty)

        # 3. Special-char-only keywords and minimal query -> safe fallback
        p_symbols = ClientQueryExtracted(
            total_budget_max=300000.0,
            themes_keywords=["!@#$%", "   ", "a"],
            semantic_search_query="!",
        )
        q_symbols = build_fts_or_query(p_symbols)
        self.assertEqual(q_symbols, "строительство OR девелопмент")

    def test_02_tariff_option_math(self) -> None:
        today = date(2026, 10, 1)

        # 1. Active Early Bird
        t_eb_active = EventTariff(
            id=101,
            event_id=1,
            tariff_name="Делегат Early Bird",
            participation_role="delegate",
            base_price=50000.0,
            early_bird_price=35000.0,
            early_bird_deadline=date(2026, 10, 15),
            included_benefits="Доступ ко всем сессиям",
        )
        opt_active = build_tariff_option(t_eb_active, today)
        self.assertEqual(opt_active.actual_price, 35000.0)
        self.assertEqual(opt_active.base_price, 50000.0)
        self.assertEqual(opt_active.savings, 15000.0)

        # 2. Expired Early Bird
        t_eb_expired = EventTariff(
            id=102,
            event_id=1,
            tariff_name="Делегат Стандарт",
            participation_role="delegate",
            base_price=50000.0,
            early_bird_price=35000.0,
            early_bird_deadline=date(2026, 9, 15),
        )
        opt_expired = build_tariff_option(t_eb_expired, today)
        self.assertEqual(opt_expired.actual_price, 50000.0)
        self.assertEqual(opt_expired.savings, 0.0)

        # 3. Free Tariff (0.0)
        t_free = EventTariff(
            id=103,
            event_id=2,
            tariff_name="Бесплатная регистрация",
            participation_role="delegate",
            base_price=0.0,
            early_bird_price=None,
            early_bird_deadline=None,
        )
        opt_free = build_tariff_option(t_free, today)
        self.assertEqual(opt_free.actual_price, 0.0)
        self.assertEqual(opt_free.base_price, 0.0)
        self.assertEqual(opt_free.savings, 0.0)

        # 4. On Request Tariff (base_price = None)
        t_on_req = EventTariff(
            id=104,
            event_id=3,
            tariff_name="Генеральный партнер",
            participation_role="sponsor",
            base_price=None,
            early_bird_price=None,
            early_bird_deadline=None,
        )
        opt_on_req = build_tariff_option(t_on_req, today)
        self.assertIsNone(opt_on_req.actual_price)
        self.assertIsNone(opt_on_req.base_price)
        self.assertEqual(opt_on_req.savings, 0.0)

    @unittest.skipUnless(is_postgres_online(), "Требуется запущенный контейнер PostgreSQL")
    async def test_03_build_bundles_performance_and_diversification(self) -> None:
        today = date(2026, 9, 1)
        profile = ClientQueryExtracted(
            cities=["Москва", "Санкт-Петербург"],
            include_online=True,
            date_from=date(2026, 9, 1),
            date_to=date(2026, 12, 31),
            total_budget_max=400000.0,
            target_events_count=3,
            preferred_formats=["forum", "conference", "session"],
            required_roles=["delegate", "speaker"],
            min_speaker_events=1,
            themes_keywords=["строительство", "девелопмент", "недвижимость", "бизнес"],
            semantic_search_query="Форумы и конференции по строительству, девелопменту и бизнес-нетворкингу",
        )

        async with async_session_maker() as session:
            candidates = await get_scored_candidates(session, profile, today)
            self.assertGreaterEqual(len(candidates), 3, "Expected at least 3 RRF candidates from seeded DB")

            t0 = time.perf_counter()
            variants, bonus_pairs = build_bundles(candidates, profile)
            elapsed_ms = (time.perf_counter() - t0) * 1000.0

            # SLA check: < 15 ms
            self.assertLess(elapsed_ms, 15.0, f"build_bundles exceeded 15ms SLA: {elapsed_ms:.3f} ms")
            self.assertGreaterEqual(len(variants), 1)

            # Check Variant 1 speaker requirement & budget
            v1 = variants[0]
            self.assertLessEqual(v1.total_actual_price, profile.total_budget_max)
            v1_speakers = sum(1 for t in v1.chosen_tariffs if t.participation_role == "speaker")
            self.assertGreaterEqual(v1_speakers, 1, "Variant 1 must satisfy min_speaker_events=1")
            self.assertTrue(v1.roles_strictly_matched)
            self.assertFalse(v1.has_date_conflict)

            # Check diversification if 2 variants are returned
            if len(variants) == 2:
                v2 = variants[1]
                v1_ids = {c.event.id for c in v1.candidates}
                v2_ids = {c.event.id for c in v2.candidates}
                self.assertNotEqual(v1_ids, v2_ids, "Variant 1 and Variant 2 must have different event sets")

            # Check bonus items have base_price is None
            self.assertGreaterEqual(len(bonus_pairs), 1, "Expected at least 1 bonus on-request item")
            for _, tar in bonus_pairs:
                self.assertIsNone(tar.base_price)

    @unittest.skipUnless(is_postgres_online(), "Требуется запущенный контейнер PostgreSQL")
    async def test_04_full_matching_pipeline_and_db_persistence(self) -> None:
        async with async_session_maker() as session:
            client_res = await session.execute(select(Client).order_by(Client.id.asc()).limit(1))
            client = client_res.scalars().first()
            self.assertIsNotNone(client, "Seeded client must exist in DB")

            profile = ClientQueryExtracted(
                cities=["Москва", "Санкт-Петербург"],
                include_online=True,
                date_from=date(2026, 9, 1),
                date_to=date(2026, 12, 31),
                total_budget_max=400000.0,
                target_events_count=3,
                preferred_formats=["forum", "conference"],
                required_roles=["delegate", "speaker"],
                min_speaker_events=1,
                themes_keywords=["девелопмент", "строительство", "нетворкинг"],
                semantic_search_query="Конференции по строительству, девелопменту и нетворкингу",
            )
            payload = MatchRequestIn(
                raw_manager_notes="Подбор 3 мероприятий для ГК Пионер на осень-зиму 2026, бюджет 400 тыс. руб., 1 спикер.",
                override_profile=profile,
            )

            result = await run_client_matching_pipeline(
                session=session,
                client_id=client.id,
                payload=payload,
            )

            self.assertIsNotNone(result.selection_id)
            self.assertEqual(result.client_id, client.id)
            self.assertGreaterEqual(len(result.bundle_variants), 1)
            self.assertTrue(len(result.generated_pitch_text) > 20)

            # Verify Selection and SelectionItem rows in DB
            sel_row = await session.get(Selection, result.selection_id)
            self.assertIsNotNone(sel_row)
            self.assertEqual(sel_row.status, "draft")

            cnt_res = await session.execute(
                select(func.count(SelectionItem.id)).where(SelectionItem.selection_id == result.selection_id)
            )
            saved_items_count = cnt_res.scalar_one()
            expected_count = sum(len(v.items) for v in result.bundle_variants)
            self.assertEqual(saved_items_count, expected_count)


if __name__ == "__main__":
    unittest.main()
