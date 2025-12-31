"""HTTP controllers (routers)."""

from apps.users.presentation.http.controllers.characters import (
    router as characters_router,
)
from apps.users.presentation.http.controllers.health import router as health_router
from apps.users.presentation.http.controllers.profile import router as profile_router

__all__ = ["profile_router", "characters_router", "health_router"]
