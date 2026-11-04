import html
import logging
from typing import Literal, TypeAlias

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

ReactionType: TypeAlias = Literal["interested", "rejected"]

# Маркеры запроса дополнительных услуг агентства (подготовка спикера, застройка стенда, организация встреч)
_AGENCY_SUPPORT_MARKERS: tuple[str, ...] = (
    "сопровожден",
    "спикер",
    "знакомств",
    "встреч",
    "интерактив",
    "стенд",
    "деловая игра",
)

# [DEV-STUB: Изоляция демо/тестовых chat_id из стаба авторизации (security.py) и локального запуска без бота]
DEV_STUB_CHAT_IDS: frozenset[str] = frozenset({"0", "123456789"})


class _TelegramClientPool:
    """Менеджер переиспользуемого пула HTTP-соединений к api.telegram.org."""

    _client: httpx.AsyncClient | None = None

    @classmethod
    def get_client(cls) -> httpx.AsyncClient:
        if cls._client is None or cls._client.is_closed:
            cls._client = httpx.AsyncClient(timeout=10.0)
        return cls._client

    @classmethod
    async def close(cls) -> None:
        if cls._client is not None and not cls._client.is_closed:
            await cls._client.aclose()
        cls._client = None


async def close_telegram_http_client() -> None:
    """Корректно закрывает пул соединений Telegram HTTP-клиента при остановке приложения."""
    await _TelegramClientPool.close()


def escape_html(value: str | None) -> str:
    """Безопасное экранирование пользовательских строк для Telegram parse_mode='HTML'."""
    if not value:
        return ""
    return html.escape(str(value), quote=True)


def _detect_agency_support_request(comment: str) -> bool:
    """Определяет наличие запроса на подготовку или сопровождение участия со стороны агентства."""
    low_comment = comment.strip().lower()
    return any(marker in low_comment for marker in _AGENCY_SUPPORT_MARKERS)


def format_reaction_alert(
    company_name: str,
    event_title: str,
    reaction: ReactionType | str,
    comment: str | None = None,
    needs_agency_support: bool | None = None,
) -> str:
    """Форматирует HTML-сообщение менеджеру о реакции клиента на карточку витрины."""
    reaction_label = "Интересно (👍)" if reaction == "interested" else "Заменить (👎)"
    lines = [
        f"<b>Реакция клиента на витрине ({escape_html(company_name)})</b>",
        f"Статус: <b>{reaction_label}</b>",
        f"Мероприятие: «{escape_html(event_title)}»",
    ]
    if comment and comment.strip():
        cleaned = comment.strip()
        lines.append(f"Комментарий: <i>{escape_html(cleaned)}</i>")
        support_flag = (
            needs_agency_support
            if needs_agency_support is not None
            else _detect_agency_support_request(cleaned)
        )
        if support_flag:
            lines.append(
                "<b>Задача агентства (Этап 09):</b> <i>Запрошена подготовка / сопровождение участия</i>"
            )
    elif needs_agency_support:
        lines.append(
            "<b>Задача агентства (Этап 09):</b> <i>Запрошена подготовка / сопровождение участия</i>"
        )
    return "\n".join(lines)


def format_escalation_alert(
    company_name: str,
    event_title: str,
    question_text: str,
) -> str:
    """Форматирует HTML-сообщение менеджеру при эскалации вопроса вне регламента."""
    return (
        f"<b>Вопрос клиента требует уточнения ({escape_html(company_name)})</b>\n"
        f"Мероприятие: «{escape_html(event_title)}»\n"
        f"Вопрос: <i>{escape_html(question_text.strip())}</i>\n"
        f"Ответьте клиенту в кабинете менеджера или свяжитесь с организаторами."
    )


async def _post_telegram_message(url: str, chat_id: int | str, text: str) -> httpx.Response:
    """Отправляет сообщение в Telegram Bot API через общий пул соединений."""
    client = _TelegramClientPool.get_client()
    payload: dict[str, int | str] = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
    }
    return await client.post(url, json=payload)


def _resolve_telegram_target(
    chat_id: int | str | None,
    text: str,
) -> tuple[str, int | str, str] | None:
    """Проверяет конфигурацию и стабовые chat_id; возвращает (bot_token, target_chat_id, target_str) или None."""
    explicit_str = str(chat_id or "").strip()
    # [DEV-STUB: При вызове со стабовым chat_id из демо-режима или автотестов не спамим реальный Telegram API]
    if explicit_str in DEV_STUB_CHAT_IDS:
        logger.info("[DEV-STUB TELEGRAM] Алерт для стабового chat_id=%s: %s", explicit_str, text)
        return None

    target_chat_id: int | str | None = chat_id or settings.TELEGRAM_MANAGER_CHAT_ID
    target_str = str(target_chat_id or "").strip()
    bot_token = (settings.TELEGRAM_BOT_TOKEN or "").strip()

    # [DEV-STUB: Локальный запуск без настроенного TELEGRAM_BOT_TOKEN или TELEGRAM_MANAGER_CHAT_ID]
    if not bot_token or target_chat_id is None or target_str in (*DEV_STUB_CHAT_IDS, ""):
        logger.info("[DEV-STUB TELEGRAM] Алерт менеджеру (chat_id=%s): %s", target_chat_id, text)
        return None

    return bot_token, target_chat_id, target_str


async def send_manager_alert(
    text: str,
    chat_id: int | str | None = None,
) -> bool:
    """
    Асинхронно отправляет сообщение менеджеру в Telegram Bot API по его telegram_chat_id.
    Для стабовых ID (DEV_STUB_CHAT_IDS) или при отсутствии токена использует изолированный DEV-STUB логгер.
    """
    resolved = _resolve_telegram_target(chat_id, text)
    if resolved is None:
        return True

    bot_token, target_chat_id, target_str = resolved
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    try:
        resp = await _post_telegram_message(url, target_chat_id, text)
        fallback_chat = settings.TELEGRAM_MANAGER_CHAT_ID
        if resp.status_code != 200 and fallback_chat and target_str != str(fallback_chat).strip():
            resp = await _post_telegram_message(url, fallback_chat, text)

        if resp.status_code != 200:
            logger.error("Ошибка Telegram API (%s): %s", resp.status_code, resp.text)
            return False
        return True
    except httpx.HTTPError:
        logger.exception("Сетевая ошибка при отправке в Telegram")
        return False
