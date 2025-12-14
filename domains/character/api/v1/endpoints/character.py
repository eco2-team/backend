from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, status

from domains.character.schemas.catalog import CharacterProfile
from domains.character.services.character import CharacterService
from domains.character.api.dependencies import get_current_user

router = APIRouter(
    prefix="/character",
    tags=["character"],
    dependencies=[Depends(get_current_user)],
)


@router.get(
    "/catalog",
    response_model=list[CharacterProfile],
    summary="Available character catalog",
)
async def catalog(service: CharacterService = Depends()):
    return await service.catalog()


# ---------------------------------------------------------------------------
# Protected ping endpoint (no DB I/O) for ext-authz 테스트 용도
# ext-authz가 주입한 x-user-id 헤더를 읽어 응답 (auth/ping과 동일한 패턴)
# ---------------------------------------------------------------------------


@router.get(
    "/ping",
    summary="Protected ping (ext-authz check only)",
)
async def ping_protected(
    x_user_id: Optional[str] = Header(default=None, alias="x-user-id"),
    x_auth_provider: Optional[str] = Header(default=None, alias="x-auth-provider"),
):
    """ext-authz 검증 후 주입된 헤더 확인용 엔드포인트."""
    if not x_user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing x-user-id header",
        )

    return {
        "success": True,
        "data": {
            "user_id": x_user_id,
            "provider": x_auth_provider or "unknown",
        },
    }
