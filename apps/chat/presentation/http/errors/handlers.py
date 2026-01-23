"""Exception Handlers.

도메인/애플리케이션 예외를 HTTP 응답으로 변환합니다.
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from chat.application.common.exceptions.auth import UnauthorizedError
from chat.application.common.exceptions.base import ApplicationError
from chat.application.common.exceptions.validation import MessageRequiredError
from chat.domain.exceptions.base import DomainError
from chat.domain.exceptions.chat import ChatAccessDeniedError, ChatNotFoundError


def register_exception_handlers(app: FastAPI) -> None:
    """예외 핸들러 등록."""

    @app.exception_handler(UnauthorizedError)
    async def unauthorized_handler(request: Request, exc: UnauthorizedError):
        return JSONResponse(
            status_code=401,
            content={"detail": exc.message, "code": "UNAUTHORIZED"},
        )

    @app.exception_handler(ChatNotFoundError)
    async def chat_not_found_handler(request: Request, exc: ChatNotFoundError):
        return JSONResponse(
            status_code=404,
            content={"detail": exc.message, "code": "CHAT_NOT_FOUND"},
        )

    @app.exception_handler(ChatAccessDeniedError)
    async def chat_access_denied_handler(request: Request, exc: ChatAccessDeniedError):
        return JSONResponse(
            status_code=403,
            content={"detail": exc.message, "code": "CHAT_ACCESS_DENIED"},
        )

    @app.exception_handler(MessageRequiredError)
    async def message_required_handler(request: Request, exc: MessageRequiredError):
        return JSONResponse(
            status_code=400,
            content={"detail": exc.message, "code": "MESSAGE_REQUIRED"},
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
