"""Chat API Controller.

메인 API 엔드포인트:
- POST /chat: 비동기 채팅 작업 제출
- POST /chat/{job_id}/input: Human-in-the-Loop 추가 입력
- GET /chat/{job_id}/events: SSE 스트리밍

scan 패턴을 따라 Taskiq에 작업 위임.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field, HttpUrl

from chat.application.chat.commands import SubmitChatRequest
from chat.setup.dependencies import SubmitCommandDep, get_async_redis

router = APIRouter(prefix="/chat", tags=["chat"])
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Schemas
# ─────────────────────────────────────────────────────────────────────────────


class UserLocation(BaseModel):
    """사용자 위치 (Geolocation API 형식)."""

    latitude: float = Field(description="위도")
    longitude: float = Field(description="경도")


class ChatRequest(BaseModel):
    """채팅 요청 스키마."""

    session_id: str = Field(description="세션 ID (대화 스레드 식별)")
    message: str = Field(description="사용자 메시지")
    image_url: HttpUrl | None = Field(
        default=None,
        description="첨부 이미지 URL",
    )
    user_location: UserLocation | None = Field(
        default=None,
        description="사용자 위치 (주변 검색용, Geolocation API 형식)",
    )
    model: str | None = Field(
        default=None,
        description="LLM 모델명 (미지정 시 기본값)",
        examples=["gpt-5.2-turbo", "gemini-3-flash-preview"],
    )


class ChatSubmitResponse(BaseModel):
    """채팅 제출 응답 스키마."""

    job_id: str = Field(description="작업 ID (UUID)")
    session_id: str = Field(description="세션 ID")
    stream_url: str = Field(description="SSE 스트리밍 URL")
    status: str = Field(default="queued", description="현재 상태")


class UserInputRequest(BaseModel):
    """Human-in-the-Loop 추가 입력 스키마.

    needs_input 이벤트 수신 후 사용자 입력을 전송합니다.
    """

    type: str = Field(
        description="입력 타입 (location, confirmation, cancel)",
        examples=["location", "confirmation", "cancel"],
    )
    data: dict[str, Any] | None = Field(
        default=None,
        description="입력 데이터 (type에 따라 다름)",
        examples=[{"latitude": 37.5665, "longitude": 126.9780}],
    )


class UserInputResponse(BaseModel):
    """추가 입력 응답 스키마."""

    status: str = Field(default="received")
    job_id: str


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
# Endpoints
# ─────────────────────────────────────────────────────────────────────────────


@router.post(
    "",
    response_model=ChatSubmitResponse,
    summary="Submit chat message for async processing",
)
async def submit_chat(
    payload: ChatRequest,
    user: CurrentUser,
    command: SubmitCommandDep,
) -> ChatSubmitResponse:
    """채팅 메시지를 비동기로 제출합니다.

    클라이언트 흐름:
    1. 이 엔드포인트 호출 → job_id, stream_url 수신
    2. stream_url로 SSE 연결 → 실시간 응답 수신
    """
    if not payload.message.strip():
        raise HTTPException(status_code=400, detail="message is required")

    # Geolocation API 형식 유지: { latitude, longitude }
    user_location = None
    if payload.user_location is not None:
        user_location = {
            "latitude": payload.user_location.latitude,
            "longitude": payload.user_location.longitude,
        }

    request = SubmitChatRequest(
        session_id=payload.session_id,
        user_id=user.user_id,
        message=payload.message,
        image_url=str(payload.image_url) if payload.image_url else None,
        user_location=user_location,
        model=payload.model,
    )

    response = await command.execute(request)

    return ChatSubmitResponse(
        job_id=response.job_id,
        session_id=response.session_id,
        stream_url=response.stream_url,
        status=response.status,
    )


@router.post(
    "/{job_id}/input",
    response_model=UserInputResponse,
    summary="Submit additional input (Human-in-the-Loop)",
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

    사용 예:
    - Location: 위치 권한 요청 → { type: "location", data: { latitude, longitude } }
    - Cancel: 사용자 취소 → { type: "cancel" }
    """
    channel = f"chat:input:{job_id}"

    message = json.dumps({
        "type": payload.type,
        "data": payload.data,
        "timestamp": datetime.utcnow().isoformat(),
    })

    await redis.publish(channel, message)

    logger.info(
        "User input submitted",
        extra={
            "job_id": job_id,
            "input_type": payload.type,
        },
    )

    return UserInputResponse(status="received", job_id=job_id)


# SSE 엔드포인트는 chat/presentation/http/sse.py로 이동
# GET /{job_id}/events → sse.router에서 처리
