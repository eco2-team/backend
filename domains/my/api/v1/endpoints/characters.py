from fastapi import APIRouter, Depends

from domains.my.schemas import CharacterOwnershipStatus, UserCharacter
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


@router.get(
    "/characters/{character_name}/ownership",
    response_model=CharacterOwnershipStatus,
    summary="Check whether the current user owns the specified character",
)
async def check_character_ownership(
    character_name: str,
    token: TokenPayload = Depends(access_token_dependency),
    service: UserCharacterService = Depends(UserCharacterService),
):
    owned = await service.owns_character(token.user_id, character_name)
    return CharacterOwnershipStatus(character_name=character_name, owned=owned)
