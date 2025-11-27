from fastapi import APIRouter, Depends

from domains.my.schemas import UserCharacter
from domains.my.security import TokenPayload, access_token_dependency
from domains.my.services import UserCharacterService

router = APIRouter(prefix="/users/me", tags=["user-characters"])


@router.get(
    "/characters",
    response_model=list[UserCharacter],
    summary="List characters owned by the current user",
)
async def list_owned_characters(
    token: TokenPayload = Depends(access_token_dependency),
    service: UserCharacterService = Depends(UserCharacterService),
):
    return await service.list_owned(token.user_id)
