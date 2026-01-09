from fastapi import APIRouter

from images.api.v1.endpoints import health, image, metrics

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(image.router)
api_router.include_router(metrics.router)

health_router = APIRouter()
health_router.include_router(health.router)

__all__ = ["api_router", "health_router"]
