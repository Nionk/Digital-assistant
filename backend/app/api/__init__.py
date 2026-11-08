from app.api.auth import router as auth_router
from app.api.manager import router as manager_router
from app.api.showcase import router as showcase_router

__all__ = ["auth_router", "manager_router", "showcase_router"]
