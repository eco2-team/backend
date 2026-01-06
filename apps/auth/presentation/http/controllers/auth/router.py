"""Auth Router.

인증 관련 엔드포인트를 통합합니다.
"""

from fastapi import APIRouter

from apps.auth.presentation.http.controllers.auth.authorize import (
    router as authorize_router,
)
from apps.auth.presentation.http.controllers.auth.callback import (
    router as callback_router,
)
from apps.auth.presentation.http.controllers.auth.logout import router as logout_router
from apps.auth.presentation.http.controllers.auth.refresh import (
    router as refresh_router,
)

router = APIRouter()

router.include_router(authorize_router)
router.include_router(callback_router)
router.include_router(logout_router)
router.include_router(refresh_router)
