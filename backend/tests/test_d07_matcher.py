import sys
import time
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import func, select

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
from app.services.matcher.candidates import _calculate_domain_bonus
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
        e4_alt = Event(
            id=4,
            canonical_title="Форум Урбанистика 4",
            city="Москва",
            is_online=False,
            start_date=date(2026, 11, 25),
            end_date=date(2026, 11, 26),
        )
        c4_with_spk = ScoredEventCandidate(
            event=e4_alt,
            rrf_score=0.022,
            all_tariffs=[t_spk],
            priced_tariffs=[t_spk],
            on_request_tariffs=[],
        )
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
        variants_tol, _ = build_bundles([c1_with_spk, c3_del_only, c4_with_spk], prof_tight_budget)
        # Полноразмерный пакет K=2 (170к) выбирается из +10% допуска (<=176к) как Вариант 1,
        # а Вариант 2 не является строгим подмножеством событий Варианта 1
        self.assertEqual(len(variants_tol), 2)
        self.assertTrue(variants_tol[0].is_over_budget_tolerance)
        self.assertEqual(len(variants_tol[0].candidates), 2)
        v1_tol_ids = {c.event.id for c in variants_tol[0].candidates}
        v2_tol_ids = {c.event.id for c in variants_tol[1].candidates}
        self.assertFalse(v2_tol_ids < v1_tol_ids)

    async def test_02c_thematic_relevance_and_synonym_fallback_unit(self) -> None:
        """Проверка приоритета тематической релевантности над шумом vec_distance и сохранения синонимов."""
        ev_bim = Event(
            id=101,
            canonical_title="Форум строительства и BIM",
            event_format="forum",
            city="Санкт-Петербург",
            is_online=False,
            start_date=date(2026, 11, 25),
            end_date=date(2026, 11, 25),
            themes=["строительство", "BIM", "цифровизация"],
            summary="Отраслевой форум по цифровизации стройки и внедрению BIM.",
        )
        ev_re_digital = Event(
            id=102,
            canonical_title="Недвижимость и капитал",
            event_format="conference",
            city="Москва",
            is_online=False,
            start_date=date(2026, 12, 10),
            end_date=date(2026, 12, 10),
            themes=["недвижимость", "девелопмент", "цифровые решения"],
            summary="Конференция для девелоперов и инвесторов.",
        )
        ev_finance_offtopic = Event(
            id=103,
            canonical_title="Финансовый директор 2026",
            event_format="conference",
            city="Москва",
            is_online=False,
            start_date=date(2026, 11, 20),
            end_date=date(2026, 11, 20),
            themes=["финансы", "финансовые директора", "IPO", "ERP"],
            summary="Премия для финансовых директоров.",
        )

        profile = ClientQueryExtracted(
            cities=["Москва"],
            include_online=True,
            total_budget_max=350000.0,
            target_events_count=2,
            preferred_formats=["conference"],
            required_roles=["delegate", "speaker"],
            min_speaker_events=1,
            themes_keywords=["цифровизация", "стройка", "BIM"],
            semantic_search_query="Мероприятия по цифровизации стройки и BIM",
        )

        # 1. Тематически релевантный кандидат с пересечением тегов всегда обходит далёкий оффтоп,
        # даже если оффтоп имеет более высокий базовый векторный ранг + совпадение города и формата.
        bonus_bim = _calculate_domain_bonus(ev_bim, profile)
        bonus_re = _calculate_domain_bonus(ev_re_digital, profile)
        bonus_fin = _calculate_domain_bonus(ev_finance_offtopic, profile)
        self.assertGreater(0.0145 + bonus_bim, 0.0164 + bonus_fin)
        self.assertGreater(0.0156 + bonus_re, 0.0164 + bonus_fin)

        t_del = TariffOptionOut(
            tariff_id=1,
            tariff_name="Делегат",
            participation_role="delegate",
            base_price=50000.0,
            actual_price=50000.0,
            savings=0.0,
        )
        tariffs_map = {101: [t_del], 102: [t_del], 103: [t_del]}

        # 2. При наличии тематически релевантных кандидатов явный оффтоп отсеивается
        async def _fake_rrf(*_args, **_kwargs):
            return [(ev_finance_offtopic, 0.016393), (ev_re_digital, 0.015625), (ev_bim, 0.031500)]

        async def _fake_tariffs(*_args, **_kwargs):
            return tariffs_map

        with (
            patch("app.services.matcher.fetch_hybrid_rrf_candidates", side_effect=_fake_rrf),
            patch("app.services.matcher.candidates._load_tariffs_by_event", side_effect=_fake_tariffs),
        ):
            scored = await get_scored_candidates(None, profile, date(2026, 11, 16))  # type: ignore[arg-type]

        scored_ids = [c.event.id for c in scored]
        self.assertIn(101, scored_ids)
        self.assertIn(102, scored_ids)
        self.assertNotIn(103, scored_ids)
        self.assertEqual(scored_ids[0], 101)

        # 3. Если запрос сформулирован синонимами и 0 кандидатов совпали лексически/FTS
        # (только векторные RRF-ранги <= 1/61), векторные кандидаты НЕ отбрасываются
        async def _fake_rrf_vector_only(*_args, **_kwargs):
            return [(ev_finance_offtopic, 0.016393), (ev_re_digital, 0.016129), (ev_bim, 0.015873)]

        synonym_profile = ClientQueryExtracted(
            cities=["Москва"],
            include_online=True,
            total_budget_max=350000.0,
            target_events_count=2,
            themes_keywords=["градостроительная политика", "умные здания"],
            semantic_search_query="Конференции по градостроительной политике и умным зданиям",
        )
        with (
            patch("app.services.matcher.fetch_hybrid_rrf_candidates", side_effect=_fake_rrf_vector_only),
            patch("app.services.matcher.candidates._load_tariffs_by_event", side_effect=_fake_tariffs),
        ):
            synonym_scored = await get_scored_candidates(None, synonym_profile, date(2026, 11, 16))  # type: ignore[arg-type]

        self.assertEqual(len(synonym_scored), 3)

    def test_02d_bonus_on_request_ordering_unit(self) -> None:
        """Бонусный слот сортируется строго по релевантности, а цена 'По запросу' не подменяет платные пакеты."""
        ev_paid = Event(
            id=201,
            canonical_title="Недвижимость и капитал",
            city="Москва",
            is_online=False,
            start_date=date(2026, 12, 10),
            end_date=date(2026, 12, 10),
        )
        ev_nisf = Event(
            id=202,
            canonical_title="НИСФ 2026",
            city="Москва",
            is_online=False,
            start_date=date(2026, 11, 25),
            end_date=date(2026, 11, 25),
        )
        ev_qube = Event(
            id=203,
            canonical_title="QUBE EXPO 2026",
            city="Москва",
            is_online=False,
            start_date=date(2026, 12, 1),
            end_date=date(2026, 12, 3),
        )
        ev_other_on_req = Event(
            id=204,
            canonical_title="Случайный митап",
            city="Москва",
            is_online=False,
            start_date=date(2026, 12, 5),
            end_date=date(2026, 12, 5),
        )

        t_paid_spk = TariffOptionOut(
            tariff_id=1,
            tariff_name="Спикер",
            participation_role="speaker",
            base_price=25000.0,
            actual_price=25000.0,
            savings=0.0,
        )
        t_req_spk = TariffOptionOut(
            tariff_id=2,
            tariff_name="Спикер (по запросу)",
            participation_role="speaker",
            base_price=None,
            actual_price=None,
            savings=0.0,
        )
        t_req_del = TariffOptionOut(
            tariff_id=3,
            tariff_name="Делегат (по запросу)",
            participation_role="delegate",
            base_price=None,
            actual_price=None,
            savings=0.0,
        )

        # Намеренно передаем кандидатов в неотсортированном порядке
        cands = [
            ScoredEventCandidate(
                event=ev_other_on_req, rrf_score=0.015, all_tariffs=[t_req_del], priced_tariffs=[], on_request_tariffs=[t_req_del]
            ),
            ScoredEventCandidate(
                event=ev_paid, rrf_score=0.036, all_tariffs=[t_paid_spk], priced_tariffs=[t_paid_spk], on_request_tariffs=[]
            ),
            ScoredEventCandidate(
                event=ev_qube, rrf_score=0.097, all_tariffs=[t_req_del], priced_tariffs=[], on_request_tariffs=[t_req_del]
            ),
            ScoredEventCandidate(
                event=ev_nisf, rrf_score=0.105, all_tariffs=[t_req_del, t_req_spk], priced_tariffs=[], on_request_tariffs=[t_req_del, t_req_spk]
            ),
        ]
        profile = ClientQueryExtracted(
            cities=["Москва"],
            include_online=True,
            total_budget_max=350000.0,
            target_events_count=2,
            required_roles=["delegate", "speaker"],
            min_speaker_events=1,
            themes_keywords=["цифровизация", "стройка", "BIM"],
            semantic_search_query="цифровизация стройки и BIM",
        )

        variants, bonus_pairs = build_bundles(cands, profile)
        self.assertEqual(len(variants), 1)
        self.assertEqual(variants[0].total_actual_price, 25000.0)
        self.assertEqual([c.event.id for c, _ in bonus_pairs[:2]], [202, 203])
        self.assertEqual(bonus_pairs[0][1].participation_role, "speaker")

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
