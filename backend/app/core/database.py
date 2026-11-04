from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

# Промышленный пул асинхронных соединений:
# pool_pre_ping=True: пингует соединение перед выдачей из пула (предотвращает падения при разрывах idle-соединений)
# pool_size=10, max_overflow=20: контроль максимального количества TCP-сокетов к Postgres
# pool_recycle=1800: пересоздание соединений каждые 30 минут для предотвращения утечек на стороне СУБД
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
    pool_recycle=1800,
    pool_timeout=30.0,
)

async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI зависимость для выдачи изолированной асинхронной сессии SQLAlchemy.
    Автоматически выполняет откат при исключениях и корректно закрывает соединение.
    """
    async with async_session_maker() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
