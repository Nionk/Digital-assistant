import logging
from datetime import UTC, datetime, timedelta
from typing import Annotated

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_async_session
from app.models.models import User

logger = logging.getLogger("app.core.security")

# Схема безопасности для Swagger UI: регистрирует заголовок Authorization: Bearer <token>.
security_scheme = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    """Генерирует криптостойкий bcrypt-хэш пароля с солью."""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Проверяет соответствие открытого пароля bcrypt-хэшу из БД."""
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8"),
        )
    except (ValueError, TypeError):
        return False


def create_access_token(data: dict[str, object], expires_delta: timedelta | None = None) -> str:
    """
    Создает подписанный JWT-токен (HS256) с метками времени exp и iat.
    """
    to_encode = data.copy()
    now = datetime.now(UTC)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire, "iat": now})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_access_token(token: str) -> dict[str, object]:
    """
    Декодирует и валидирует JWT-токен.
    Выбрасывает HTTP 401 при истечении срока действия или неверной подписи.
    """
    try:
        payload: dict[str, object] = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
        )
        return payload
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Срок действия токена авторизации истек.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    except jwt.InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Невалидный токен авторизации.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


class ManagerUser(BaseModel):
    """
    Модель авторизованного пользователя-менеджера.
    Полностью совместима по полям с ORM-моделью User (SQLAlchemy).
    """
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    full_name: str
    telegram_chat_id: int | None = None


async def get_current_manager(
    auth: HTTPAuthorizationCredentials | None = Depends(security_scheme),  # noqa: B008
    session: AsyncSession = Depends(get_async_session),  # noqa: B008
) -> ManagerUser:
    """
    Зависимость аутентификации менеджера.
    
    1. Боевой режим (при наличии заголовка Authorization: Bearer <token>):
       - Декодирует JWT через pyjwt с проверкой подписи и срока жизни;
       - Загружает реальную запись User из таблицы users PostgreSQL;
       - Возвращает типизированный объект ManagerUser.
       
    2. Переходный режим Демо (при отсутствии заголовка):
       - Если settings.ALLOW_DEMO_AUTH_BYPASS == False: немедленно возвращает HTTP 401;
       - Если settings.ALLOW_DEMO_AUTH_BYPASS == True: запрашивает ведущего менеджера id=1
         из базы данных с логированием предупреждения.
       [TODO-PHASE-P01]: Удалить обход после реализации страницы входа во фронтенде (Шаг 6).
    """
    # 1. Если заголовок с Bearer-токеном предоставлен — строгая криптографическая проверка
    if auth is not None and auth.credentials:
        payload = decode_access_token(auth.credentials)
        sub = payload.get("sub")
        if not sub:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="В токене авторизации отсутствует субъект (sub).",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Поиск пользователя в БД по email или целочисленному id
        sub_str = str(sub)
        user_id_val = int(sub_str) if sub_str.isdigit() else -1
        stmt = select(User).where((User.email == sub_str) | (User.id == user_id_val))
        res = await session.execute(stmt)
        user = res.scalar_one_or_none()

        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Пользователь из токена авторизации не найден в базе данных.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        return ManagerUser.model_validate(user)

    # 2. Если заголовок отсутствует: проверка флага переходного периода Демо
    if not settings.ALLOW_DEMO_AUTH_BYPASS:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Требуется авторизация. Передайте заголовок 'Authorization: Bearer <token>'.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    logger.warning(
        "[SECURITY-DEMO-BYPASS] Запрос без Bearer-токена обработан от имени менеджера id=1. "
        "Переходный мост будет отключен после внедрения экрана входа (Шаг 6 / Задача P-01)."
    )

    try:
        stmt = select(User).where(User.id == 1)
        res = await session.execute(stmt)
        user = res.scalar_one_or_none()
        if user is not None:
            return ManagerUser.model_validate(user)
    except (SQLAlchemyError, OSError) as exc:
        logger.warning(
            "[SECURITY-DEMO-BYPASS] Ошибка обращения к БД при загрузке менеджера (%s). "
            "Используется резервный профиль для автономного тестового режима.",
            exc,
        )

    # [DEV-STUB: Резервный профиль на случай остановленной БД во время изолированных контрактных тестов]
    return ManagerUser(
        id=1,
        email="manager@skart.ru",
        full_name="Анна Соколова (Ведущий менеджер сопровождения)",
        telegram_chat_id=settings.TELEGRAM_MANAGER_CHAT_ID,
    )


# Типизированный псевдоним зависимости для внедрения в защищенные роуты кабинета менеджера
CurrentManagerDep = Annotated[ManagerUser, Depends(get_current_manager)]
