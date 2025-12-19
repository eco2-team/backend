from fastapi import APIRouter, Depends

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
