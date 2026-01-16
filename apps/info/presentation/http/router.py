"""HTTP Router.

FastAPI 라우터 설정.
"""

from fastapi import APIRouter

from info.presentation.http.controllers.news_controller import (
    router as news_router,
)
from info.presentation.http.schemas import HealthCheckResponseSchema

router = APIRouter(prefix="/api/v1/info")

# 뉴스 라우터 등록
router.include_router(news_router)


@router.get(
    "/health",
    response_model=HealthCheckResponseSchema,
    tags=["health"],
    summary="헬스체크",
)
async def health_check() -> HealthCheckResponseSchema:
    """서비스 헬스체크."""
    return HealthCheckResponseSchema(status="ok", service="info")
