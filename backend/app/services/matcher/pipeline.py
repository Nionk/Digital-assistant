import asyncio

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Client, Event, Selection, SelectionItem
from app.schemas.manager import (
    BundleEventItemOut,
    BundleVariantOut,
    ClientQueryExtracted,
    MatchRequestIn,
    MatchResponseOut,
    TariffOptionOut,
)
from app.services.matcher.pitch import (
    _collect_unique_events_for_pitch,
    build_default_rationale,
)
from app.services.matcher.types import (
    EvaluatedCombo,
    ScoredEventCandidate,
    _normalize_data_status,
    _normalize_event_format,
)


def _to_bundle_event_item(
    cand: ScoredEventCandidate,
    recommended_tariff: TariffOptionOut,
    rationale: str,
) -> BundleEventItemOut:
    """Собирает выходную карточку BundleEventItemOut со строгой нормализацией типов."""
    ev = cand.event
    primary_url = str(ev.source_urls[0]) if (ev.source_urls and len(ev.source_urls) > 0) else None
    return BundleEventItemOut(
        event_id=ev.id,
        canonical_title=ev.canonical_title,
        event_format=_normalize_event_format(ev.event_format),
        city=ev.city,
        is_online=bool(ev.is_online),
        venue=ev.venue,
        start_date=ev.start_date,
        end_date=ev.end_date,
        themes=list(ev.themes or []),
        recommended_tariff=recommended_tariff,
        available_tariffs=cand.all_tariffs,
        ai_rationale=rationale,
        website_url=primary_url,
        data_status=_normalize_data_status(ev.data_status),
        missing_data_warnings=list(ev.missing_data_warnings or []),
    )


def _format_bundle_variants_out(
    evaluated_variants: list[EvaluatedCombo],
    rationales_map: dict[int, str],
    unique_events_info: dict[int, tuple[Event, TariffOptionOut]] | None = None,
    profile: ClientQueryExtracted | None = None,
) -> list[BundleVariantOut]:
    """Преобразует оцененные комбинации EvaluatedCombo в выходные схемы BundleVariantOut."""
    bundle_variants_out: list[BundleVariantOut] = []
    for idx, ev_var in enumerate(evaluated_variants, start=1):
        items_out = []
        for cand, tar in zip(ev_var.candidates, ev_var.chosen_tariffs):
            if unique_events_info and profile and cand.event.id in unique_events_info:
                ref_tariff = unique_events_info[cand.event.id][1]
                if tar.participation_role == ref_tariff.participation_role:
                    rationale = rationales_map.get(cand.event.id, "")
                else:
                    rationale = build_default_rationale(cand.event, tar, profile)
            else:
                rationale = rationales_map.get(cand.event.id, "")
            items_out.append(
                _to_bundle_event_item(
                    cand=cand,
                    recommended_tariff=tar,
                    rationale=rationale,
                )
            )
        if idx == 1:
            title = (
                "Вариант 1: Максимальное совпадение по темам (требует согласования бюджета)"
                if ev_var.is_over_budget_tolerance
                else f"Вариант 1: Максимальный охват тем ({len(items_out)} события)"
            )
        else:
            title = (
                f"Вариант 2: Альтернативный состав ({len(items_out)} события, требует согласования бюджета)"
                if ev_var.is_over_budget_tolerance
                else f"Вариант 2: Оптимальный по экономии бюджета ({len(items_out)} события)"
            )

        bundle_variants_out.append(
            BundleVariantOut(
                bundle_group=idx,
                bundle_title=title,
                items=items_out,
                total_actual_price=ev_var.total_actual_price,
                total_base_price=ev_var.total_base_price,
                total_savings=ev_var.total_savings,
                earliest_deadline=ev_var.earliest_deadline,
                is_over_budget_tolerance=ev_var.is_over_budget_tolerance,
            )
        )
    return bundle_variants_out


async def _persist_draft_selection(
    session: AsyncSession,
    client_id: int,
    pitch_text: str,
    budget_limit: float,
    bundle_variants_out: list[BundleVariantOut],
) -> int:
    """Удаляет устаревшие черновики клиента и атомарно сохраняет новый черновик подборки."""
    await session.execute(
        delete(Selection).where(
            Selection.client_id == client_id,
            Selection.status == "draft",
        )
    )
    new_selection = Selection(
        client_id=client_id,
        status="draft",
        generated_pitch_text=pitch_text,
        total_budget_limit=budget_limit,
    )
    session.add(new_selection)
    await session.flush()
    selection_id = new_selection.id

    for variant in bundle_variants_out:
        for item in variant.items:
            session.add(
                SelectionItem(
                    selection_id=selection_id,
                    event_id=item.event_id,
                    recommended_tariff_id=item.recommended_tariff.tariff_id,
                    bundle_group=variant.bundle_group,
                    ai_rationale=item.ai_rationale,
                    client_reaction="pending",
                )
            )
    await session.commit()
    return selection_id


async def _load_and_update_client_profile(
    session: AsyncSession,
    client_id: int,
    payload: MatchRequestIn,
) -> tuple[Client, ClientQueryExtracted]:
    """Загружает клиента из БД и обновляет его сохраненный NER-профиль."""
    import app.services.matcher as matcher_pkg

    client_res = await session.execute(select(Client).where(Client.id == client_id))
    client_obj = client_res.scalar_one_or_none()
    if client_obj is None:
        raise LookupError(f"Клиент с ID={client_id} не найден")

    if payload.override_profile is not None:
        extracted_profile = payload.override_profile
        extracted_profile.profile_source = "manual"
    else:
        extracted_profile = await matcher_pkg.extract_client_profile(payload.raw_manager_notes)

    client_obj.raw_manager_notes = payload.raw_manager_notes
    client_obj.extracted_profile = extracted_profile.model_dump(mode="json")
    return client_obj, extracted_profile


async def run_client_matching_pipeline(
    session: AsyncSession,
    client_id: int,
    payload: MatchRequestIn,
) -> MatchResponseOut:
    """
    Полный цикл Задачи D-07 + сохранение черновика подборки в БД.
    Выбрасывает LookupError, если клиент с указанным client_id отсутствует в БД.
    """
    import app.services.matcher as matcher_pkg

    client_obj, extracted_profile = await _load_and_update_client_profile(session, client_id, payload)
    candidates = await matcher_pkg.get_scored_candidates(
        session, extracted_profile, matcher_pkg.today_local()
    )
    evaluated_variants, bonus_pairs = await asyncio.to_thread(
        matcher_pkg.build_bundles, candidates, extracted_profile
    )

    rationales_map, pitch_text = await matcher_pkg.generate_pitch_and_rationales(
        client_name=client_obj.company_name,
        raw_notes=payload.raw_manager_notes,
        profile=extracted_profile,
        selected_variants=evaluated_variants,
        bonus_pairs=bonus_pairs,
    )
    unique_events_info = _collect_unique_events_for_pitch(evaluated_variants, bonus_pairs)
    bundle_variants_out = _format_bundle_variants_out(
        evaluated_variants, rationales_map, unique_events_info, extracted_profile
    )
    bonus_items_out = [
        _to_bundle_event_item(cand, tar, rationales_map.get(cand.event.id, ""))
        for cand, tar in bonus_pairs
    ]
    selection_id = await _persist_draft_selection(
        session, client_obj.id, pitch_text, extracted_profile.total_budget_max, bundle_variants_out
    )

    return MatchResponseOut(
        selection_id=selection_id,
        client_id=client_id,
        extracted_profile=extracted_profile,
        bundle_variants=bundle_variants_out,
        bonus_on_request_items=bonus_items_out,
        generated_pitch_text=pitch_text,
    )
