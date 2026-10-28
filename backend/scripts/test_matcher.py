import asyncio
import sys
import time
import io
from pathlib import Path
from datetime import date

# Force UTF-8 output on Windows consoles
if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select, func
from app.core.database import async_session_maker, engine
from app.models.models import Client, Selection, SelectionItem
from app.schemas.manager import ClientQueryExtracted, MatchRequestIn
from app.services.matcher import (
    get_scored_candidates,
    build_bundles,
    run_client_matching_pipeline,
)


async def run_tests() -> None:
    print("🚀 [Test Matcher] Starting standalone verification of Hybrid RRF & Combinatorial Bundle Builder...\n")

    async with async_session_maker() as db:
        # Fetch seeded Client 1 (ГК "Пионер")
        res = await db.execute(select(Client).order_by(Client.id.asc()).limit(1))
        client = res.scalars().first()
        if not client:
            print("❌ Error: No clients found in database! Run seed_db.py first.")
            sys.exit(1)

        print(f"👤 Found Client: {client.company_name} (ID: {client.id})")
        today = date.today()

        # =========================================================================
        # Scenario 1: Classic Request (Budget 400k, K=3, 1 Speaker)
        # =========================================================================
        print("\n------------------------------------------------------------")
        print("🧪 SCENARIO 1: Classic Request (Budget 400,000 ₽, K=3, 1 Speaker)")
        print("------------------------------------------------------------")
        profile_1 = ClientQueryExtracted(
            cities=["Москва", "Санкт-Петербург"],
            include_online=True,
            date_from=date(2026, 9, 1),
            date_to=date(2026, 12, 31),
            total_budget_max=400000.0,
            target_events_count=3,
            preferred_formats=["forum", "conference", "session", "roundtable", "business_breakfast"],
            required_roles=["delegate", "speaker"],
            min_speaker_events=1,
            themes_keywords=["девелопмент", "строительство", "недвижимость", "бизнес", "нетворкинг"],
            semantic_search_query="Конференции и форумы по девелопменту, строительству, недвижимости и бизнес-нетворкингу для застройщика",
        )
        payload_1 = MatchRequestIn(
            raw_manager_notes=(
                "Созвонились с ГК Пионер. Ищут на осень-зиму 2026 в Москве или СПб 3 мероприятия по "
                "девелопменту, строительству и бизнес-нетворкингу. Хотя бы на одном хотят выступить спикером. "
                "Общий бюджет на всё — 400 000 руб."
            ),
            override_profile=profile_1,
        )

        response_1 = await run_client_matching_pipeline(
            session=db,
            client_id=client.id,
            payload=payload_1,
        )

        print(f"📝 Selection ID persisted: {response_1.selection_id}")
        print(f"💬 Executive Pitch:\n   {response_1.generated_pitch_text}\n")
        assert len(response_1.bundle_variants) >= 1, "Expected at least 1 bundle variant!"

        for variant in response_1.bundle_variants:
            print(
                f"📦 Variant #{variant.bundle_group}: {variant.bundle_title} "
                f"| Total Actual: {variant.total_actual_price:,.0f} ₽ "
                f"| Base: {variant.total_base_price:,.0f} ₽ "
                f"| Savings: {variant.total_savings:,.0f} ₽ "
                f"| Deadline: {variant.earliest_deadline}"
            )
            calc_actual = round(sum(i.recommended_tariff.actual_price or 0.0 for i in variant.items), 2)
            calc_base = round(sum(i.recommended_tariff.base_price or 0.0 for i in variant.items), 2)
            calc_savings = round(calc_base - calc_actual, 2)
            assert calc_actual == variant.total_actual_price, "Mismatch in total_actual_price!"
            assert calc_base == variant.total_base_price, "Mismatch in total_base_price!"
            assert calc_savings == variant.total_savings, "Mismatch in total_savings!"
            assert variant.total_actual_price <= profile_1.total_budget_max * 1.10, "Exceeded budget tolerance!"

            for item in variant.items:
                rt = item.recommended_tariff
                print(
                    f"   🔹 [{rt.participation_role.upper()}] {item.canonical_title} ({item.start_date}) "
                    f"— {rt.tariff_name}: {rt.actual_price:,.0f} ₽ "
                    f"| {item.ai_rationale}"
                )

        # Verify speaker role requirement in Variant 1
        v1_speakers = sum(
            1 for i in response_1.bundle_variants[0].items if i.recommended_tariff.participation_role == "speaker"
        )
        assert v1_speakers >= 1, f"Expected at least 1 speaker in Variant 1, got {v1_speakers}"
        print(f"✅ Scenario 1 Passed! Variant 1 has {v1_speakers} speaker role(s) and exact price arithmetic.")

        # Verify DB persistence
        sel_row = await db.get(Selection, response_1.selection_id)
        assert sel_row is not None, "Selection row not found in DB!"
        items_count_res = await db.execute(
            select(func.count(SelectionItem.id)).where(SelectionItem.selection_id == response_1.selection_id)
        )
        items_count = items_count_res.scalar_one()
        expected_items_count = sum(len(v.items) for v in response_1.bundle_variants)
        assert items_count == expected_items_count, (
            f"DB SelectionItem count ({items_count}) != response bundle items ({expected_items_count})"
        )
        print(f"✅ DB Persistence Verified: Selection + {items_count} SelectionItems saved in PostgreSQL.")

        # =========================================================================
        # Scenario 2: Diversification & Bonus "On Request" Events Check
        # =========================================================================
        print("\n------------------------------------------------------------")
        print("🧪 SCENARIO 2: Diversification (Variant 1 vs Variant 2) & Bonus Items")
        print("------------------------------------------------------------")
        if len(response_1.bundle_variants) == 2:
            v1_ids = {i.event_id for i in response_1.bundle_variants[0].items}
            v2_ids = {i.event_id for i in response_1.bundle_variants[1].items}
            assert v1_ids != v2_ids, "Variant 1 and Variant 2 have identical event sets!"
            diff_count = len(v1_ids.symmetric_difference(v2_ids))
            print(f"✅ Diversification Verified: Variant 1 and Variant 2 differ by {diff_count} event IDs.")
        else:
            print("ℹ️ Single variant returned for Scenario 1.")

        print(f"🎁 Bonus 'On Request' Items count: {len(response_1.bonus_on_request_items)}")
        for b in response_1.bonus_on_request_items:
            print(
                f"   ⭐ [BONUS / ON REQUEST] {b.canonical_title} ({b.start_date}) "
                f"— {b.recommended_tariff.tariff_name} (base_price={b.recommended_tariff.base_price}) "
                f"| {b.ai_rationale}"
            )
            assert b.recommended_tariff.base_price is None, "Bonus item must have base_price=None!"
        assert len(response_1.bonus_on_request_items) >= 1, "Expected at least 1 bonus on-request item!"
        print("✅ Scenario 2 Passed!")

        # =========================================================================
        # Scenario 3: Stress Test (Tiny Budget 15,000 ₽ & Empty FTS Keywords)
        # =========================================================================
        print("\n------------------------------------------------------------")
        print("🧪 SCENARIO 3: Stress Test (Budget 15,000 ₽, K=3, Empty Keywords)")
        print("------------------------------------------------------------")
        profile_3 = ClientQueryExtracted(
            cities=["Москва"],
            include_online=True,
            date_from=date(2026, 9, 1),
            date_to=date(2026, 12, 31),
            total_budget_max=15000.0,
            target_events_count=3,
            preferred_formats=[],
            required_roles=["delegate"],
            min_speaker_events=0,
            themes_keywords=[],  # Triggers fallback inside build_fts_or_query
            semantic_search_query="Конференции и выставки по строительству и бизнесу",
        )
        payload_3 = MatchRequestIn(
            raw_manager_notes="Малый бюджет 15 000 рублей на 3 мероприятия в Москве или онлайн осенью 2026.",
            override_profile=profile_3,
        )

        response_3 = await run_client_matching_pipeline(
            session=db,
            client_id=client.id,
            payload=payload_3,
        )
        assert len(response_3.bundle_variants) >= 1, "Expected graceful bundle even on tiny budget!"
        v1_tiny = response_3.bundle_variants[0]
        print(
            f"✅ Scenario 3 Passed! Assembled {len(v1_tiny.items)} events within {v1_tiny.total_actual_price:,.0f} ₽ "
            f"(Budget limit: {profile_3.total_budget_max:,.0f} ₽)."
        )

        # =========================================================================
        # Scenario 4: Pure Combinatorial Speed Benchmark (< 15 ms SLA)
        # =========================================================================
        print("\n------------------------------------------------------------")
        print("🧪 SCENARIO 4: Pure Combinatorial Speed Benchmark (Target < 15 ms)")
        print("------------------------------------------------------------")
        candidates = await get_scored_candidates(db, profile_1, today)
        t0 = time.perf_counter()
        bundles, bonus = build_bundles(candidates, profile_1)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        print(f"⚡ Pure build_bundles() execution time: {elapsed_ms:.3f} ms (SLA limit: 15.000 ms)")
        assert elapsed_ms < 15.0, f"SLA breached! build_bundles took {elapsed_ms:.3f} ms (> 15 ms)"
        print("✅ Scenario 4 Passed! Combinatorial engine is well within the < 15 ms requirement.")

    await engine.dispose()
    print("\n🎉 ALL 4 STANDALONE MATCHER SCENARIOS PASSED SUCCESSFULLY!")


if __name__ == "__main__":
    asyncio.run(run_tests())

