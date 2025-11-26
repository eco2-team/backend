from fastapi import APIRouter, Depends

from domains.chat.services.chat import ChatService

router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.get("/", summary="Chat service metrics")
async def metrics(service: ChatService = Depends()):
    return await service.metrics()
