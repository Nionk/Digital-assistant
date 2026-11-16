import asyncio
import logging

import httpx
from instructor.core import InstructorError
from openai import APIError
from pydantic import BaseModel, Field, field_validator

from app.services.scraper.sources import CustomerSourceConfig, DiscoveredCandidate

logger = logging.getLogger(__name__)


class CandidateTriageDecision(BaseModel):
    """Решение дешевого LLM-триажа кандидата до запуска 2-Hop краулера и дорогой экстракции LLM-3."""

    is_b2b_target: bool = Field(
        ...,
        description=(
            "True только для деловых B2B/профессиональных событий в сфере строительства, архитектуры, "
            "дизайна, интерьеров, урбанистики, девелопмента, недвижимости, инженерии и бизнеса "
            "(форумы, конференции, выставки, круглые столы, бизнес-завтраки, отраслевые дайджесты). "
            "False для художественных выставок картин/плакатов, спектаклей, концертов, экскурсий, хобби и детских курсов."
        ),
    )
    is_russia_or_online: bool = Field(
        ...,
        description=(
            "True, если событие проводится в России (или онлайн, когда онлайн допустим для источника). "
            "False для зарубежных мероприятий (и зарубежных вебинаров при запрете глобального онлайна)."
        ),
    )
    reason: str = Field(
        default="",
        max_length=150,
        description="Краткое обоснование решения (до 150 символов).",
    )

    @field_validator("reason", mode="before")
    @classmethod
    def _truncate_reason(cls, value: object) -> str:
        text = " ".join(str(value or "").split())
        return text[:150]


async def triage_discovery_candidate(
    candidate: DiscoveredCandidate,
    source: CustomerSourceConfig,
) -> CandidateTriageDecision:
    """
    Выполняет дешевый B2B/РФ LLM-триаж карточки по минимальному сниппету до 2-Hop и LLM-3.
    При отсутствии LLM_API_KEY пропускает кандидата дальше (fail-open) для автономных тестов.
    """
    import app.services.scraper as scraper_pkg

    if not scraper_pkg.settings.LLM_API_KEY:
        return CandidateTriageDecision(
            is_b2b_target=True,
            is_russia_or_online=True,
            reason="LLM_API_KEY не задан — пропуск триажа",
        )

    allow_global_online = source.source_key != "archdaily"
    if not source.russia_online_only:
        geo_rule = "Гео-ограничений нет: ставь is_russia_or_online=True."
    elif not allow_global_online:
        geo_rule = (
            "Гео-правило (строго РФ): ставь is_russia_or_online=True ТОЛЬКО если событие проходит в России "
            "(города РФ или явное упоминание России). Международные и англоязычные онлайн-вебинары вне РФ -> False."
        )
    else:
        geo_rule = (
            "Гео-правило: ставь is_russia_or_online=True, если событие проходит в России или в онлайн-формате. "
            "Офлайн-события в других странах (Европа, Азия, СНГ и т.д.) -> False."
        )

    system_prompt = (
        "Ты — быстрый B2B-фильтр событий для корпоративной базы знаний.\n"
        "Оцени кандидата по заголовку и короткому фрагменту:\n"
        "1) is_b2b_target=True для деловых B2B и профессиональных мероприятий в сферах: "
        "строительство, архитектура, дизайн, интерьеры, урбанистика, девелопмент, недвижимость, инженерия, бизнес "
        "(включая профессиональные дайджесты дизайнерских/архитектурных событий).\n"
        "   is_b2b_target=False для художественных выставок картин/плакатов/фотографий, театров, концертов, "
        "туристических экскурсий, досуговых хобби-мастер-классов и детских курсов/шоу.\n"
        f"2) {geo_rule}\n"
        "3) reason — кратко (до 150 символов)."
    )
    user_prompt = (
        f"Источник: {source.display_name}\n"
        f"URL: {candidate.url}\n"
        f"Заголовок: {candidate.title or '(не указан)'}\n"
        f"Фрагмент: {(candidate.snippet or '')[:500]}"
    )

    try:
        async with scraper_pkg.LLM_SEMAPHORE:
            decision: CandidateTriageDecision = await asyncio.wait_for(
                scraper_pkg.structured_llm_client.chat.completions.create(
                    model=scraper_pkg.settings.LLM_MODEL,
                    response_model=CandidateTriageDecision,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    max_tokens=200,
                    max_retries=1,
                ),
                timeout=15.0,
            )
            return decision
    except (TimeoutError, APIError, httpx.HTTPError, InstructorError) as exc:
        logger.warning(
            "Сбой LLM-триажа для %s (%s), кандидат отложен для повтора (fail-closed): %s",
            candidate.url,
            source.source_key,
            exc,
        )
        raise
