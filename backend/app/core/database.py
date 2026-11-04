from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

# [AUDIT-TIMEBOMB]: Отсутствуют параметры пула соединений (pool_pre_ping=True, pool_size, max_overflow, pool_recycle), что приведет к падению запросов при разрыве idle-соединений с PostgreSQL.
engine = create_async_engine(settings.DATABASE_URL, echo=False)
async_session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

class Base(DeclarativeBase):
    pass

# [AUDIT-CRUTCH]: Отсутствует обработка исключений с явным rollback() сессии и аннотация возвращаемого типа AsyncGenerator[AsyncSession, None].
async def get_async_session():
    async with async_session_maker() as session:
        yield session