"""Health/Readiness probe endpoints (로그 제외 - 노이즈 방지)."""

from pydantic import BaseModel

from domains.auth.presentation.http.routers import health_probe_router, health_router
from domains.auth.application.schemas.common import SuccessResponse

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
async def health_api():
    return HealthSuccessResponse(
        data=HealthData(
            status="healthy",
            service=f"{SERVICE_NAME}-api",
        )
    )


@health_probe_router.get(
    "/health", response_model=HealthSuccessResponse, summary="Auth service health probe"
)
async def health_root():
    return HealthSuccessResponse(
        data=HealthData(
            status="healthy",
            service=f"{SERVICE_NAME}-api",
        )
    )


@health_router.get(
    "/ready", response_model=HealthSuccessResponse, summary="Auth service readiness probe"
)
async def readiness_api():
    return HealthSuccessResponse(
        data=HealthData(
            status="ready",
            service=f"{SERVICE_NAME}-api",
        )
    )


@health_probe_router.get(
    "/ready", response_model=HealthSuccessResponse, summary="Auth service readiness probe"
)
async def readiness_root():
    return HealthSuccessResponse(
        data=HealthData(
            status="ready",
            service=f"{SERVICE_NAME}-api",
        )
    )
