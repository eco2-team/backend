"""Health controller - Health check endpoints."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    """헬스체크 엔드포인트."""
    return {"status": "healthy", "service": "users-api"}


@router.get("/ping")
async def ping() -> str:
    """Ping 엔드포인트."""
    return "pong"
