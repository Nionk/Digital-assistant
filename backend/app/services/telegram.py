import html
import logging
import httpx
from app.core.config import settings

logger = logging.getLogger(__name__)

DUMMY_SEED_CHAT_IDS = {None, "", 0, "0", 123456789, "123456789"}


def escape_html(value: str | None) -> str:
    """Безопасное экранирование пользовательских строк для Telegram parse_mode='HTML'."""
    if not value:
        return ""
    return html.escape(str(value), quote=True)


def format_reaction_alert(
    company_name: str,
    event_title: str,
    reaction: str,
    comment: str | None = None,
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
        lower_c = cleaned.lower()
        if any(
            kw in lower_c
            for kw in (
                "сопровожден",
                "спикер",
                "знакомств",
                "встреч",
                "интерактив",
                "стенд",
                "деловая игра",
            )
        ):
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


async def send_manager_alert(
    text: str,
    chat_id: int | str | None = None,
) -> bool:
    """
    Асинхронно отправляет сообщение менеджеру в Telegram Bot API по его telegram_chat_id
    (с фолбэком на глобальный TELEGRAM_MANAGER_CHAT_ID из настроек, если в БД стоит тестовый стаб 123456789).
    Если токен или chat_id не заданы, логирует сообщение в режиме [TELEGRAM MOCK] и возвращает True.
    """
    target_chat_id = (
        chat_id
        if chat_id not in DUMMY_SEED_CHAT_IDS
        else settings.TELEGRAM_MANAGER_CHAT_ID
    )
    bot_token = (settings.TELEGRAM_BOT_TOKEN or "").strip()

    if not bot_token or not target_chat_id:
        logger.info("[TELEGRAM MOCK] Алерт менеджеру (chat_id=%s): %s", target_chat_id, text)
        return True

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

    async def _post_message(cid: int | str) -> httpx.Response:
        payload = {
            "chat_id": cid,
            "text": text,
            "parse_mode": "HTML",
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            return await client.post(url, json=payload)

    try:
        resp = await _post_message(target_chat_id)
        if (
            resp.status_code != 200
            and settings.TELEGRAM_MANAGER_CHAT_ID
            and str(target_chat_id) != str(settings.TELEGRAM_MANAGER_CHAT_ID)
        ):
            resp = await _post_message(settings.TELEGRAM_MANAGER_CHAT_ID)

        if resp.status_code != 200:
            logger.error("Ошибка Telegram API (%s): %s", resp.status_code, resp.text)
            return False
        return True
    except Exception as exc:
        logger.error("Сетевая ошибка при отправке в Telegram: %s", exc)
        return False
