# [AUDIT-STUB]: В пакете app.api отсутствует модуль auth.py (POST /api/auth/login) из фиксированной структуры монорепозитория (rules.md п. 2).
from app.api.manager import router as manager_router
from app.api.showcase import router as showcase_router

__all__ = ["manager_router", "showcase_router"]
