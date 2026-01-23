"""Exception Handlers.

도메인/애플리케이션 예외를 HTTP 응답으로 변환합니다.
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from users.application.common.exceptions.auth import (
    InvalidUserIdFormatError,
    MissingUserIdError,
)
from users.application.common.exceptions.base import ApplicationError
from users.application.profile.exceptions import (
    InvalidPhoneNumberError,
    NoChangesProvidedError,
    UserNotFoundError,
)


def register_exception_handlers(app: FastAPI) -> None:
    """예외 핸들러 등록."""

    @app.exception_handler(MissingUserIdError)
    async def missing_user_id_handler(request: Request, exc: MissingUserIdError):
        return JSONResponse(
            status_code=401,
            content={"detail": exc.message, "code": "MISSING_USER_ID"},
        )

    @app.exception_handler(InvalidUserIdFormatError)
    async def invalid_user_id_format_handler(request: Request, exc: InvalidUserIdFormatError):
        return JSONResponse(
            status_code=401,
            content={"detail": exc.message, "code": "INVALID_USER_ID_FORMAT"},
        )

    @app.exception_handler(UserNotFoundError)
    async def user_not_found_handler(request: Request, exc: UserNotFoundError):
        return JSONResponse(
            status_code=404,
            content={"detail": exc.message, "code": "USER_NOT_FOUND"},
        )

    @app.exception_handler(NoChangesProvidedError)
    async def no_changes_provided_handler(request: Request, exc: NoChangesProvidedError):
        return JSONResponse(
            status_code=422,
            content={"detail": exc.message, "code": "NO_CHANGES_PROVIDED"},
        )

    @app.exception_handler(InvalidPhoneNumberError)
    async def invalid_phone_number_handler(request: Request, exc: InvalidPhoneNumberError):
        return JSONResponse(
            status_code=422,
            content={"detail": exc.message, "code": "INVALID_PHONE_NUMBER"},
        )

    @app.exception_handler(ApplicationError)
    async def application_error_handler(request: Request, exc: ApplicationError):
        return JSONResponse(
            status_code=400,
            content={"detail": exc.message, "code": "APPLICATION_ERROR"},
        )
