from fastapi import APIRouter, Depends, HTTPException, status

from app.schemas.chat import (
    ChatFeedback,
    ChatMessageRequest,
    ChatMessageResponse,
    ChatSession,
)
from app.services.chat import ChatService

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post(
    "/messages",
    response_model=ChatMessageResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Send message and get assistant response",
)
async def send_message(
    payload: ChatMessageRequest,
    service: ChatService = Depends(),
):
    return await service.send_message(payload)


@router.get(
    "/sessions/{session_id}",
    response_model=ChatSession,
    summary="Retrieve chat session transcript",
)
async def get_session(session_id: str, service: ChatService = Depends()):
    session = await service.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@router.delete("/sessions/{session_id}", summary="Delete chat session")
async def delete_session(session_id: str, service: ChatService = Depends()):
    await service.delete_session(session_id)
    return {"message": f"session {session_id} deleted"}


@router.get("/suggestions", summary="Suggested starter prompts")
async def suggestions(service: ChatService = Depends()):
    return await service.suggestions()


@router.post("/feedback", summary="Submit conversation feedback")
async def feedback(payload: ChatFeedback, service: ChatService = Depends()):
    await service.submit_feedback(payload)
    return {"message": "feedback stored"}
