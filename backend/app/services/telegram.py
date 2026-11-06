import html
import logging
from collections.abc import Sequence
from typing import Literal, Protocol, TypeAlias

# pyrefly: ignore[missing-import]
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


class TelegramTransportProtocol(Protocol):
    """Протокол транспорта отправки HTML-уведомлений в Telegram."""

    async def send_message(self, text: str, chat_id: int | str | None = None) -> bool: ...


async def _post_telegram_message(url: str, chat_id: int | str, text: str) -> httpx.Response:
    """Отправляет сообщение в Telegram Bot API через общий пул соединений."""
    client = _TelegramClientPool.get_client()
    payload: dict[str, int | str] = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
    }
    return await client.post(url, json=payload)


def _is_valid_chat_id(chat_id: int | str | None) -> bool:
    """Проверяет, что переданный идентификатор чата не пуст и не равен нулю."""
    return chat_id is not None and str(chat_id).strip() not in ("", "0")


def _resolve_target_chat_id(chat_id: int | str | None) -> int | str | None:
    """Определяет целевой chat_id: явный аргумент либо дефолтный TELEGRAM_MANAGER_CHAT_ID из настроек."""
    return chat_id if _is_valid_chat_id(chat_id) else settings.TELEGRAM_MANAGER_CHAT_ID


def _should_retry_with_fallback_chat(
    status_code: int,
    target_chat_id: int | str,
    fallback_chat: int | str | None,
) -> bool:
    """Определяет, нужно ли повторить отправку на резервный TELEGRAM_MANAGER_CHAT_ID."""
    if status_code == 200 or fallback_chat is None or not _is_valid_chat_id(fallback_chat):
        return False
    return str(target_chat_id).strip() != str(fallback_chat).strip()


class HttpTelegramTransport:
    """
    Боевой HTTP-транспорт к api.telegram.org поверх переиспользуемого пула соединений.
    При отсутствии TELEGRAM_BOT_TOKEN или целевого chat_id логирует warning и честно возвращает False.
    """

    async def send_message(self, text: str, chat_id: int | str | None = None) -> bool:
        bot_token = (settings.TELEGRAM_BOT_TOKEN or "").strip()
        target_chat_id = _resolve_target_chat_id(chat_id)

        if not bot_token or target_chat_id is None or not _is_valid_chat_id(target_chat_id):
            logger.warning(
                "Telegram-алерт не отправлен: не задан TELEGRAM_BOT_TOKEN или chat_id получателя (chat_id=%s).",
                target_chat_id,
            )
            return False

        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        try:
            resp = await _post_telegram_message(url, target_chat_id, text)
            fallback_chat = settings.TELEGRAM_MANAGER_CHAT_ID
            if fallback_chat is not None and _should_retry_with_fallback_chat(
                resp.status_code, target_chat_id, fallback_chat
            ):
                resp = await _post_telegram_message(url, fallback_chat, text)

            if resp.status_code != 200:
                logger.error("Ошибка Telegram API (%s): %s", resp.status_code, resp.text)
                return False
            return True
        except httpx.HTTPError:
            logger.exception("Сетевая ошибка при отправке в Telegram")
            return False


# [DEV-STUB: Изолированный провайдер Telegram-уведомлений для автотестов и автономного демо-стенда]
class StubTelegramTransport:
    """
    Тестовый провайдер уведомлений (активируется явно через set_telegram_transport в тестах).
    Записывает отправленные сообщения в память (sent_messages) и лог, возвращая True без сетевых вызовов.
    """

    def __init__(self) -> None:
        self.sent_messages: list[tuple[int | str | None, str]] = []

    async def send_message(self, text: str, chat_id: int | str | None = None) -> bool:
        self.sent_messages.append((chat_id, text))
        logger.info("[DEV-STUB TELEGRAM] Зафиксирован алерт менеджеру (chat_id=%s): %s", chat_id, text)
        return True


class _TelegramTransportRegistry:
    """Реестр активного транспорта уведомлений (позволяет чистое DI-переопределение в автотестах)."""

    _active_transport: TelegramTransportProtocol = HttpTelegramTransport()

    @classmethod
    def get(cls) -> TelegramTransportProtocol:
        return cls._active_transport

    @classmethod
    def set(cls, transport: TelegramTransportProtocol | None) -> None:
        cls._active_transport = transport if transport is not None else HttpTelegramTransport()


def get_telegram_transport() -> TelegramTransportProtocol:
    """Возвращает текущий зарегистрированный транспорт Telegram-уведомлений."""
    return _TelegramTransportRegistry.get()


def set_telegram_transport(transport: TelegramTransportProtocol | None) -> None:
    """Устанавливает кастомный транспорт уведомлений (или сбрасывает на боевой HttpTelegramTransport при None)."""
    _TelegramTransportRegistry.set(transport)


def _clip(value: str | None, limit: int) -> str:
    """Обрезает строку до заданного лимита символов до HTML-экранирования, предотвращая превышение 4096 байт в Telegram."""
    text = (value or "").strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


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
    reaction: ReactionType,
    comment: str | None = None,
    needs_agency_support: bool | None = None,
) -> str:
    """Форматирует HTML-сообщение менеджеру о реакции клиента на карточку витрины."""
    if reaction not in ("interested", "rejected"):
        raise ValueError(f"Недопустимый тип реакции клиента: {reaction!r}")

    reaction_label = "Интересно (👍)" if reaction == "interested" else "Заменить (👎)"
    lines = [
        f"<b>Реакция клиента на витрине ({escape_html(_clip(company_name, 120))})</b>",
        f"Статус: <b>{reaction_label}</b>",
        f"Мероприятие: «{escape_html(_clip(event_title, 250))}»",
    ]
    if comment and comment.strip():
        cleaned = comment.strip()
        lines.append(f"Комментарий: <i>{escape_html(_clip(cleaned, 1000))}</i>")
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
        f"<b>Вопрос клиента требует уточнения ({escape_html(_clip(company_name, 120))})</b>\n"
        f"Мероприятие: «{escape_html(_clip(event_title, 250))}»\n"
        f"Вопрос: <i>{escape_html(_clip(question_text.strip(), 1000))}</i>\n"
        f"Ответьте клиенту в кабинете менеджера или свяжитесь с организаторами."
    )


def format_monitoring_summary_alert(
    ready_count: int,
    needs_enrichment_titles: Sequence[str],
) -> str:
    """Форматирует утреннюю сводку итогов фонового мониторинга рынка (get_data.md раздел 6, Способ Б)."""
    lines = [
        "<b>Итоги ночного мониторинга рынка:</b>",
        f"Полностью готовы к подбору: <b>{ready_count} новых мероприятий</b>.",
    ]
    if needs_enrichment_titles:
        lines.append(
            f"Требуют быстрой проверки (не найдены цены на сайте или закрыт доступ): "
            f"<b>{len(needs_enrichment_titles)} мероприятия</b>."
        )
        for idx, title in enumerate(needs_enrichment_titles[:10], start=1):
            lines.append(f"{idx}. {escape_html(title)}")
    return "\n".join(lines)


async def send_manager_alert(
    text: str,
    chat_id: int | str | None = None,
    *,
    transport: TelegramTransportProtocol | None = None,
) -> bool:
    """
    Асинхронно отправляет сообщение менеджеру через активный TelegramTransportProtocol.
    В боевом режиме использует HttpTelegramTransport и возвращает True только при реальной доставке (HTTP 200).
    """
    active_transport = transport if transport is not None else get_telegram_transport()
    return await active_transport.send_message(text=text, chat_id=chat_id)
