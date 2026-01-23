"""Exception Handlers.

도메인/서비스 예외를 HTTP 응답으로 변환합니다.
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from images.core.exceptions.auth import InvalidUserIdFormatError, MissingUserIdError
from images.core.exceptions.upload import UploaderMismatchError
from images.services.image import (
    PendingUploadChannelMismatchError,
    PendingUploadNotFoundError,
    PendingUploadPermissionDeniedError,
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

    @app.exception_handler(UploaderMismatchError)
    async def uploader_mismatch_handler(request: Request, exc: UploaderMismatchError):
        return JSONResponse(
            status_code=403,
            content={"detail": exc.message, "code": "UPLOADER_MISMATCH"},
        )

    @app.exception_handler(PendingUploadNotFoundError)
    async def upload_not_found_handler(request: Request, exc: PendingUploadNotFoundError):
        return JSONResponse(
            status_code=404,
            content={
                "detail": "Upload session not found or expired",
                "code": "UPLOAD_NOT_FOUND",
            },
        )

    @app.exception_handler(PendingUploadChannelMismatchError)
    async def channel_mismatch_handler(request: Request, exc: PendingUploadChannelMismatchError):
        return JSONResponse(
            status_code=400,
            content={
                "detail": "Channel does not match the original upload request",
                "code": "CHANNEL_MISMATCH",
            },
        )

    @app.exception_handler(PendingUploadPermissionDeniedError)
    async def upload_permission_denied_handler(
        request: Request, exc: PendingUploadPermissionDeniedError
    ):
        return JSONResponse(
            status_code=403,
            content={"detail": "Uploader mismatch", "code": "UPLOADER_MISMATCH"},
        )
