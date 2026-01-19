"""Image gRPC Servicer.

내부 서비스에서 이미지를 S3에 업로드할 때 사용합니다.

RPC Methods:
- UploadBytes: 바이트 데이터를 S3에 업로드하고 CDN URL 반환
"""

from __future__ import annotations

import asyncio
import logging
from functools import partial
from typing import TYPE_CHECKING
from uuid import uuid4

import grpc

from images.proto import image_pb2, image_pb2_grpc

if TYPE_CHECKING:
    from botocore.client import BaseClient

    from images.core import Settings

logger = logging.getLogger(__name__)

# 허용된 Content-Type
ALLOWED_CONTENT_TYPES = frozenset(
    {
        "image/png",
        "image/jpeg",
        "image/jpg",
        "image/gif",
        "image/webp",
    }
)

# Content-Type → 확장자 매핑
CONTENT_TYPE_TO_EXT = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/gif": ".gif",
    "image/webp": ".webp",
}

# 최대 이미지 크기 (10MB)
MAX_IMAGE_SIZE = 10 * 1024 * 1024


class ImageServicer(image_pb2_grpc.ImageServiceServicer):
    """Image gRPC Servicer.

    S3에 직접 이미지를 업로드합니다.
    """

    def __init__(
        self,
        s3_client: "BaseClient",
        settings: "Settings",
    ) -> None:
        """Initialize.

        Args:
            s3_client: boto3 S3 클라이언트
            settings: 이미지 서비스 설정
        """
        self._s3 = s3_client
        self._settings = settings

    async def UploadBytes(
        self,
        request: image_pb2.UploadBytesRequest,
        context: grpc.aio.ServicerContext,
    ) -> image_pb2.UploadBytesResponse:
        """바이트 데이터를 S3에 업로드합니다.

        Args:
            request: 업로드 요청 (channel, image_data, content_type, uploader_id)
            context: gRPC 컨텍스트

        Returns:
            UploadBytesResponse: CDN URL, S3 키
        """
        try:
            # 1. 입력 검증
            if not request.image_data:
                return image_pb2.UploadBytesResponse(
                    success=False,
                    error="image_data is required",
                )

            # 크기 검증
            image_size = len(request.image_data)
            if image_size > MAX_IMAGE_SIZE:
                return image_pb2.UploadBytesResponse(
                    success=False,
                    error=f"Image too large: {image_size} bytes > {MAX_IMAGE_SIZE} bytes",
                )

            if request.content_type not in ALLOWED_CONTENT_TYPES:
                return image_pb2.UploadBytesResponse(
                    success=False,
                    error=f"Invalid content_type: {request.content_type}",
                )

            channel = request.channel or "generated"

            # 2. S3 키 생성
            ext = CONTENT_TYPE_TO_EXT.get(request.content_type, ".bin")
            identifier = uuid4().hex
            key = f"{channel}/{identifier}{ext}"

            # 3. S3 업로드 (비동기 - 이벤트 루프 블로킹 방지)
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(
                None,
                partial(
                    self._s3.put_object,
                    Bucket=self._settings.s3_bucket,
                    Key=key,
                    Body=request.image_data,
                    ContentType=request.content_type,
                    Metadata={
                        "uploader_id": request.uploader_id or "system",
                        **dict(request.metadata),
                    },
                ),
            )

            # 4. CDN URL 생성
            cdn_domain = str(self._settings.cdn_domain).rstrip("/")
            cdn_url = f"{cdn_domain}/{key}"

            logger.info(
                "Image uploaded via gRPC",
                extra={
                    "channel": channel,
                    "key": key,
                    "content_type": request.content_type,
                    "size_bytes": len(request.image_data),
                    "uploader_id": request.uploader_id,
                },
            )

            return image_pb2.UploadBytesResponse(
                success=True,
                cdn_url=cdn_url,
                key=key,
            )

        except Exception as e:
            logger.exception(
                "Failed to upload image via gRPC",
                extra={
                    "channel": request.channel,
                    "content_type": request.content_type,
                    "error": str(e),
                },
            )
            return image_pb2.UploadBytesResponse(
                success=False,
                error=f"Upload failed: {str(e)}",
            )
