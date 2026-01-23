"""Exception Handlers.

예외를 HTTP 응답으로 변환합니다.
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from sse_gateway.core.exceptions.validation import (
    InvalidJobIdError,
    UnsupportedServiceError,
)


def register_exception_handlers(app: FastAPI) -> None:
    """예외 핸들러 등록."""

    @app.exception_handler(InvalidJobIdError)
    async def invalid_job_id_handler(request: Request, exc: InvalidJobIdError):
        return JSONResponse(
            status_code=400,
            content={"detail": exc.message, "code": "INVALID_JOB_ID"},
        )

    @app.exception_handler(UnsupportedServiceError)
    async def unsupported_service_handler(request: Request, exc: UnsupportedServiceError):
        return JSONResponse(
            status_code=400,
            content={"detail": exc.message, "code": "UNSUPPORTED_SERVICE"},
        )
