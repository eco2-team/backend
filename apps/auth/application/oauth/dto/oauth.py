"""OAuth DTOs."""

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class OAuthAuthorizeRequest:
    """OAuth 인증 요청."""

    provider: str
    redirect_uri: str | None = None
    state: str | None = None
    device_id: str | None = None
    frontend_origin: str | None = None


@dataclass(frozen=True, slots=True)
class OAuthAuthorizeResponse:
    """OAuth 인증 응답."""

    authorization_url: str
    state: str


@dataclass(frozen=True, slots=True)
class OAuthCallbackRequest:
    """OAuth 콜백 요청."""

    provider: str
    code: str
    state: str
    redirect_uri: str | None = None
    user_agent: str | None = None
    ip_address: str | None = None
    frontend_origin: str | None = None  # X-Frontend-Origin 헤더에서


@dataclass(frozen=True, slots=True)
class OAuthCallbackResponse:
    """OAuth 콜백 응답."""

    user_id: UUID
    access_token: str
    refresh_token: str
    access_expires_at: int
    refresh_expires_at: int
    frontend_origin: str | None = None
