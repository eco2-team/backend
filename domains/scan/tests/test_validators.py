"""Tests for ImageUrlValidator."""

import pytest

from domains.scan.core.validators import (
    ImageUrlError,
    ImageUrlValidator,
    ValidationResult,
)


class MockSettings:
    """Mock settings for testing."""

    allowed_image_hosts = frozenset({"images.dev.growbin.app", "images.growbin.app"})
    allowed_image_channels = frozenset({"scan", "chat", "my"})
    allowed_image_extensions = frozenset({".jpg", ".jpeg", ".png", ".webp", ".gif"})
    image_filename_pattern = r"^[a-f0-9]{32}$"


class TestImageUrlValidator:
    """Unit tests for ImageUrlValidator."""

    @pytest.fixture
    def validator(self) -> ImageUrlValidator:
        return ImageUrlValidator(MockSettings())

    # === Valid URLs ===

    def test_valid_scan_url(self, validator: ImageUrlValidator):
        """Test valid scan channel URL."""
        url = "https://images.dev.growbin.app/scan/1e89074f111d4727b1f28da647bc7c8e.jpg"
        result = validator.validate(url)
        assert result.valid is True
        assert result.error is None

    def test_valid_chat_url(self, validator: ImageUrlValidator):
        """Test valid chat channel URL."""
        url = "https://images.dev.growbin.app/chat/abcdef1234567890abcdef1234567890.png"
        result = validator.validate(url)
        assert result.valid is True

    def test_valid_my_url(self, validator: ImageUrlValidator):
        """Test valid my channel URL."""
        url = "https://images.growbin.app/my/0123456789abcdef0123456789abcdef.webp"
        result = validator.validate(url)
        assert result.valid is True

    def test_valid_uppercase_extension(self, validator: ImageUrlValidator):
        """Test valid URL with uppercase extension."""
        url = "https://images.dev.growbin.app/scan/1e89074f111d4727b1f28da647bc7c8e.JPG"
        result = validator.validate(url)
        assert result.valid is True

    # === HTTPS Required ===

    def test_http_rejected(self, validator: ImageUrlValidator):
        """Test HTTP scheme is rejected."""
        url = "http://images.dev.growbin.app/scan/1e89074f111d4727b1f28da647bc7c8e.jpg"
        result = validator.validate(url)
        assert result.valid is False
        assert result.error == ImageUrlError.HTTPS_REQUIRED

    def test_ftp_rejected(self, validator: ImageUrlValidator):
        """Test FTP scheme is rejected."""
        url = "ftp://images.dev.growbin.app/scan/1e89074f111d4727b1f28da647bc7c8e.jpg"
        result = validator.validate(url)
        assert result.valid is False
        assert result.error == ImageUrlError.HTTPS_REQUIRED

    # === Invalid Host ===

    def test_invalid_host_rejected(self, validator: ImageUrlValidator):
        """Test invalid host is rejected."""
        url = "https://evil.com/scan/1e89074f111d4727b1f28da647bc7c8e.jpg"
        result = validator.validate(url)
        assert result.valid is False
        assert result.error == ImageUrlError.INVALID_HOST

    def test_similar_host_rejected(self, validator: ImageUrlValidator):
        """Test similar but different host is rejected."""
        url = "https://images.dev.growbin.app.evil.com/scan/1e89074f111d4727b1f28da647bc7c8e.jpg"
        result = validator.validate(url)
        assert result.valid is False
        assert result.error == ImageUrlError.INVALID_HOST

    # === Invalid Channel ===

    def test_invalid_channel_rejected(self, validator: ImageUrlValidator):
        """Test invalid channel is rejected."""
        url = "https://images.dev.growbin.app/admin/1e89074f111d4727b1f28da647bc7c8e.jpg"
        result = validator.validate(url)
        assert result.valid is False
        assert result.error == ImageUrlError.INVALID_CHANNEL

    def test_empty_channel_rejected(self, validator: ImageUrlValidator):
        """Test empty channel is rejected."""
        url = "https://images.dev.growbin.app/1e89074f111d4727b1f28da647bc7c8e.jpg"
        result = validator.validate(url)
        assert result.valid is False
        assert result.error == ImageUrlError.INVALID_PATH_FORMAT

    # === Invalid Path Format ===

    def test_nested_path_rejected(self, validator: ImageUrlValidator):
        """Test nested path is rejected."""
        url = "https://images.dev.growbin.app/scan/nested/1e89074f111d4727b1f28da647bc7c8e.jpg"
        result = validator.validate(url)
        assert result.valid is False
        assert result.error == ImageUrlError.INVALID_PATH_FORMAT

    def test_root_path_rejected(self, validator: ImageUrlValidator):
        """Test root path is rejected."""
        url = "https://images.dev.growbin.app/"
        result = validator.validate(url)
        assert result.valid is False
        assert result.error == ImageUrlError.INVALID_PATH_FORMAT

    # === Invalid Filename ===

    def test_short_filename_rejected(self, validator: ImageUrlValidator):
        """Test short filename is rejected."""
        url = "https://images.dev.growbin.app/scan/abc123.jpg"
        result = validator.validate(url)
        assert result.valid is False
        assert result.error == ImageUrlError.INVALID_FILENAME

    def test_non_hex_filename_rejected(self, validator: ImageUrlValidator):
        """Test non-hex filename is rejected."""
        url = "https://images.dev.growbin.app/scan/zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz.jpg"
        result = validator.validate(url)
        assert result.valid is False
        assert result.error == ImageUrlError.INVALID_FILENAME

    def test_filename_with_dashes_rejected(self, validator: ImageUrlValidator):
        """Test filename with dashes is rejected."""
        url = "https://images.dev.growbin.app/scan/1e89074f-111d-4727-b1f2-8da647bc7c8e.jpg"
        result = validator.validate(url)
        assert result.valid is False
        assert result.error == ImageUrlError.INVALID_FILENAME

    # === Invalid Extension ===

    def test_invalid_extension_rejected(self, validator: ImageUrlValidator):
        """Test invalid extension is rejected."""
        url = "https://images.dev.growbin.app/scan/1e89074f111d4727b1f28da647bc7c8e.exe"
        result = validator.validate(url)
        assert result.valid is False
        assert result.error == ImageUrlError.INVALID_EXTENSION

    def test_no_extension_rejected(self, validator: ImageUrlValidator):
        """Test no extension is rejected."""
        url = "https://images.dev.growbin.app/scan/1e89074f111d4727b1f28da647bc7c8e"
        result = validator.validate(url)
        assert result.valid is False
        assert result.error == ImageUrlError.INVALID_EXTENSION

    # === SSRF Prevention ===

    def test_localhost_blocked(self, validator: ImageUrlValidator):
        """Test localhost is blocked (via INVALID_HOST since not in allowlist)."""
        url = "https://localhost/scan/1e89074f111d4727b1f28da647bc7c8e.jpg"
        result = validator.validate(url)
        assert result.valid is False
        # localhost is not in allowlist, so INVALID_HOST is returned first
        assert result.error == ImageUrlError.INVALID_HOST

    def test_127_0_0_1_blocked(self, validator: ImageUrlValidator):
        """Test 127.0.0.1 is blocked."""
        url = "https://127.0.0.1/scan/1e89074f111d4727b1f28da647bc7c8e.jpg"
        result = validator.validate(url)
        assert result.valid is False
        assert result.error == ImageUrlError.INVALID_HOST


class TestValidationResult:
    """Tests for ValidationResult dataclass."""

    def test_ok_result(self):
        """Test ok() creates valid result."""
        result = ValidationResult.ok()
        assert result.valid is True
        assert result.error is None
        assert result.message is None

    def test_fail_result(self):
        """Test fail() creates invalid result."""
        result = ValidationResult.fail(ImageUrlError.INVALID_HOST, "Test message")
        assert result.valid is False
        assert result.error == ImageUrlError.INVALID_HOST
        assert result.message == "Test message"
