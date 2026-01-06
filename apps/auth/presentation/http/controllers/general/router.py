"""General Router.

Health check와 Metrics 엔드포인트입니다.
"""

from fastapi import APIRouter

from apps.auth.presentation.http.controllers.general.health import (
    router as health_router,
)
from apps.auth.presentation.http.controllers.general.metrics import (
    router as metrics_router,
)

router = APIRouter()

router.include_router(health_router)
router.include_router(metrics_router)
