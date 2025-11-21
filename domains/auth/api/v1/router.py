from fastapi import APIRouter

from domains.auth.core.config import get_settings
from domains.auth.services.auth import ACCESS_COOKIE_NAME
from domains.auth.services.token_blacklist import TokenBlacklist
from domains._shared.security import build_access_token_dependency

auth_router = APIRouter(prefix="/auth", tags=["auth"])
google_router = APIRouter(prefix="/auth/google", tags=["auth/google"])
kakao_router = APIRouter(prefix="/auth/kakao", tags=["auth/kakao"])
naver_router = APIRouter(prefix="/auth/naver", tags=["auth/naver"])
metrics_router = APIRouter(prefix="/auth/metrics", tags=["metrics"])
health_router = APIRouter(prefix="/auth", tags=["health"])
health_probe_router = APIRouter(tags=["health"])

access_token_dependency = build_access_token_dependency(
    get_settings,
    cookie_alias=ACCESS_COOKIE_NAME,
    blacklist_dependency=TokenBlacklist,
)

# Import endpoints before including routers to ensure they're registered
from domains.auth.api.v1.endpoints import auth as _auth_endpoints  # noqa: F401, E402, UP035
from domains.auth.api.v1.endpoints import health as _health_endpoints  # noqa: F401, E402, UP035
from domains.auth.api.v1.endpoints import metrics as _metrics_endpoints  # noqa: F401, E402, UP035

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth_router)
api_router.include_router(google_router)
api_router.include_router(kakao_router)
api_router.include_router(naver_router)
api_router.include_router(health_router)
api_router.include_router(metrics_router)

__all__ = [
    "api_router",
    "auth_router",
    "health_router",
    "health_probe_router",
    "google_router",
    "kakao_router",
    "naver_router",
    "metrics_router",
    "access_token_dependency",
]
