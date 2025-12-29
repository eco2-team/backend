"""Authenticated ping endpoint for ext-authz performance testing.

This endpoint requires authentication but performs no database operations,
making it ideal for measuring pure ext-authz overhead.

Usage:
    curl -H "Authorization: Bearer <token>" https://api.dev.growbin.app/api/v1/user/ping
"""

from fastapi import APIRouter, Depends

from domains.my.security import get_current_user, UserInfo

router = APIRouter(tags=["ping"])


@router.get("/ping", summary="Authenticated ping (no DB)")
async def ping(user: UserInfo = Depends(get_current_user)):
    """Return user info from token without any database lookup.

    This endpoint is designed for ext-authz performance testing:
    - Requires valid JWT token (ext-authz verification)
    - No database queries
    - Minimal response payload
    """
    return {
        "pong": True,
        "user_id": str(user.user_id)[:8] + "...",  # Masked for security
        "provider": user.provider,
    }
