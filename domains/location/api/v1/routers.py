from fastapi import APIRouter

from domains.location.api.v1.endpoints import health, location, metrics

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(location.router)
api_router.include_router(metrics.router)

health_router = APIRouter()
health_router.include_router(health.router)

__all__ = ["api_router", "health_router"]

