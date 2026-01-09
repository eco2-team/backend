"""Health/Readiness probe endpoints (로그 제외 - 노이즈 방지)."""

from fastapi import APIRouter

SERVICE_NAME = "image"

router = APIRouter(tags=["health"])


@router.get("/health")
async def health():
    return {"status": "healthy", "service": f"{SERVICE_NAME}-api"}


@router.get("/ready")
async def readiness():
    return {"status": "ready", "service": f"{SERVICE_NAME}-api"}
