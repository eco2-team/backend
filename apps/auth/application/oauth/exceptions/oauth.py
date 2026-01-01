"""OAuth Exceptions."""

from apps.auth.application.common.exceptions.base import ApplicationError


class InvalidStateError(ApplicationError):
    """OAuth 상태 검증 실패."""

    def __init__(self, reason: str = "Invalid or expired state") -> None:
        super().__init__(reason)


class OAuthProviderError(ApplicationError):
    """OAuth 프로바이더 오류."""

    def __init__(self, provider: str, reason: str) -> None:
        self.provider = provider
        super().__init__(f"OAuth provider error ({provider}): {reason}")
