from typing import Annotated
from fastapi import Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, ConfigDict

# Схема безопасности для Swagger UI: регистрирует заголовок Authorization: Bearer <token>,
# но auto_error=False позволяет выполнять запросы без токена на этапе Демо.
security_scheme = HTTPBearer(auto_error=False)


class ManagerUser(BaseModel):
    """
    Модель пользователя-менеджера.
    Полностью совместима по полям с ORM-моделью User (SQLAlchemy).
    """
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    full_name: str
    telegram_chat_id: int | None = None


async def get_current_manager(
    auth: HTTPAuthorizationCredentials | None = Depends(security_scheme)
) -> ManagerUser:
    """
    ЗАГЛУШКА ДЛЯ ДЕМО (Auth Stub / Dependency Stub).
    
    На этапе MVP / Демо всегда возвращает дефолтного ведущего менеджера (id=1).
    Это позволяет frontend-разработчикам и ИИ-генераторам интерфейса сразу работать
    с реальными данными и эндпоинтами без обязательного прохождения экрана авторизации.
    
    После демонстрации (в задаче P-01) внутрь этой функции будет добавлена
    проверка JWT-токена из заголовка Authorization (pyjwt + bcrypt) без изменения
    сигнатур и контрактов контроллеров в api/manager.py.
    """
    return ManagerUser(
        id=1,
        email="manager@skart.ru",
        full_name="Анна Соколова (Ведущий менеджер сопровождения)",
        telegram_chat_id=123456789,
    )


# Типизированный псевдоним зависимости для внедрения в защищенные роуты кабинета менеджера
CurrentManagerDep = Annotated[ManagerUser, Depends(get_current_manager)]
