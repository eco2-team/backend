from fastapi import APIRouter

from . import character, health, metrics

api_router = APIRouter()
api_router.include_router(character.router)
api_router.include_router(metrics.router)

health_router = APIRouter()
health_router.include_router(health.router)

__all__ = ["api_router", "health_router"]
