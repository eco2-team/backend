from pydantic import BaseModel

from domain.auth.api.v1.router import health_router
from domain.auth.schemas.common import SuccessResponse

SERVICE_NAME = "auth"


class HealthData(BaseModel):
    """Health check response data."""

    status: str
    service: str


class HealthSuccessResponse(SuccessResponse[HealthData]):
    """Standardized success response for health check."""

    pass


@health_router.get(
    "/health", response_model=HealthSuccessResponse, summary="Auth service health probe"
)
async def health():
    return HealthSuccessResponse(
        data=HealthData(
            status="healthy",
            service=f"{SERVICE_NAME}-api",
        )
    )


@health_router.get(
    "/ready", response_model=HealthSuccessResponse, summary="Auth service readiness probe"
)
async def readiness():
    return HealthSuccessResponse(
        data=HealthData(
            status="ready",
            service=f"{SERVICE_NAME}-api",
        )
    )
