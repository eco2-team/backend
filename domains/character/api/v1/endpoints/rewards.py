from fastapi import APIRouter, Depends

from domains.character.schemas import CharacterRewardRequest, CharacterRewardResponse
from domains.character.services.character import CharacterService

router = APIRouter(
    prefix="/internal/characters",
    tags=["character-rewards"],
    # Istio sidecar handles mTLS authentication.
    # We rely on AuthorizationPolicy to restrict access to this endpoint.
    dependencies=[],
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
