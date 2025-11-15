from fastapi import APIRouter, Depends

from app.services.chat import ChatService

router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.get("/", summary="Chat service metrics")
async def metrics(service: ChatService = Depends()):
    return await service.metrics()
