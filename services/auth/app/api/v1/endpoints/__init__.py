from fastapi import APIRouter

from . import auth, health, metrics, oauth

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(metrics.router)
api_router.include_router(oauth.google_router)
api_router.include_router(oauth.kakao_router)
api_router.include_router(oauth.naver_router)

health_router = APIRouter()
health_router.include_router(health.router)

__all__ = ["api_router", "health_router"]
