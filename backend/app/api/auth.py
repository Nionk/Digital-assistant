import asyncio
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_session
from app.core.security import ManagerUser, create_access_token, verify_password
from app.models.models import User

logger = logging.getLogger("app.api.auth")

router = APIRouter(prefix="/api/auth", tags=["Auth"])

AsyncSessionDep = Annotated[AsyncSession, Depends(get_async_session)]


class LoginRequestIn(BaseModel):
    """Схема входных данных для авторизации менеджера."""

    email: str = Field(
        ...,
        description="Email менеджера сопровождения",
        examples=["manager@skart.ru"],
    )
    password: str = Field(..., description="Пароль учетной записи")


class TokenOut(BaseModel):
    """Схема ответа успешной авторизации с JWT-токеном."""

    access_token: str = Field(..., description="Подписанный JWT-токен доступа (HS256)")
    token_type: str = Field(default="bearer", description="Тип авторизационного токена")
    user: ManagerUser = Field(..., description="Профиль авторизованного менеджера")


@router.post(
    "/login",
    response_model=TokenOut,
    status_code=status.HTTP_200_OK,
    summary="Авторизация менеджера отдела сопровождения и получение JWT-токена",
    description="Проверяет email и пароль менеджера по таблице users и возвращает JWT-токен доступа.",
)
async def login(
    credentials: LoginRequestIn,
    session: AsyncSessionDep,
) -> TokenOut:
    """Аутентификация менеджера и генерация криптографически подписанного JWT токена."""
    normalized_email = credentials.email.strip().lower()
    try:
        stmt = select(User).where(User.email == normalized_email)
        res = await session.execute(stmt)
        user = res.scalar_one_or_none()

        is_valid_pw = False
        if user is not None:
            is_valid_pw = await asyncio.to_thread(
                verify_password, credentials.password, user.password_hash
            )

        if user is None or not is_valid_pw:
            logger.warning("Неудачная попытка входа для email: %s", credentials.email)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Неверный email или пароль.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        manager_user = ManagerUser(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            telegram_chat_id=user.telegram_chat_id,
        )
    except (SQLAlchemyError, OSError) as exc:
        logger.error("Ошибка БД при авторизации: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="База данных временно недоступна",
        ) from exc

    access_token = create_access_token(
        data={"sub": str(manager_user.id), "email": manager_user.email}
    )
    logger.info("Менеджер ID=%s (%s) успешно авторизован.", manager_user.id, manager_user.email)
    return TokenOut(
        access_token=access_token,
        token_type="bearer",
        user=manager_user,
    )
