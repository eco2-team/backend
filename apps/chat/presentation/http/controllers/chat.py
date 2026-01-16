"""Chat API Controller.

RESTful 엔드포인트:
- GET    /chat              채팅 목록 (사이드바)
- POST   /chat              새 채팅 생성
- GET    /chat/{id}         채팅 상세 + 메시지
- DELETE /chat/{id}         채팅 삭제 (soft delete)
- POST   /chat/{id}/messages  메시지 전송 → Worker
- POST   /chat/{job_id}/input Human-in-the-Loop 입력

SSE 스트리밍은 별도 SSE Gateway에서 처리:
- GET /chat/{job_id}/events
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field, HttpUrl

from chat.application.chat.commands import SubmitChatRequest
from chat.domain.entities.chat import Chat
from chat.domain.entities.message import Message  # MessageResponse용
from chat.setup.dependencies import (
    ChatRepositoryDep,
    SubmitCommandDep,
    get_async_redis,
)

router = APIRouter(prefix="/chat", tags=["chat"])
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Response Schemas
# ─────────────────────────────────────────────────────────────────────────────


class UserLocation(BaseModel):
    """사용자 위치 (Geolocation API 형식)."""

    latitude: float = Field(description="위도")
    longitude: float = Field(description="경도")


class ChatSummary(BaseModel):
    """채팅 목록 항목 (사이드바용)."""

    id: str = Field(description="채팅 ID")
    title: str | None = Field(default=None, description="채팅 제목")
    preview: str | None = Field(default=None, description="마지막 메시지 미리보기")
    message_count: int = Field(description="메시지 수")
    last_message_at: datetime | None = Field(default=None, description="마지막 메시지 시각")
    created_at: datetime = Field(description="생성 시각")

    @classmethod
    def from_entity(cls, chat: Chat) -> "ChatSummary":
        return cls(
            id=str(chat.id),
            title=chat.title,
            preview=chat.preview,
            message_count=chat.message_count,
            last_message_at=chat.last_message_at,
            created_at=chat.created_at,
        )


class ChatListResponse(BaseModel):
    """채팅 목록 응답."""

    chats: list[ChatSummary] = Field(description="채팅 목록")
    next_cursor: str | None = Field(default=None, description="다음 페이지 커서")


class MessageResponse(BaseModel):
    """메시지 응답."""

    id: str = Field(description="메시지 ID")
    role: str = Field(description="역할 (user/assistant)")
    content: str = Field(description="내용")
    intent: str | None = Field(default=None, description="분류된 의도")
    metadata: dict[str, Any] | None = Field(default=None, description="메타데이터")
    created_at: datetime = Field(description="생성 시각")

    @classmethod
    def from_entity(cls, message: Message) -> "MessageResponse":
        return cls(
            id=str(message.id),
            role=message.role,
            content=message.content,
            intent=message.intent,
            metadata=message.metadata,
            created_at=message.created_at,
        )


class ChatDetailResponse(BaseModel):
    """채팅 상세 응답 (메시지 포함)."""

    id: str = Field(description="채팅 ID")
    title: str | None = Field(default=None, description="채팅 제목")
    messages: list[MessageResponse] = Field(description="메시지 목록")
    has_more: bool = Field(default=False, description="더 많은 메시지 존재 여부")
    created_at: datetime = Field(description="생성 시각")


class CreateChatRequest(BaseModel):
    """새 채팅 생성 요청."""

    title: str | None = Field(default=None, description="채팅 제목 (선택)")


class CreateChatResponse(BaseModel):
    """새 채팅 생성 응답."""

    id: str = Field(description="생성된 채팅 ID")
    title: str | None = Field(default=None, description="채팅 제목")
    created_at: datetime = Field(description="생성 시각")


class SendMessageRequest(BaseModel):
    """메시지 전송 요청."""

    message: str = Field(description="사용자 메시지")
    image_url: HttpUrl | None = Field(
        default=None,
        description="첨부 이미지 URL",
    )
    user_location: UserLocation | None = Field(
        default=None,
        description="사용자 위치 (주변 검색용)",
    )
    model: str | None = Field(
        default=None,
        description="LLM 모델명 (미지정 시 기본값)",
    )


class SendMessageResponse(BaseModel):
    """메시지 전송 응답."""

    job_id: str = Field(description="작업 ID (Worker)")
    stream_url: str = Field(description="SSE 스트리밍 URL")
    status: str = Field(default="submitted", description="현재 상태")


class UserInputRequest(BaseModel):
    """Human-in-the-Loop 추가 입력 스키마."""

    type: str = Field(
        description="입력 타입 (location, confirmation, cancel)",
        examples=["location", "confirmation", "cancel"],
    )
    data: dict[str, Any] | None = Field(
        default=None,
        description="입력 데이터",
        examples=[{"latitude": 37.5665, "longitude": 126.9780}],
    )


class UserInputResponse(BaseModel):
    """추가 입력 응답."""

    status: str = Field(default="received")
    job_id: str


class DeleteChatResponse(BaseModel):
    """채팅 삭제 응답."""

    success: bool = Field(description="삭제 성공 여부")


# ─────────────────────────────────────────────────────────────────────────────
# User Authentication (Ext-Authz 연동)
# ─────────────────────────────────────────────────────────────────────────────


class User(BaseModel):
    """인증된 사용자 모델."""

    user_id: str
    role: str | None = None


def get_current_user(
    x_user_id: str | None = Header(None, alias="X-User-ID"),
    x_user_role: str | None = Header(None, alias="X-User-Role"),
) -> User:
    """Ext-Authz에서 주입된 사용자 정보 추출."""
    if not x_user_id:
        raise HTTPException(
            status_code=401,
            detail="Unauthorized: X-User-ID header is required",
        )
    return User(user_id=x_user_id, role=x_user_role)


CurrentUser = Annotated[User, Depends(get_current_user)]


# ─────────────────────────────────────────────────────────────────────────────
# Chat CRUD Endpoints
# ─────────────────────────────────────────────────────────────────────────────


@router.get(
    "",
    response_model=ChatListResponse,
    summary="채팅 목록 조회 (사이드바)",
)
async def list_chats(
    user: CurrentUser,
    repo: ChatRepositoryDep,
    limit: int = Query(default=20, ge=1, le=100, description="조회 개수"),
    cursor: str | None = Query(default=None, description="페이징 커서"),
) -> ChatListResponse:
    """사용자의 채팅 목록을 조회합니다.

    사이드바에 표시되는 대화 목록을 반환합니다.
    최근 메시지 순으로 정렬됩니다.
    """
    chats, next_cursor = await repo.get_chats_by_user(
        user_id=UUID(user.user_id),
        limit=limit,
        cursor=cursor,
    )

    return ChatListResponse(
        chats=[ChatSummary.from_entity(c) for c in chats],
        next_cursor=next_cursor,
    )


@router.post(
    "",
    response_model=CreateChatResponse,
    status_code=201,
    summary="새 채팅 생성",
)
async def create_chat(
    user: CurrentUser,
    repo: ChatRepositoryDep,
    payload: CreateChatRequest | None = None,
) -> CreateChatResponse:
    """새 채팅 세션을 생성합니다.

    사용자가 '새 대화' 버튼을 클릭했을 때 호출됩니다.
    """
    chat = Chat(
        user_id=UUID(user.user_id),
        title=payload.title if payload else None,
    )
    created = await repo.create_chat(chat)

    logger.info(
        "chat_created",
        extra={"chat_id": str(created.id), "user_id": user.user_id},
    )

    return CreateChatResponse(
        id=str(created.id),
        title=created.title,
        created_at=created.created_at,
    )


@router.get(
    "/{chat_id}",
    response_model=ChatDetailResponse,
    summary="채팅 상세 조회",
)
async def get_chat(
    chat_id: UUID,
    user: CurrentUser,
    repo: ChatRepositoryDep,
    limit: int = Query(default=50, ge=1, le=200, description="메시지 조회 개수"),
    before: str | None = Query(default=None, description="이 시간 이전 메시지"),
) -> ChatDetailResponse:
    """채팅 상세 정보와 메시지 목록을 조회합니다.

    사용자가 사이드바에서 채팅을 선택했을 때 호출됩니다.
    """
    # 채팅 존재 확인 및 권한 검증
    chat = await repo.get_chat_by_id(chat_id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    if str(chat.user_id) != user.user_id:
        raise HTTPException(status_code=403, detail="Access denied")

    # 메시지 조회
    messages, has_more = await repo.get_messages_by_chat(
        chat_id=chat_id,
        limit=limit,
        before=before,
    )

    return ChatDetailResponse(
        id=str(chat.id),
        title=chat.title,
        messages=[MessageResponse.from_entity(m) for m in messages],
        has_more=has_more,
        created_at=chat.created_at,
    )


@router.delete(
    "/{chat_id}",
    response_model=DeleteChatResponse,
    summary="채팅 삭제",
)
async def delete_chat(
    chat_id: UUID,
    user: CurrentUser,
    repo: ChatRepositoryDep,
) -> DeleteChatResponse:
    """채팅을 삭제합니다 (soft delete).

    사용자가 채팅을 삭제했을 때 호출됩니다.
    실제 데이터는 유지되며 is_deleted 플래그만 변경됩니다.
    """
    # 채팅 존재 확인 및 권한 검증
    chat = await repo.get_chat_by_id(chat_id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    if str(chat.user_id) != user.user_id:
        raise HTTPException(status_code=403, detail="Access denied")

    success = await repo.delete_chat(chat_id)

    logger.info(
        "chat_deleted",
        extra={"chat_id": str(chat_id), "user_id": user.user_id, "success": success},
    )

    return DeleteChatResponse(success=success)


# ─────────────────────────────────────────────────────────────────────────────
# Message Endpoints
# ─────────────────────────────────────────────────────────────────────────────


@router.post(
    "/{chat_id}/messages",
    response_model=SendMessageResponse,
    summary="메시지 전송",
)
async def send_message(
    chat_id: UUID,
    payload: SendMessageRequest,
    user: CurrentUser,
    repo: ChatRepositoryDep,
    command: SubmitCommandDep,
) -> SendMessageResponse:
    """채팅에 새 메시지를 전송합니다.

    Eventual Consistency:
    - DB 저장은 하지 않음 (Worker 완료 시 배치 저장)
    - 채팅 존재/권한만 확인 후 Worker에 작업 제출
    - 클라이언트는 stream_url로 SSE 연결하여 응답 수신
    """
    if not payload.message.strip():
        raise HTTPException(status_code=400, detail="message is required")

    # 채팅 존재 확인 및 권한 검증
    chat = await repo.get_chat_by_id(chat_id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    if str(chat.user_id) != user.user_id:
        raise HTTPException(status_code=403, detail="Access denied")

    # Worker에 작업 제출 (DB 저장은 Worker 완료 시 배치로)
    user_location = None
    if payload.user_location is not None:
        user_location = {
            "latitude": payload.user_location.latitude,
            "longitude": payload.user_location.longitude,
        }

    request = SubmitChatRequest(
        session_id=str(chat_id),  # chat_id를 session_id로 사용
        user_id=user.user_id,
        message=payload.message,
        image_url=str(payload.image_url) if payload.image_url else None,
        user_location=user_location,
        model=payload.model,
    )

    response = await command.execute(request)

    logger.info(
        "message_submitted",
        extra={
            "chat_id": str(chat_id),
            "job_id": response.job_id,
            "user_id": user.user_id,
        },
    )

    return SendMessageResponse(
        job_id=response.job_id,
        stream_url=response.stream_url,
        status=response.status,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Human-in-the-Loop Endpoint
# ─────────────────────────────────────────────────────────────────────────────


@router.post(
    "/{job_id}/input",
    response_model=UserInputResponse,
    summary="추가 입력 제출 (Human-in-the-Loop)",
)
async def submit_user_input(
    job_id: str,
    payload: UserInputRequest,
    redis=Depends(get_async_redis),
) -> UserInputResponse:
    """진행 중인 작업에 추가 입력을 제출합니다.

    Human-in-the-Loop 패턴:
    1. Worker가 needs_input 이벤트 발행 (SSE)
    2. Frontend가 입력 수집 (예: Geolocation API)
    3. 이 엔드포인트로 입력 전송
    4. Worker가 Redis Pub/Sub로 입력 수신 후 계속 진행
    """
    channel = f"chat:input:{job_id}"

    message = json.dumps({
        "type": payload.type,
        "data": payload.data,
        "timestamp": datetime.utcnow().isoformat(),
    })

    await redis.publish(channel, message)

    logger.info(
        "user_input_submitted",
        extra={
            "job_id": job_id,
            "input_type": payload.type,
        },
    )

    return UserInputResponse(status="received", job_id=job_id)
