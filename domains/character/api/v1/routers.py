from fastapi import APIRouter

from domains.character.api.v1.endpoints import character, health, metrics, onboarding, rewards

api_router = APIRouter()
api_router.include_router(character.router)
api_router.include_router(metrics.router)
api_router.include_router(rewards.router)
api_router.include_router(onboarding.router)

health_router = APIRouter()
health_router.include_router(health.router)

metrics_router = APIRouter()
metrics_router.include_router(metrics.router)

__all__ = ["api_router", "health_router", "metrics_router"]
