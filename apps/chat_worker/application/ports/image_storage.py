"""Image Storage Port - 이미지 업로드 추상화.

생성된 이미지를 Object Storage에 업로드하고 CDN URL을 반환합니다.

Clean Architecture:
- Port: 이 파일 (추상 인터페이스)
- Adapter: infrastructure/integrations/image/client.py (gRPC 구현)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class ImageUploadResult:
    """이미지 업로드 결과."""

    success: bool
    cdn_url: str | None = None  # 성공 시 CDN URL
    key: str | None = None  # S3 오브젝트 키
    error: str | None = None  # 실패 시 에러 메시지


class ImageStoragePort(ABC):
    """이미지 저장소 Port.

    생성된 이미지 바이트를 Object Storage에 업로드합니다.
    """

    @abstractmethod
    async def upload_bytes(
        self,
        image_data: bytes,
        content_type: str = "image/png",
        channel: str = "generated",
        uploader_id: str = "system",
        metadata: dict[str, str] | None = None,
    ) -> ImageUploadResult:
        """이미지 바이트를 업로드합니다.

        Args:
            image_data: 이미지 바이트 데이터
            content_type: MIME 타입 (기본 image/png)
            channel: 채널 (기본 generated)
            uploader_id: 업로더 ID (기본 system)
            metadata: 추가 메타데이터

        Returns:
            ImageUploadResult: 업로드 결과 (cdn_url 포함)
        """
        ...

    @abstractmethod
    async def close(self) -> None:
        """연결을 종료합니다."""
        ...
