from fastapi import APIRouter

from . import health, info, metrics

api_router = APIRouter()
api_router.include_router(info.router)
api_router.include_router(metrics.router)

health_router = APIRouter()
health_router.include_router(health.router)

__all__ = ["api_router", "health_router"]
