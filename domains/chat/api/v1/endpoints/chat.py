from fastapi import APIRouter, Depends, status

from domains.chat.api.v1.dependencies import get_chat_service
from domains.chat.schemas.chat import ChatMessageRequest, ChatMessageResponse
from domains.chat.services.chat import ChatService
from domains.chat.security import get_current_user, UserInfo

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post(
    "/messages",
    response_model=ChatMessageResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Send message and get assistant response",
)
async def send_message(
    payload: ChatMessageRequest,
    service: ChatService = Depends(get_chat_service),
    _user: UserInfo = Depends(get_current_user),
):
    return await service.send_message(payload)
