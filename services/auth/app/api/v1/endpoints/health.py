from fastapi import APIRouter

SERVICE_NAME = "auth"

router = APIRouter(tags=["health"])


@router.get("/health", summary="Auth service health probe")
async def health():
    return {"status": "healthy", "service": f"{SERVICE_NAME}-api"}


@router.get("/ready", summary="Auth service readiness probe")
async def readiness():
    return {"status": "ready", "service": f"{SERVICE_NAME}-api"}
