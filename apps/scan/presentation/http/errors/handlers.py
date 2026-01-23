"""Exception Handlers.

도메인/애플리케이션 예외를 HTTP 응답으로 변환합니다.
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from scan.application.common.exceptions.auth import UnauthorizedError
from scan.application.common.exceptions.base import ApplicationError
from scan.application.common.exceptions.validation import ImageUrlRequiredError
from scan.domain.exceptions.base import DomainError
from scan.domain.exceptions.scan import ResultNotFoundError, UnsupportedModelError


def register_exception_handlers(app: FastAPI) -> None:
    """예외 핸들러 등록."""

    @app.exception_handler(UnauthorizedError)
    async def unauthorized_handler(request: Request, exc: UnauthorizedError):
        return JSONResponse(
            status_code=401,
            content={"detail": exc.message, "code": "UNAUTHORIZED"},
        )

    @app.exception_handler(ResultNotFoundError)
    async def result_not_found_handler(request: Request, exc: ResultNotFoundError):
        return JSONResponse(
            status_code=404,
            content={"detail": exc.message, "code": "RESULT_NOT_FOUND"},
        )

    @app.exception_handler(ImageUrlRequiredError)
    async def image_url_required_handler(request: Request, exc: ImageUrlRequiredError):
        return JSONResponse(
            status_code=400,
            content={"detail": exc.message, "code": "IMAGE_URL_REQUIRED"},
        )

    @app.exception_handler(UnsupportedModelError)
    async def unsupported_model_handler(request: Request, exc: UnsupportedModelError):
        return JSONResponse(
            status_code=400,
            content={
                "detail": {
                    "error": "unsupported_model",
                    "message": exc.message,
                    "supported_models": exc.supported_models,
                },
                "code": "UNSUPPORTED_MODEL",
            },
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
