from fastapi import APIRouter, Depends

from domains.location.security import get_current_user, UserInfo
from domains.location.services.location import LocationService

router = APIRouter(prefix="/locations/metrics", tags=["metrics"])


@router.get("/", summary="Location service metrics")
async def metrics(
    service: LocationService = Depends(),
    _: UserInfo = Depends(get_current_user),
):
    return await service.metrics()
