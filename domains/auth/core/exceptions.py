"""Custom exception handlers for standardized error responses."""

import logging

from fastapi import HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from domains.auth.application.schemas.common import ErrorDetail, ErrorResponse

logger = logging.getLogger(__name__)


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Handle HTTPException with standardized error response."""
    # HTTP 상태 코드를 에러 코드로 매핑
    error_code_map = {
        status.HTTP_400_BAD_REQUEST: "BAD_REQUEST",
        status.HTTP_401_UNAUTHORIZED: "UNAUTHORIZED",
        status.HTTP_403_FORBIDDEN: "FORBIDDEN",
        status.HTTP_404_NOT_FOUND: "NOT_FOUND",
        status.HTTP_409_CONFLICT: "CONFLICT",
        status.HTTP_422_UNPROCESSABLE_ENTITY: "VALIDATION_ERROR",
        status.HTTP_500_INTERNAL_SERVER_ERROR: "INTERNAL_SERVER_ERROR",
    }

    error_code = error_code_map.get(exc.status_code, "UNKNOWN_ERROR")

    # 에러 로깅 (trace.id 자동 포함)
    log_level = logging.WARNING if exc.status_code < 500 else logging.ERROR
    logger.log(
        log_level,
        f"HTTP {exc.status_code} {error_code}: {exc.detail}",
        extra={
            "http.request.method": request.method,
            "url.path": request.url.path,
            "http.response.status_code": exc.status_code,
            "error.code": error_code,
        },
    )

    error_response = ErrorResponse(
        error=ErrorDetail(
            code=error_code,
            message=str(exc.detail),
        )
    )

    return JSONResponse(
        status_code=exc.status_code,
        content=error_response.model_dump(),
    )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError | ValidationError
) -> JSONResponse:
    """Handle validation errors with standardized error response."""
    # 첫 번째 validation error를 기본 메시지로 사용
    errors = exc.errors() if isinstance(exc, (RequestValidationError, ValidationError)) else []
    first_error = errors[0] if errors else {}

    field = (
        ".".join(str(loc) for loc in first_error.get("loc", [])) if first_error.get("loc") else None
    )
    message = first_error.get("msg", "Validation error") if first_error else "Validation error"

    # Validation 에러 로깅 (trace.id 자동 포함)
    logger.warning(
        f"Validation error: {message}",
        extra={
            "http.request.method": request.method,
            "url.path": request.url.path,
            "http.response.status_code": 422,
            "error.code": "VALIDATION_ERROR",
            "error.field": field,
        },
    )

    error_response = ErrorResponse(
        error=ErrorDetail(
            code="VALIDATION_ERROR",
            message=message,
            field=field,
        )
    )

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=error_response.model_dump(),
    )


async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle all other exceptions with standardized error response."""
    # 예상치 못한 에러 로깅 (trace.id 자동 포함)
    logger.exception(
        f"Unexpected error: {type(exc).__name__}",
        extra={
            "http.request.method": request.method,
            "url.path": request.url.path,
            "http.response.status_code": 500,
            "error.code": "INTERNAL_SERVER_ERROR",
            "error.type": type(exc).__name__,
        },
    )

    error_response = ErrorResponse(
        error=ErrorDetail(
            code="INTERNAL_SERVER_ERROR",
            message="An unexpected error occurred",
        )
    )

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=error_response.model_dump(),
    )
