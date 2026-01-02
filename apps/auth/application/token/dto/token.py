"""Token DTOs."""

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class LogoutRequest:
    """로그아웃 요청."""

    access_token: str | None = None
    refresh_token: str | None = None


@dataclass(frozen=True, slots=True)
class RefreshTokensRequest:
    """토큰 갱신 요청."""

    refresh_token: str


@dataclass(frozen=True, slots=True)
class RefreshTokensResponse:
    """토큰 갱신 응답."""

    user_id: UUID
    access_token: str
    refresh_token: str
    access_expires_at: int
    refresh_expires_at: int
