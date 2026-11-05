import sys
import time
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import settings
from app.core.database import async_session_maker, engine
from app.models.models import Client, Event, EventTariff, Selection, SelectionItem
from app.schemas.manager import ClientQueryExtracted, MatchRequestIn, TariffOptionOut
from app.services.matcher import (
    ScoredEventCandidate,
    build_bundles,
    build_fts_or_query,
    build_tariff_option,
    get_scored_candidates,
    run_client_matching_pipeline,
)
from sqlalchemy import func, select
from tests.test_d08_d09_d10 import is_postgres_online


class TestD07Matcher(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._emb_patcher = patch(
            "app.services.matcher.get_embedding",
            return_value=[1.0] + [0.0] * (settings.EMBEDDING_DIM - 1),
        )
        self._emb_patcher.start()

    async def asyncTearDown(self) -> None:
        self._emb_patcher.stop()
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

        # 3. Special-char-only keywords and minimal query -> safe domain-agnostic fallback
        p_symbols = ClientQueryExtracted(
            total_budget_max=300000.0,
            themes_keywords=["!@#$%", "   ", "a"],
            semantic_search_query="!",
        )
        q_symbols = build_fts_or_query(p_symbols)
        self.assertEqual(q_symbols, "мероприятие OR конференция OR форум")

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

    def test_02b_combinatorial_bundle_invariants_unit(self) -> None:
        """Автономная проверка инвариантов build_bundles без СУБД (роли, накладки дат, +10% бюджет)."""
        e1 = Event(
            id=1,
            canonical_title="Форум КРТ 1",
            city="Москва",
            is_online=False,
            start_date=date(2026, 11, 10),
            end_date=date(2026, 11, 11),
        )
        e2_conflict = Event(
            id=2,
            canonical_title="Конференция КРТ 2 (Конфликт дат)",
            city="Санкт-Петербург",
            is_online=False,
            start_date=date(2026, 11, 11),
            end_date=date(2026, 11, 12),
        )
        e3_ok = Event(
            id=3,
            canonical_title="Саммит Девелопмент 3",
            city="Москва",
            is_online=False,
            start_date=date(2026, 11, 20),
            end_date=date(2026, 11, 21),
        )

        t_del = TariffOptionOut(
            tariff_id=11,
            tariff_name="Делегат",
            participation_role="delegate",
            base_price=50000.0,
            actual_price=50000.0,
            savings=0.0,
        )
        t_spk = TariffOptionOut(
            tariff_id=12,
            tariff_name="Спикер",
            participation_role="speaker",
            base_price=120000.0,
            actual_price=120000.0,
            savings=0.0,
        )

        # Кандидаты, у которых есть ТОЛЬКО делегатский тариф (нет спикера и нет спонсора)
        c1_del_only = ScoredEventCandidate(
            event=e1, rrf_score=0.03, all_tariffs=[t_del], priced_tariffs=[t_del], on_request_tariffs=[]
        )
        c3_del_only = ScoredEventCandidate(
            event=e3_ok, rrf_score=0.025, all_tariffs=[t_del], priced_tariffs=[t_del], on_request_tariffs=[]
        )

        # 1. Запрет подмены роли спикера на делегата при min_speaker_events=1
        prof_need_speaker = ClientQueryExtracted(
            cities=["Москва"],
            include_online=True,
            total_budget_max=300000.0,
            target_events_count=2,
            required_roles=["speaker", "delegate"],
            min_speaker_events=1,
            themes_keywords=["КРТ"],
            semantic_search_query="КРТ",
        )
        variants_no_spk, _ = build_bundles([c1_del_only, c3_del_only], prof_need_speaker)
        self.assertEqual(len(variants_no_spk), 0, "Must not silently substitute speaker slot with delegate tariff")

        # 2. Когда есть спикерский тариф и второй кандидат конфликтует по датам — конфликт отсекается
        c1_with_spk = ScoredEventCandidate(
            event=e1,
            rrf_score=0.032,
            all_tariffs=[t_del, t_spk],
            priced_tariffs=[t_del, t_spk],
            on_request_tariffs=[],
        )
        c2_conflict_cand = ScoredEventCandidate(
            event=e2_conflict,
            rrf_score=0.031,
            all_tariffs=[t_del],
            priced_tariffs=[t_del],
            on_request_tariffs=[],
        )
        variants_valid, _ = build_bundles([c1_with_spk, c2_conflict_cand, c3_del_only], prof_need_speaker)
        self.assertGreaterEqual(len(variants_valid), 1)
        v1 = variants_valid[0]
        v1_ids = {c.event.id for c in v1.candidates}
        self.assertEqual(v1_ids, {1, 3}, "Event #2 with overlapping dates must be excluded from bundle of size 2")
        self.assertEqual(v1.matched_speaker_count, 1)
        self.assertEqual(v1.total_actual_price, 170000.0)

        # 3. Проверка допуска +10% бюджета (170 000 ₽ при бюджете 160 000 ₽ укладывается в 160k * 1.10 = 176k)
        prof_tight_budget = ClientQueryExtracted(
            cities=["Москва"],
            include_online=True,
            total_budget_max=160000.0,
            target_events_count=2,
            required_roles=["speaker", "delegate"],
            min_speaker_events=1,
            themes_keywords=["КРТ"],
            semantic_search_query="КРТ",
        )
        variants_tol, _ = build_bundles([c1_with_spk, c3_del_only], prof_tight_budget)
        # При бюджете 160к строгий пакет размера K=1 (c1_with_spk за 120к) укладывается строго (<=160к),
        # а пакет размера K=2 (170к) попадает в +10% допуск (<=176к) как второй вариант
        self.assertEqual(len(variants_tol), 2)
        self.assertTrue(any(v.is_over_budget_tolerance for v in variants_tol))

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
            # [AUDIT-TIMEBOMB]: Жесткий тайминг-ассерт < 15.0 мс на выполнение build_bundles делает тест нестабильным (flaky) при запуске на нагруженном CI-раннере (в BENCHMARK_RESULTS.md p95 уже составляет 15.13 мс, max 15.90 мс).
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
