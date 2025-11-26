from fastapi import APIRouter

from domains.info.api.v1.endpoints import health, info, metrics

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(info.router)
api_router.include_router(metrics.router)

health_router = APIRouter()
health_router.include_router(health.router)

__all__ = ["api_router", "health_router"]
