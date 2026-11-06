from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.core.config import settings


def today_local() -> date:
    """
    Возвращает сегодняшнюю дату в часовом поясе приложения (по умолчанию Europe/Moscow).
    Предотвращает баги на стыке суток (00:00 - 03:00 МСК) при запуске контейнера в UTC.
    """
    return datetime.now(ZoneInfo(settings.APP_TIMEZONE)).date()

