"""Exception Handlers.

도메인/애플리케이션 예외를 HTTP 응답으로 변환합니다.
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from apps.auth.application.common.exceptions import ApplicationError
from apps.auth.application.oauth.exceptions import InvalidStateError, OAuthProviderError
from apps.auth.application.token.exceptions import AuthenticationError
from apps.auth.domain.exceptions.auth import (
    InvalidTokenError,
    TokenExpiredError,
    TokenRevokedError,
    TokenTypeMismatchError,
)
from apps.auth.domain.exceptions.base import DomainError
from apps.auth.domain.exceptions.user import UserNotFoundError


def register_exception_handlers(app: FastAPI) -> None:
    """예외 핸들러 등록."""

    @app.exception_handler(UserNotFoundError)
    async def user_not_found_handler(request: Request, exc: UserNotFoundError):
        return JSONResponse(
            status_code=404,
            content={"detail": exc.message, "code": "USER_NOT_FOUND"},
        )

    @app.exception_handler(InvalidTokenError)
    async def invalid_token_handler(request: Request, exc: InvalidTokenError):
        return JSONResponse(
            status_code=401,
            content={"detail": exc.message, "code": "INVALID_TOKEN"},
        )

    @app.exception_handler(TokenExpiredError)
    async def token_expired_handler(request: Request, exc: TokenExpiredError):
        return JSONResponse(
            status_code=401,
            content={"detail": exc.message, "code": "TOKEN_EXPIRED"},
        )

    @app.exception_handler(TokenTypeMismatchError)
    async def token_type_mismatch_handler(request: Request, exc: TokenTypeMismatchError):
        return JSONResponse(
            status_code=400,
            content={"detail": exc.message, "code": "TOKEN_TYPE_MISMATCH"},
        )

    @app.exception_handler(TokenRevokedError)
    async def token_revoked_handler(request: Request, exc: TokenRevokedError):
        return JSONResponse(
            status_code=401,
            content={"detail": exc.message, "code": "TOKEN_REVOKED"},
        )

    @app.exception_handler(AuthenticationError)
    async def authentication_error_handler(request: Request, exc: AuthenticationError):
        return JSONResponse(
            status_code=401,
            content={"detail": exc.message, "code": "AUTHENTICATION_FAILED"},
        )

    @app.exception_handler(InvalidStateError)
    async def invalid_state_handler(request: Request, exc: InvalidStateError):
        return JSONResponse(
            status_code=400,
            content={"detail": exc.message, "code": "INVALID_STATE"},
        )

    @app.exception_handler(OAuthProviderError)
    async def oauth_provider_handler(request: Request, exc: OAuthProviderError):
        return JSONResponse(
            status_code=502,
            content={"detail": exc.message, "code": "OAUTH_PROVIDER_ERROR"},
        )

    @app.exception_handler(DomainError)
    async def domain_error_handler(request: Request, exc: DomainError):
        return JSONResponse(
            status_code=400,
            content={"detail": exc.message, "code": "DOMAIN_ERROR"},
        )

    @app.exception_handler(ApplicationError)
    async def application_error_handler(request: Request, exc: ApplicationError):
        return JSONResponse(
            status_code=400,
            content={"detail": exc.message, "code": "APPLICATION_ERROR"},
        )
