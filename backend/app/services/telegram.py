import logging
import httpx
from app.core.config import settings

logger = logging.getLogger(__name__)

async def send_manager_alert(text: str) -> bool:
    """
    Асинхронно отправляет сообщение менеджеру в Telegram.
    Если токен не задан, выводит сообщение в консоль (для локального тестирования).
    """
    if not settings.TELEGRAM_BOT_TOKEN or not settings.TELEGRAM_MANAGER_CHAT_ID:
        logger.warning(f"[TELEGRAM MOCK] Алерт менеджеру: {text}")
        print(f"\n🔔 [TELEGRAM MOCK] {text}\n")
        return True

    url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": settings.TELEGRAM_MANAGER_CHAT_ID,
        "text": text,
        "parse_mode": "HTML"
    }

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json=payload, timeout=10.0)
            if resp.status_code != 200:
                print(f"❌ ОШИБКА TELEGRAM API: {resp.status_code} - {resp.text}")
                return False
            return True
    except Exception as e:
        logger.error(f"Ошибка отправки в Telegram: {e}")
        print(f"❌ КРИТИЧЕСКАЯ ОШИБКА СЕТИ: {e}")
        return False