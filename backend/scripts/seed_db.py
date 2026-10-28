import asyncio
import json
import hashlib
import sys
from pathlib import Path
import bcrypt
from sqlalchemy import select, delete, text
from sqlalchemy.ext.asyncio import AsyncSession

# Настройка sys.path для прямого запуска скрипта из любой директории
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app.core.database import async_session_maker
from app.models.models import User, Client, Event, EventTariff, LLMCache
from app.services.ai_client import get_embeddings_batch
from app.schemas.event_ingestion import EventIngestionSchema



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


def find_seed_data_file() -> Path:
    """Определяет путь к seed_data.json в зависимости от рабочей директории."""
    candidates = [
        BASE_DIR / "scripts" / "seed_data.json",
        BASE_DIR.parent / "seed_data.json",
        Path("seed_data.json"),
        Path("backend/scripts/seed_data.json"),
    ]
    for p in candidates:
        if p.exists():
            return p.resolve()
    raise FileNotFoundError("Файл seed_data.json не найден ни в одной из доступных директорий.")


async def seed_events(session: AsyncSession) -> list[Event]:
    """
    Идемпотентное наполнение базы данных мероприятиями, тарифами,
    1024-мерными векторными эмбеддингами (Zero-Local-ML via Jina AI)
    и предпрогретым кэшем частых вопросов регламента (llm_cache).
    Соответствует задаче D-04 из plan.md.
    """
    seed_file = find_seed_data_file()
    print(f"[INFO] Загрузка золотого датасета из: {seed_file}")
    with open(seed_file, "r", encoding="utf-8") as f:
        raw_items = json.load(f)

    print(f"[INFO] Найдено {len(raw_items)} мероприятий в {seed_file.name}.")

    # 1. Батчевая генерация 1024-мерных эмбеддингов через облачный API Jina AI
    summaries = [item["event_data"]["summary"] for item in raw_items]
    print(f"[INFO] Расчет эмбеддингов для {len(summaries)} саммари через Jina Embeddings v3...")
    embeddings = await get_embeddings_batch(summaries, batch_size=16)
    print(f"[OK] Успешно получено {len(embeddings)} векторов (размерность {len(embeddings[0]) if embeddings else 0}).")

    seeded_events: list[Event] = []
    total_tariffs_count = 0
    total_cache_count = 0

    for i, item in enumerate(raw_items):
        e_raw = item["event_data"]
        # Валидируем и нормализуем через строгую Pydantic v2 схему
        e_schema = EventIngestionSchema.model_validate(e_raw)

        # Проверяем наличие события в БД по каноническому названию
        stmt = select(Event).where(Event.canonical_title == e_schema.canonical_title)
        res = await session.execute(stmt)
        event = res.scalar_one_or_none()

        missing_fields = item.get("missing_or_needed_data", {}).get("missing_fields", [])
        warnings = e_schema.missing_data_warnings or missing_fields

        if event is None:
            event = Event(
                canonical_title=e_schema.canonical_title,
                normalized_title=e_raw.get("normalized_title") or e_schema.canonical_title.lower().strip(),
                event_format=e_schema.event_format,
                city=e_schema.city,
                is_online=e_schema.is_online,
                venue=e_schema.venue,
                start_date=e_schema.start_date,
                end_date=e_schema.end_date,
                summary=e_schema.summary,
                full_regulation_markdown=e_schema.full_regulation_markdown,
                themes=e_schema.themes,
                source_urls=e_raw.get("source_urls", []),
                data_status="ready",
                missing_data_warnings=warnings,
                summary_embedding=embeddings[i],
                is_active=True,
            )
            session.add(event)
            await session.flush()
            print(f"[OK] Создано мероприятие: ID={event.id}, '{event.canonical_title}' (онлайн={event.is_online}, город={event.city})")
        else:
            event.normalized_title = e_raw.get("normalized_title") or e_schema.canonical_title.lower().strip()
            event.event_format = e_schema.event_format
            event.city = e_schema.city
            event.is_online = e_schema.is_online
            event.venue = e_schema.venue
            event.start_date = e_schema.start_date
            event.end_date = e_schema.end_date
            event.summary = e_schema.summary
            event.full_regulation_markdown = e_schema.full_regulation_markdown
            event.themes = e_schema.themes
            event.source_urls = e_raw.get("source_urls", [])
            event.data_status = "ready"
            event.missing_data_warnings = warnings
            event.summary_embedding = embeddings[i]
            event.is_active = True
            await session.flush()
            print(f"[EXISTS] Мероприятие синхронизировано: ID={event.id}, '{event.canonical_title}'")

        seeded_events.append(event)

        # 2. Идемпотентная синхронизация тарифов (event_tariffs)
        await session.execute(delete(EventTariff).where(EventTariff.event_id == event.id))
        created_tariffs: list[EventTariff] = []
        for t_data in e_schema.tariffs:
            tariff = EventTariff(
                event_id=event.id,
                tariff_name=t_data.tariff_name,
                participation_role=t_data.participation_role,
                base_price=t_data.base_price,
                early_bird_price=t_data.early_bird_price,
                early_bird_deadline=t_data.early_bird_deadline,
                is_vat_included=t_data.is_vat_included,
                included_benefits=t_data.included_benefits,
            )
            session.add(tariff)
            created_tariffs.append(tariff)

        await session.flush()
        total_tariffs_count += len(created_tariffs)

        # 3. Идемпотентный предпрогрев кэша частых вопросов регламента (llm_cache)
        await session.execute(delete(LLMCache).where(LLMCache.event_id == event.id))
        seen_cache_keys: set[str] = set()

        for faq in e_schema.faq_cache:
            cache_payload = json.dumps({
                "is_answer_found": True,
                "answer_text": faq.answer,
                "source_quote": faq.source_quote,
            }, ensure_ascii=False)

            tariff_ids = [0] + [t.id for t in created_tariffs]

            # Нормализованный вопрос (канонический чипс) + исходные вариации вопроса
            questions_to_hash = {faq.question.strip().lower()}
            for raw_faq in e_raw.get("faq_cache", []):
                if raw_faq.get("answer") == faq.answer:
                    questions_to_hash.add(raw_faq.get("question", "").strip().lower())

            for tid in tariff_ids:
                for q_str in questions_to_hash:
                    if not q_str:
                        continue
                    cache_key = hashlib.sha256(f"{event.id}:{tid}:{q_str}".encode("utf-8")).hexdigest()
                    if cache_key not in seen_cache_keys:
                        seen_cache_keys.add(cache_key)
                        session.add(LLMCache(
                            cache_key=cache_key,
                            event_id=event.id,
                            response_text=cache_payload,
                        ))

        await session.flush()
        total_cache_count += len(seen_cache_keys)

    print(f"[OK] Успешно сидировано: {len(seeded_events)} мероприятий, {total_tariffs_count} тарифов, {total_cache_count} записей llm_cache.")
    return seeded_events


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

            # 3. Сидинг 15 мероприятий, 43 тарифов, векторов и llm_cache (D-04 п.1-4)
            events = await seed_events(session)

            # 4. Синхронизация последовательностей (Bug 2 fix)
            await sync_database_sequences(session)

    print("=" * 70)
    print(f"Сидинг успешно завершен! Создано/проверено: 1 менеджер, {len(clients)} клиента, {len(events)} мероприятий.")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(seed_all())

