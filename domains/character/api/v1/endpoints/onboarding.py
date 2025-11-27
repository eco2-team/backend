from fastapi import APIRouter, Depends

from domains.character.schemas.character import (
    CharacterAcquireResponse,
    DefaultCharacterGrantRequest,
)
from domains.character.services.character import CharacterService

router = APIRouter(prefix="/internal/characters", tags=["character-onboarding"])


@router.post(
    "/default",
    response_model=CharacterAcquireResponse,
    summary="Grant the default character to a user during onboarding",
)
async def grant_default_character(
    payload: DefaultCharacterGrantRequest,
    service: CharacterService = Depends(),
):
    return await service.grant_default_character(payload.user_id)
