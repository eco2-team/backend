"""Root Router.

최상위 라우터로, 모든 하위 라우터를 통합합니다.
"""

from fastapi import APIRouter

from apps.auth.presentation.http.controllers.api_v1_router import (
    router as api_v1_router,
)

router = APIRouter()

# API v1
router.include_router(api_v1_router, prefix="/api/v1")
