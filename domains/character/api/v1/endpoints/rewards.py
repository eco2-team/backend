from fastapi import APIRouter, Depends

from domains.character.schemas import CharacterRewardRequest, CharacterRewardResponse
from domains.character.services.character import CharacterService
from domains.character.api.dependencies import service_token_dependency

router = APIRouter(
    prefix="/internal/characters",
    tags=["character-rewards"],
    dependencies=[Depends(service_token_dependency)],
)


@router.post(
    "/rewards",
    response_model=CharacterRewardResponse,
    summary="Evaluate and apply character reward from classification sources",
)
async def evaluate_character_reward(
    payload: CharacterRewardRequest,
    service: CharacterService = Depends(),
):
    return await service.evaluate_reward(payload)
