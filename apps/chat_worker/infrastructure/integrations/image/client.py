"""Image Storage gRPC Client - ImageStoragePort 구현체.

Images API의 gRPC 서비스를 호출하여 이미지를 S3에 업로드합니다.

Clean Architecture:
- Port: ImageStoragePort (application/ports/image_storage.py)
- Adapter: ImageStorageClient (이 파일)
"""

from __future__ import annotations

import logging

import grpc

from chat_worker.application.ports.image_storage import (
    ImageStoragePort,
    ImageUploadResult,
)
from chat_worker.infrastructure.integrations.image.proto import (
    ImageServiceStub,
    UploadBytesRequest,
)

logger = logging.getLogger(__name__)

# gRPC 타임아웃 (초) - 이미지 업로드는 시간이 걸릴 수 있음
DEFAULT_GRPC_TIMEOUT = 30.0


class ImageStorageClient(ImageStoragePort):
    """Image Storage gRPC 클라이언트.

    Images API의 gRPC 서비스를 호출하여 이미지를 S3에 업로드합니다.

    사용 예:
        client = ImageStorageClient()
        result = await client.upload_bytes(image_bytes, "image/png")
        if result.success:
            cdn_url = result.cdn_url
    """

    def __init__(
        self,
        host: str = "images-api",
        port: int = 50052,
    ):
        """Initialize.

        Args:
            host: Images API gRPC host
            port: Images API gRPC port
        """
        self._address = f"{host}:{port}"
        self._channel: grpc.aio.Channel | None = None
        self._stub: ImageServiceStub | None = None

    async def _get_stub(self) -> ImageServiceStub:
        """Lazy connection - 첫 호출 시 연결."""
        if self._channel is None:
            # 이미지 업로드를 위해 메시지 크기 제한 증가 (10MB)
            options = [
                ("grpc.max_send_message_length", 10 * 1024 * 1024),
                ("grpc.max_receive_message_length", 10 * 1024 * 1024),
            ]
            self._channel = grpc.aio.insecure_channel(self._address, options=options)
            self._stub = ImageServiceStub(self._channel)
            logger.info(
                "Image Storage gRPC channel created",
                extra={"address": self._address},
            )
        return self._stub

    async def upload_bytes(
        self,
        image_data: bytes,
        content_type: str = "image/png",
        channel: str = "generated",
        uploader_id: str = "system",
        metadata: dict[str, str] | None = None,
    ) -> ImageUploadResult:
        """이미지 바이트를 S3에 업로드합니다.

        gRPC로 Images API의 UploadBytes 호출.

        Args:
            image_data: 이미지 바이트 데이터
            content_type: MIME 타입 (기본 image/png)
            channel: 채널 (기본 generated)
            uploader_id: 업로더 ID (기본 system)
            metadata: 추가 메타데이터

        Returns:
            ImageUploadResult: 업로드 결과 (cdn_url 포함)
        """
        stub = await self._get_stub()

        request = UploadBytesRequest(
            channel=channel,
            image_data=image_data,
            content_type=content_type,
            uploader_id=uploader_id,
        )
        if metadata:
            request.metadata.update(metadata)

        try:
            response = await stub.UploadBytes(request, timeout=DEFAULT_GRPC_TIMEOUT)

            if response.success:
                logger.info(
                    "Image uploaded via gRPC",
                    extra={
                        "channel": channel,
                        "cdn_url": response.cdn_url,
                        "size_bytes": len(image_data),
                    },
                )
                return ImageUploadResult(
                    success=True,
                    cdn_url=response.cdn_url,
                    key=response.key,
                )
            else:
                logger.error(
                    "Image upload failed via gRPC",
                    extra={
                        "channel": channel,
                        "error": response.error,
                    },
                )
                return ImageUploadResult(
                    success=False,
                    error=response.error,
                )

        except grpc.aio.AioRpcError as e:
            logger.error(
                "Image Storage gRPC error",
                extra={
                    "channel": channel,
                    "code": e.code().name,
                    "details": e.details(),
                },
            )
            return ImageUploadResult(
                success=False,
                error=f"gRPC error: {e.code().name} - {e.details()}",
            )

    async def close(self) -> None:
        """연결 종료."""
        if self._channel:
            await self._channel.close()
            self._channel = None
            self._stub = None
            logger.info("Image Storage gRPC channel closed")
