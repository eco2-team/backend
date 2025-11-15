from fastapi import APIRouter, Depends

from app.services.auth import AuthService

router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.get("/", summary="Auth service metrics snapshot")
async def metrics(service: AuthService = Depends()):
    return await service.get_metrics()
