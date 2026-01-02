"""Auth HTTP Schemas."""

from datetime import datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, Field
from uuid import UUID


DataT = TypeVar("DataT")


class SuccessResponse(BaseModel, Generic[DataT]):
    """레거시 호환용 성공 응답 래퍼."""

    success: bool = Field(default=True, description="성공 여부")
    data: DataT = Field(..., description="응답 데이터")


class AuthorizeResponse(BaseModel):
    """OAuth 인증 URL 응답."""

    authorization_url: str = Field(..., description="OAuth 인증 URL")
    state: str = Field(..., description="CSRF 방지용 상태 값")


class AuthorizationData(BaseModel):
    """레거시 OAuth 인증 응답 데이터."""

    provider: str = Field(..., description="OAuth 프로바이더")
    state: str = Field(..., description="CSRF 방지용 상태 값")
    authorization_url: str = Field(..., description="OAuth 인증 URL")
    expires_at: datetime = Field(..., description="상태 만료 시간")


class AuthorizationSuccessResponse(SuccessResponse[AuthorizationData]):
    """레거시 호환용 OAuth 인증 응답."""

    pass


class CallbackRequest(BaseModel):
    """OAuth 콜백 요청."""

    code: str = Field(..., description="OAuth 인증 코드")
    state: str = Field(..., description="상태 값")
    redirect_uri: str | None = Field(None, description="리다이렉트 URI")


class UserResponse(BaseModel):
    """사용자 정보 응답."""

    id: UUID = Field(..., description="사용자 ID")
    username: str | None = Field(None, description="사용자명")
    nickname: str | None = Field(None, description="닉네임")
    email: str | None = Field(None, description="이메일")
    profile_image_url: str | None = Field(None, description="프로필 이미지 URL")
    provider: str = Field(..., description="OAuth 프로바이더")

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    """토큰 응답 (쿠키로 전달되므로 body는 간소화)."""

    message: str = Field(default="success", description="결과 메시지")


class LogoutData(BaseModel):
    """로그아웃 응답 데이터."""

    message: str = Field(default="Successfully logged out", description="결과 메시지")


class LogoutSuccessResponse(SuccessResponse[LogoutData]):
    """레거시 호환용 로그아웃 응답."""

    pass
