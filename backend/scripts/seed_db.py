import asyncio
import sys
from pathlib import Path
import bcrypt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# Настройка sys.path для прямого запуска скрипта из любой директории
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app.core.database import async_session_maker
from app.models.models import User, Client


def hash_password(password: str) -> str:
    """Генерирует криптостойкий bcrypt-хэш пароля для пользователя."""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


DEFAULT_MANAGER_DATA = {
    "id": 1,
    "email": "manager@skart.ru",
    "full_name": "Анна Соколова (Ведущий менеджер сопровождения)",
    "password": "scart_manager_2026",
    "telegram_chat_id": 123456789,
}

TEST_CLIENTS_DATA = [
    {
        "id": 1,
        "company_name": "ГК «Пионер»",
        "contact_person": "Игорь Ветров (Директор по развитию)",
        "raw_manager_notes": (
            "Созвонились с ГК Пионер. Ищут на ноябрь-декабрь в Москве или СПб 3 небольших мероприятия "
            "(круглые столы или закрытые завтраки) по теме КРТ и урбанистики. Хотят выступить спикером "
            "хотя бы на одном. Общий бюджет — потолок 400 тыс. руб."
        ),
        "extracted_profile": {
            "cities": ["Москва", "Санкт-Петербург"],
            "include_online": True,
            "date_from": "2026-11-01",
            "date_to": "2026-12-25",
            "total_budget_max": 400000.0,
            "target_events_count": 3,
            "preferred_formats": ["roundtable", "business_breakfast"],
            "required_roles": ["speaker", "delegate"],
            "min_speaker_events": 1,
            "themes_keywords": ["КРТ", "урбанистика", "жилая застройка"],
            "semantic_search_query": "Комплексное развитие территорий КРТ урбанистика жилая застройка девелопмент круглый стол",
        },
    },
    {
        "id": 2,
        "company_name": "Девелопмент-Юг",
        "contact_person": "Елена Смирнова (PR-директор)",
        "raw_manager_notes": (
            "Нужны 2 региональные сессии по ИЖС и мастер-планированию на конец осени. "
            "Только делегатами, бюджет до 150 000 руб. Город — Екатеринбург."
        ),
        "extracted_profile": {
            "cities": ["Екатеринбург"],
            "include_online": False,
            "date_from": "2026-10-15",
            "date_to": "2026-11-30",
            "total_budget_max": 150000.0,
            "target_events_count": 2,
            "preferred_formats": ["session"],
            "required_roles": ["delegate"],
            "min_speaker_events": 0,
            "themes_keywords": ["ИЖС", "мастер-планирование", "девелопмент"],
            "semantic_search_query": "Индивидуальное жилищное строительство ИЖС мастер-планирование региональные сессии",
        },
    },
    {
        "id": 3,
        "company_name": "Брусника. Сибирь",
        "contact_person": "Максим Ковалев (Руководитель проектного офиса)",
        "raw_manager_notes": (
            "Интересует онлайн-конференция по BIM и цифровизации стройки, а также очный форум в Москве. "
            "Бюджет до 250 000 руб, обязательно делегатское участие с доступом к закрытому нетворкингу."
        ),
        "extracted_profile": {
            "cities": ["Москва"],
            "include_online": True,
            "date_from": "2026-11-01",
            "date_to": "2026-12-31",
            "total_budget_max": 250000.0,
            "target_events_count": 2,
            "preferred_formats": ["conference", "forum"],
            "required_roles": ["delegate"],
            "min_speaker_events": 0,
            "themes_keywords": ["BIM", "цифровизация", "ТИМ", "строительство"],
            "semantic_search_query": "BIM цифровизация строительства ТИМ онлайн-конференция форум Москва",
        },
    },
]


async def seed_default_manager(session: AsyncSession) -> User:
    """
    Идемпотентное создание/обновление дефолтного ведущего менеджера (id=1).
    Соответствует контракту get_current_manager() из app/core/security.py.
    """
    stmt = select(User).where((User.id == DEFAULT_MANAGER_DATA["id"]) | (User.email == DEFAULT_MANAGER_DATA["email"]))
    result = await session.execute(stmt)
    manager = result.scalar_one_or_none()

    if manager is None:
        manager = User(
            id=DEFAULT_MANAGER_DATA["id"],
            email=DEFAULT_MANAGER_DATA["email"],
            password_hash=hash_password(DEFAULT_MANAGER_DATA["password"]),
            full_name=DEFAULT_MANAGER_DATA["full_name"],
            telegram_chat_id=DEFAULT_MANAGER_DATA["telegram_chat_id"],
        )
        session.add(manager)
        await session.flush()
        print(f"[OK] Создан дефолтный менеджер: ID={manager.id}, email={manager.email}, full_name='{manager.full_name}'")
    else:
        # Обновляем профиль при необходимости
        manager.full_name = DEFAULT_MANAGER_DATA["full_name"]
        manager.telegram_chat_id = DEFAULT_MANAGER_DATA["telegram_chat_id"]
        await session.flush()
        print(f"[EXISTS] Дефолтный менеджер уже существует: ID={manager.id}, email={manager.email}")

    return manager


async def seed_test_clients(session: AsyncSession, manager_id: int) -> list[Client]:
    """
    Идемпотентное создание/обновление 3 тестовых клиентов строительной отрасли.
    Связаны внешним ключом с manager_id (дефолтный менеджер).
    """
    seeded_clients: list[Client] = []

    for client_dict in TEST_CLIENTS_DATA:
        stmt = select(Client).where(
            (Client.id == client_dict["id"]) | (Client.company_name == client_dict["company_name"])
        )
        result = await session.execute(stmt)
        client = result.scalar_one_or_none()

        if client is None:
            client = Client(
                id=client_dict["id"],
                manager_id=manager_id,
                company_name=client_dict["company_name"],
                contact_person=client_dict["contact_person"],
                raw_manager_notes=client_dict["raw_manager_notes"],
                extracted_profile=client_dict["extracted_profile"],
            )
            session.add(client)
            await session.flush()
            print(f"[OK] Создан клиент: ID={client.id}, компания='{client.company_name}', контакт='{client.contact_person}'")
        else:
            client.manager_id = manager_id
            client.contact_person = client_dict["contact_person"]
            client.raw_manager_notes = client_dict["raw_manager_notes"]
            client.extracted_profile = client_dict["extracted_profile"]
            await session.flush()
            print(f"[EXISTS] Клиент уже существует (данные синхронизированы): ID={client.id}, компания='{client.company_name}'")

        seeded_clients.append(client)

    return seeded_clients


async def seed_events_placeholder(session: AsyncSession):
    """
    Заглушка для пунктов 1–4 задачи D-04:
    Наполнение базы данных 35 мероприятиями, тарифами и эмбеддингами из seed_data.json.
    Будет выполнена при утверждении золотого датасета.
    """
    print("[INFO] Наполнение 35 мероприятиями (пункты 1–4 D-04) ожидает формирования финального seed_data.json.")


from sqlalchemy import text


async def sync_database_sequences(session: AsyncSession):
    """
    Синхронизирует последовательности (sequence) автоинкремента после вставки явных ID.
    Предотвращает UniqueViolationError при последующих автоматических INSERT без явного id.
    """
    for table in ("users", "clients", "events", "event_tariffs", "selections"):
        try:
            await session.execute(
                text(f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), COALESCE((SELECT MAX(id) FROM {table}), 1), true);")
            )
        except Exception:
            # Игнорируем в средах без поддержки pg_get_serial_sequence (например, SQLite в тестах)
            pass


async def seed_all():
    """Главная функция запуска сидинга базы данных."""
    print("=" * 70)
    print("Запуск скрипта наполнения БД (seed_db.py) — Задача D-04")
    print("=" * 70)

    async with async_session_maker() as session:
        async with session.begin():
            # 1. Сидинг дефолтного менеджера (D-04 п.5)
            manager = await seed_default_manager(session)

            # 2. Сидинг 3 тестовых клиентов (D-04 п.5)
            clients = await seed_test_clients(session, manager.id)

            # 3. Информирование о пунктах 1–4
            await seed_events_placeholder(session)

            # 4. Синхронизация последовательностей (Bug 2 fix)
            await sync_database_sequences(session)

    print("=" * 70)
    print(f"Сидинг успешно завершен! Создано/проверено: 1 менеджер, {len(clients)} клиента.")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(seed_all())
