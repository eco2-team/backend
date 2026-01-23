"""Exception Handlers.

도메인/애플리케이션 예외를 HTTP 응답으로 변환합니다.
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from info.application.exceptions.validation import (
    ApplicationError,
    InvalidCategoryError,
    InvalidCursorFormatError,
    InvalidSourceError,
)


def register_exception_handlers(app: FastAPI) -> None:
    """예외 핸들러 등록."""

    @app.exception_handler(InvalidCategoryError)
    async def invalid_category_handler(request: Request, exc: InvalidCategoryError):
        return JSONResponse(
            status_code=400,
            content={"detail": exc.message, "code": "INVALID_CATEGORY"},
        )

    @app.exception_handler(InvalidSourceError)
    async def invalid_source_handler(request: Request, exc: InvalidSourceError):
        return JSONResponse(
            status_code=400,
            content={"detail": exc.message, "code": "INVALID_SOURCE"},
        )

    @app.exception_handler(InvalidCursorFormatError)
    async def invalid_cursor_format_handler(request: Request, exc: InvalidCursorFormatError):
        return JSONResponse(
            status_code=400,
            content={"detail": exc.message, "code": "INVALID_CURSOR_FORMAT"},
        )

    @app.exception_handler(ApplicationError)
    async def application_error_handler(request: Request, exc: ApplicationError):
        return JSONResponse(
            status_code=400,
            content={"detail": exc.message, "code": "APPLICATION_ERROR"},
        )
