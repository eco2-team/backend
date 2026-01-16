"""Auth Router.

인증 관련 엔드포인트를 통합합니다.
"""

from fastapi import APIRouter
from fastapi.responses import RedirectResponse

from auth.presentation.http.controllers.auth.authorize import (
    router as authorize_router,
)
from auth.presentation.http.controllers.auth.callback import (
    router as callback_router,
)
from auth.presentation.http.controllers.auth.logout import router as logout_router
from auth.presentation.http.controllers.auth.refresh import (
    router as refresh_router,
)

router = APIRouter()


# /docs, /openapi.json 경로를 명시적으로 처리
# /{provider} 패턴보다 먼저 매칭되어야 함
@router.get("/docs", include_in_schema=False)
async def auth_docs_redirect():
    """루트 /docs로 리다이렉트."""
    return RedirectResponse(url="/docs")


@router.get("/openapi.json", include_in_schema=False)
async def auth_openapi_redirect():
    """루트 /openapi.json으로 리다이렉트."""
    return RedirectResponse(url="/openapi.json")


router.include_router(authorize_router)
router.include_router(callback_router)
router.include_router(logout_router)
router.include_router(refresh_router)
