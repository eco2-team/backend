"""Unit tests for ImageService."""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

# apps/ 디렉토리를 PYTHONPATH에 추가 (from images.* 가능하게)
APPS_DIR = Path(__file__).resolve().parents[2]
if str(APPS_DIR) not in sys.path:
    sys.path.insert(0, str(APPS_DIR))

from images.core.config import Settings  # noqa: E402
from images.schemas.image import ImageChannel, ImageUploadRequest  # noqa: E402
from images.services.image import (  # noqa: E402
    ImageService,
    PendingUpload,
    PendingUploadChannelMismatchError,
    PendingUploadNotFoundError,
    PendingUploadPermissionDeniedError,
)


@pytest.fixture
def test_settings():
    """Test settings."""
    return Settings(
        s3_bucket="test-bucket",
        cdn_domain="https://cdn.test.com",
        presign_expires_seconds=300,
        upload_state_ttl=300,
        aws_region="ap-northeast-2",
    )


@pytest.fixture
def mock_s3_client():
    """Mock S3 client."""
    client = MagicMock()
    client.generate_presigned_url = MagicMock(return_value="https://s3.presigned.url")
    return client


@pytest.fixture
def mock_redis():
    """Mock Redis client."""
    redis = MagicMock()
    redis.setex = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    redis.delete = AsyncMock()
    return redis


@pytest.fixture
def service(test_settings, mock_s3_client, mock_redis):
    """Create ImageService with mocked dependencies."""
    return ImageService(
        settings=test_settings,
        s3_client=mock_s3_client,
        redis_client=mock_redis,
    )


class TestPendingUpload:
    """Tests for PendingUpload data class."""

    def test_to_json_and_from_json(self):
        """JSON 직렬화/역직렬화가 올바르게 동작합니다."""
        pending = PendingUpload(
            channel=ImageChannel.scan,
            uploader_id="user-123",
            metadata={"key": "value"},
            content_type="image/png",
            cdn_url="https://cdn.test.com/image.png",
        )

        json_str = pending.to_json()
        restored = PendingUpload.from_json(json_str)

        assert restored.channel == ImageChannel.scan
        assert restored.uploader_id == "user-123"
        assert restored.metadata == {"key": "value"}
        assert restored.content_type == "image/png"

    def test_from_json_with_empty_metadata(self):
        """metadata가 없어도 빈 dict로 복원됩니다."""
        import json

        data = {
            "channel": "scan",
            "uploader_id": "user-123",
            "content_type": "image/png",
            "cdn_url": "https://cdn.test.com/image.png",
        }

        restored = PendingUpload.from_json(json.dumps(data))

        assert restored.metadata == {}


class TestCreateUploadUrl:
    """Tests for create_upload_url method."""

    @pytest.mark.asyncio
    async def test_creates_presigned_url(self, service, mock_s3_client):
        """Presigned URL을 생성합니다."""
        request = ImageUploadRequest(
            filename="test.png",
            content_type="image/png",
        )

        result = await service.create_upload_url(
            channel=ImageChannel.scan,
            request=request,
            uploader_id="user-123",
        )

        assert str(result.upload_url).startswith("https://s3.presigned.url")
        assert "scan/" in str(result.cdn_url)
        assert result.expires_in > 0  # Settings에서 설정된 값
        mock_s3_client.generate_presigned_url.assert_called_once()

    @pytest.mark.asyncio
    async def test_saves_pending_upload(self, service, mock_redis):
        """Pending upload을 Redis에 저장합니다."""
        request = ImageUploadRequest(
            filename="test.png",
            content_type="image/png",
            metadata={"scan_id": "123"},
        )

        await service.create_upload_url(
            channel=ImageChannel.scan,
            request=request,
            uploader_id="user-123",
        )

        mock_redis.setex.assert_called_once()


class TestFinalizeUpload:
    """Tests for finalize_upload method."""

    @pytest.mark.asyncio
    async def test_finalizes_upload(self, service, mock_redis):
        """업로드를 완료합니다."""
        from images.schemas.image import ImageUploadCallbackRequest

        pending = PendingUpload(
            channel=ImageChannel.scan,
            uploader_id="user-123",
            metadata={},
            content_type="image/png",
            cdn_url="https://cdn.test.com/scan/abc.png",
        )
        mock_redis.get = AsyncMock(return_value=pending.to_json())

        callback = ImageUploadCallbackRequest(
            key="scan/abc.png",
            etag="abc123",
        )

        result = await service.finalize_upload(
            channel=ImageChannel.scan,
            request=callback,
            uploader_id="user-123",
        )

        assert result.key == "scan/abc.png"
        assert "scan/abc.png" in str(result.cdn_url)
        mock_redis.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_raises_not_found(self, service, mock_redis):
        """Pending upload이 없으면 NotFoundError를 발생시킵니다."""
        from images.schemas.image import ImageUploadCallbackRequest

        mock_redis.get = AsyncMock(return_value=None)

        callback = ImageUploadCallbackRequest(
            key="scan/abc.png",
            etag="abc123",
        )

        with pytest.raises(PendingUploadNotFoundError):
            await service.finalize_upload(
                channel=ImageChannel.scan,
                request=callback,
                uploader_id="user-123",
            )

    @pytest.mark.asyncio
    async def test_raises_channel_mismatch(self, service, mock_redis):
        """채널이 다르면 ChannelMismatchError를 발생시킵니다."""
        from images.schemas.image import ImageUploadCallbackRequest

        pending = PendingUpload(
            channel=ImageChannel.chat,  # 다른 채널
            uploader_id="user-123",
            metadata={},
            content_type="image/png",
            cdn_url="https://cdn.test.com/chat/abc.png",
        )
        mock_redis.get = AsyncMock(return_value=pending.to_json())

        callback = ImageUploadCallbackRequest(
            key="chat/abc.png",
            etag="abc123",
        )

        with pytest.raises(PendingUploadChannelMismatchError):
            await service.finalize_upload(
                channel=ImageChannel.scan,  # 요청은 scan
                request=callback,
                uploader_id="user-123",
            )

    @pytest.mark.asyncio
    async def test_raises_permission_denied(self, service, mock_redis):
        """다른 사용자의 업로드면 PermissionDeniedError를 발생시킵니다."""
        from images.schemas.image import ImageUploadCallbackRequest

        pending = PendingUpload(
            channel=ImageChannel.scan,
            uploader_id="user-456",  # 다른 사용자
            metadata={},
            content_type="image/png",
            cdn_url="https://cdn.test.com/scan/abc.png",
        )
        mock_redis.get = AsyncMock(return_value=pending.to_json())

        callback = ImageUploadCallbackRequest(
            key="scan/abc.png",
            etag="abc123",
        )

        with pytest.raises(PendingUploadPermissionDeniedError):
            await service.finalize_upload(
                channel=ImageChannel.scan,
                request=callback,
                uploader_id="user-123",  # 요청은 user-123
            )


class TestBuildObjectKey:
    """Tests for _build_object_key method."""

    def test_builds_key_with_extension(self, service):
        """확장자를 포함한 key를 생성합니다."""
        key = service._build_object_key("scan", "test.png")

        assert key.startswith("scan/")
        assert key.endswith(".png")

    def test_builds_key_without_extension(self, service):
        """확장자가 없으면 .bin을 사용합니다."""
        key = service._build_object_key("scan", "test")

        assert key.endswith(".bin")

    def test_sanitizes_extension(self, service):
        """확장자를 소문자로 변환합니다."""
        key = service._build_object_key("scan", "test.PNG")

        assert key.endswith(".png")


class TestComposeCdnUrl:
    """Tests for _compose_cdn_url method."""

    def test_composes_url(self, service):
        """CDN URL을 생성합니다."""
        url = service._compose_cdn_url("scan/abc123.png")

        # Settings에서 주입된 cdn_domain 사용
        assert url.endswith("/scan/abc123.png")
        assert str(service.settings.cdn_domain) in url


class TestMetrics:
    """Tests for metrics method."""

    @pytest.mark.asyncio
    async def test_returns_metrics(self, service):
        """메트릭스를 반환합니다."""
        result = await service.metrics()

        assert "bucket" in result
        assert "cdn_domain" in result
        assert "presign_expires_seconds" in result
        assert "allowed_channels" in result
        assert "auth_required" in result
