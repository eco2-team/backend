"""API v1 Router."""

from fastapi import APIRouter

from apps.auth.presentation.http.controllers.auth.router import router as auth_router
from apps.auth.presentation.http.controllers.general.router import (
    router as general_router,
)

router = APIRouter()

# Auth endpoints
router.include_router(auth_router, prefix="/auth", tags=["auth"])

# General endpoints (health, metrics)
router.include_router(general_router, tags=["general"])
