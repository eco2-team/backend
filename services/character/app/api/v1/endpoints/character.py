from fastapi import APIRouter, Depends

from app.schemas.character import (
    CharacterAnalysisRequest,
    CharacterProfile,
    CharacterHistoryEntry,
)
from app.services.character import CharacterService

router = APIRouter(prefix="/character", tags=["character"])


@router.post("/analyze", response_model=CharacterProfile, summary="Analyze user to character")
async def analyze_user(
    payload: CharacterAnalysisRequest,
    service: CharacterService = Depends(),
):
    return await service.analyze(payload)


@router.get(
    "/history/{user_id}",
    response_model=list[CharacterHistoryEntry],
    summary="List character evolution history",
)
async def history(user_id: str, service: CharacterService = Depends()):
    return await service.history(user_id)


@router.get(
    "/catalog",
    response_model=list[CharacterProfile],
    summary="Available character catalog",
)
async def catalog(service: CharacterService = Depends()):
    return await service.catalog()
