"""Exception Handlers.

도메인/애플리케이션 예외를 HTTP 응답으로 변환합니다.
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from location.application.common.exceptions.base import ApplicationError
from location.application.common.exceptions.validation import (
    InvalidPickupCategoryError,
    InvalidStoreCategoryError,
    KakaoApiUnavailableError,
    ServiceUnavailableError,
)
from location.domain.exceptions.base import DomainError
from location.domain.exceptions.location import LocationNotFoundError


def register_exception_handlers(app: FastAPI) -> None:
    """예외 핸들러 등록."""

    @app.exception_handler(KakaoApiUnavailableError)
    async def kakao_api_unavailable_handler(request: Request, exc: KakaoApiUnavailableError):
        return JSONResponse(
            status_code=503,
            content={"detail": exc.message, "code": "KAKAO_API_UNAVAILABLE"},
        )

    @app.exception_handler(ServiceUnavailableError)
    async def service_unavailable_handler(request: Request, exc: ServiceUnavailableError):
        return JSONResponse(
            status_code=503,
            content={"detail": exc.message, "code": "SERVICE_UNAVAILABLE"},
        )

    @app.exception_handler(LocationNotFoundError)
    async def location_not_found_handler(request: Request, exc: LocationNotFoundError):
        return JSONResponse(
            status_code=404,
            content={"detail": exc.message, "code": "LOCATION_NOT_FOUND"},
        )

    @app.exception_handler(InvalidStoreCategoryError)
    async def invalid_store_category_handler(request: Request, exc: InvalidStoreCategoryError):
        return JSONResponse(
            status_code=400,
            content={"detail": exc.message, "code": "INVALID_STORE_CATEGORY"},
        )

    @app.exception_handler(InvalidPickupCategoryError)
    async def invalid_pickup_category_handler(request: Request, exc: InvalidPickupCategoryError):
        return JSONResponse(
            status_code=400,
            content={"detail": exc.message, "code": "INVALID_PICKUP_CATEGORY"},
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
