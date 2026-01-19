"""Unit tests for ImageServicer (gRPC)."""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# apps/ 디렉토리를 PYTHONPATH에 추가 (from images.* 가능하게)
APPS_DIR = Path(__file__).resolve().parents[2]
if str(APPS_DIR) not in sys.path:
    sys.path.insert(0, str(APPS_DIR))

from images.core.config import Settings  # noqa: E402
from images.presentation.grpc.servicers.image_servicer import (  # noqa: E402
    ALLOWED_CONTENT_TYPES,
    MAX_IMAGE_SIZE,
    ImageServicer,
)
from images.proto import image_pb2  # noqa: E402


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
def mock_session():
    """Mock aioboto3 session."""
    session = MagicMock()
    return session


@pytest.fixture
def servicer(mock_session, test_settings):
    """Create ImageServicer with mocked dependencies."""
    return ImageServicer(
        session=mock_session,
        settings=test_settings,
    )


@pytest.fixture
def mock_grpc_context():
    """Mock gRPC context."""
    return MagicMock()


class TestUploadBytesValidation:
    """Tests for UploadBytes input validation."""

    @pytest.mark.asyncio
    async def test_rejects_empty_image_data(self, servicer, mock_grpc_context):
        """빈 이미지 데이터를 거부합니다."""
        request = image_pb2.UploadBytesRequest(
            channel="generated",
            image_data=b"",
            content_type="image/png",
        )

        response = await servicer.UploadBytes(request, mock_grpc_context)

        assert response.success is False
        assert "image_data is required" in response.error

    @pytest.mark.asyncio
    async def test_rejects_oversized_image(self, servicer, mock_grpc_context):
        """크기 초과 이미지를 거부합니다."""
        large_data = b"x" * (MAX_IMAGE_SIZE + 1)
        request = image_pb2.UploadBytesRequest(
            channel="generated",
            image_data=large_data,
            content_type="image/png",
        )

        response = await servicer.UploadBytes(request, mock_grpc_context)

        assert response.success is False
        assert "too large" in response.error

    @pytest.mark.asyncio
    async def test_rejects_invalid_content_type(self, servicer, mock_grpc_context):
        """허용되지 않은 content_type을 거부합니다."""
        request = image_pb2.UploadBytesRequest(
            channel="generated",
            image_data=b"fake-image",
            content_type="application/pdf",
        )

        response = await servicer.UploadBytes(request, mock_grpc_context)

        assert response.success is False
        assert "Invalid content_type" in response.error


class TestUploadBytesSuccess:
    """Tests for successful UploadBytes."""

    @pytest.mark.asyncio
    async def test_uploads_image_successfully(self, mock_session, test_settings, mock_grpc_context):
        """이미지를 성공적으로 업로드합니다."""
        # Mock S3 client context manager
        mock_s3 = AsyncMock()
        mock_s3.put_object = AsyncMock()

        mock_client_cm = AsyncMock()
        mock_client_cm.__aenter__ = AsyncMock(return_value=mock_s3)
        mock_client_cm.__aexit__ = AsyncMock(return_value=None)

        mock_session.client = MagicMock(return_value=mock_client_cm)

        servicer = ImageServicer(session=mock_session, settings=test_settings)

        request = image_pb2.UploadBytesRequest(
            channel="generated",
            image_data=b"fake-png-data",
            content_type="image/png",
            uploader_id="chat_worker",
        )

        response = await servicer.UploadBytes(request, mock_grpc_context)

        assert response.success is True
        # CDN URL은 settings.cdn_domain + key로 구성
        expected_cdn_prefix = str(test_settings.cdn_domain).rstrip("/") + "/generated/"
        assert response.cdn_url.startswith(expected_cdn_prefix)
        assert response.cdn_url.endswith(".png")
        assert response.key.startswith("generated/")

        # S3 put_object가 호출되었는지 확인
        mock_s3.put_object.assert_called_once()
        call_kwargs = mock_s3.put_object.call_args.kwargs
        assert call_kwargs["Bucket"] == test_settings.s3_bucket
        assert call_kwargs["Body"] == b"fake-png-data"
        assert call_kwargs["ContentType"] == "image/png"

    @pytest.mark.asyncio
    async def test_uses_default_channel(self, mock_session, test_settings, mock_grpc_context):
        """채널이 없으면 'generated'를 사용합니다."""
        mock_s3 = AsyncMock()
        mock_s3.put_object = AsyncMock()

        mock_client_cm = AsyncMock()
        mock_client_cm.__aenter__ = AsyncMock(return_value=mock_s3)
        mock_client_cm.__aexit__ = AsyncMock(return_value=None)

        mock_session.client = MagicMock(return_value=mock_client_cm)

        servicer = ImageServicer(session=mock_session, settings=test_settings)

        request = image_pb2.UploadBytesRequest(
            channel="",  # 빈 채널
            image_data=b"fake-png-data",
            content_type="image/png",
        )

        response = await servicer.UploadBytes(request, mock_grpc_context)

        assert response.success is True
        assert "generated/" in response.key

    @pytest.mark.asyncio
    async def test_includes_metadata(self, mock_session, test_settings, mock_grpc_context):
        """메타데이터가 S3에 포함됩니다."""
        mock_s3 = AsyncMock()
        mock_s3.put_object = AsyncMock()

        mock_client_cm = AsyncMock()
        mock_client_cm.__aenter__ = AsyncMock(return_value=mock_s3)
        mock_client_cm.__aexit__ = AsyncMock(return_value=None)

        mock_session.client = MagicMock(return_value=mock_client_cm)

        servicer = ImageServicer(session=mock_session, settings=test_settings)

        request = image_pb2.UploadBytesRequest(
            channel="generated",
            image_data=b"fake-png-data",
            content_type="image/png",
            uploader_id="test_user",
        )
        request.metadata["job_id"] = "job-123"
        request.metadata["description"] = "test image"

        response = await servicer.UploadBytes(request, mock_grpc_context)

        assert response.success is True

        call_kwargs = mock_s3.put_object.call_args.kwargs
        assert call_kwargs["Metadata"]["uploader_id"] == "test_user"
        assert call_kwargs["Metadata"]["job_id"] == "job-123"
        assert call_kwargs["Metadata"]["description"] == "test image"


class TestUploadBytesError:
    """Tests for UploadBytes error handling."""

    @pytest.mark.asyncio
    async def test_handles_s3_error(self, mock_session, test_settings, mock_grpc_context):
        """S3 오류를 처리합니다."""
        mock_s3 = AsyncMock()
        mock_s3.put_object = AsyncMock(side_effect=Exception("S3 connection failed"))

        mock_client_cm = AsyncMock()
        mock_client_cm.__aenter__ = AsyncMock(return_value=mock_s3)
        mock_client_cm.__aexit__ = AsyncMock(return_value=None)

        mock_session.client = MagicMock(return_value=mock_client_cm)

        servicer = ImageServicer(session=mock_session, settings=test_settings)

        request = image_pb2.UploadBytesRequest(
            channel="generated",
            image_data=b"fake-png-data",
            content_type="image/png",
        )

        response = await servicer.UploadBytes(request, mock_grpc_context)

        assert response.success is False
        assert "S3 connection failed" in response.error


class TestAllowedContentTypes:
    """Tests for allowed content types."""

    def test_allowed_types(self):
        """허용된 Content-Type 목록을 확인합니다."""
        expected = {"image/png", "image/jpeg", "image/jpg", "image/gif", "image/webp"}
        assert ALLOWED_CONTENT_TYPES == expected

    def test_max_image_size(self):
        """최대 이미지 크기를 확인합니다."""
        assert MAX_IMAGE_SIZE == 10 * 1024 * 1024  # 10MB
