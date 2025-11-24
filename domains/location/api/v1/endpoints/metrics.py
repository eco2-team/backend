from fastapi import APIRouter, Depends

from domains.location.security import access_token_dependency
from domains.location.services.location import LocationService
from domains._shared.security import TokenPayload

router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.get("/", summary="Location service metrics")
async def metrics(
    service: LocationService = Depends(),
    _: TokenPayload = Depends(access_token_dependency),
):
    return await service.metrics()
