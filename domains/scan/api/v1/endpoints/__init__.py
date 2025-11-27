from fastapi import APIRouter

from . import health, metrics, scan

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(scan.router)
api_router.include_router(metrics.router)

health_router = APIRouter()
health_router.include_router(health.router)

__all__ = ["api_router", "health_router"]
