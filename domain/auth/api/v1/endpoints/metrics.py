from typing import Any

from fastapi import Depends

from domain.auth.api.v1.router import metrics_router
from domain.auth.schemas.common import SuccessResponse
from domain.auth.services.auth import AuthService


class MetricsSuccessResponse(SuccessResponse[dict[str, Any]]):
    """Standardized success response for metrics."""

    pass


@metrics_router.get(
    "/", response_model=MetricsSuccessResponse, summary="Auth service metrics snapshot"
)
async def metrics(service: AuthService = Depends()):
    metrics_data = await service.get_metrics()
    return MetricsSuccessResponse(data=metrics_data)
