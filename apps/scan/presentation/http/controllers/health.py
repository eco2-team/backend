"""Health Check Controller."""

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    """서비스 헬스 체크."""
    return {"status": "ok", "service": "scan-api", "version": "2.0.0"}


@router.get("/ready")
async def ready() -> dict:
    """서비스 준비 상태 체크."""
    # TODO: Redis, DB 연결 확인
    return {"status": "ready"}
