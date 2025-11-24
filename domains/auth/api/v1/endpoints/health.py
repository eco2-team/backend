from pydantic import BaseModel

from logging import getLogger

from domains.auth.api.v1.routers import health_probe_router, health_router
from domains.auth.schemas.common import SuccessResponse

SERVICE_NAME = "auth"
logger = getLogger(__name__)


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
    logger.info("Health probe accessed via /api/v1/health")
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
    logger.info("Health probe accessed via /health")
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
    logger.info("Readiness probe accessed via /api/v1/ready")
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
    logger.info("Readiness probe accessed via /ready")
    return HealthSuccessResponse(
        data=HealthData(
            status="ready",
            service=f"{SERVICE_NAME}-api",
        )
    )
