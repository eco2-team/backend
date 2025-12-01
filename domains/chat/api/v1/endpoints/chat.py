from fastapi import APIRouter, Depends, status

from domains._shared.security import TokenPayload
from domains.chat.api.v1.dependencies import get_chat_service
from domains.chat.schemas.chat import ChatMessageRequest, ChatMessageResponse
from domains.chat.services.chat import ChatService
from domains.chat.security import access_token_dependency

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
    _token: TokenPayload = Depends(access_token_dependency),
):
    return await service.send_message(payload)
