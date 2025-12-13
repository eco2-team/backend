from fastapi import APIRouter, Depends

from domains.my.schemas import CharacterOwnershipStatus, UserCharacter
from domains.my.security import get_current_user, UserInfo
from domains.my.services import UserCharacterService

router = APIRouter(prefix="/user/me", tags=["user-characters"])


@router.get(
    "/characters",
    response_model=list[UserCharacter],
    summary="List characters owned by the current user",
)
async def list_owned_characters(
    user: UserInfo = Depends(get_current_user),
    service: UserCharacterService = Depends(UserCharacterService),
):
    return await service.list_owned(user.user_id)


@router.get(
    "/characters/{character_name}/ownership",
    response_model=CharacterOwnershipStatus,
    summary="Check whether the current user owns the specified character",
)
async def check_character_ownership(
    character_name: str,
    user: UserInfo = Depends(get_current_user),
    service: UserCharacterService = Depends(UserCharacterService),
):
    owned = await service.owns_character(user.user_id, character_name)
    return CharacterOwnershipStatus(character_name=character_name, owned=owned)
