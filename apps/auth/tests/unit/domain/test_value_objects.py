"""Value Object Tests."""

from __future__ import annotations

import time
import uuid

import pytest

from apps.auth.domain.enums.token_type import TokenType
from apps.auth.domain.value_objects.email import Email
from apps.auth.domain.value_objects.token_payload import TokenPayload
from apps.auth.domain.value_objects.user_id import UserId


class TestUserId:
    """UserId Value Object 테스트."""

    def test_create_user_id(self) -> None:
        """UserId 생성."""
        # Act
        user_id = UserId.generate()

        # Assert
        assert user_id.value is not None
        assert isinstance(user_id.value, uuid.UUID)

    def test_user_id_equality(self) -> None:
        """같은 값의 UserId는 동일."""
        # Arrange
        raw_id = uuid.uuid4()

        # Act
        id1 = UserId(value=raw_id)
        id2 = UserId(value=raw_id)

        # Assert
        assert id1 == id2
        assert hash(id1) == hash(id2)

    def test_from_string(self) -> None:
        """문자열에서 UserId 생성."""
        # Arrange
        raw_id = uuid.uuid4()

        # Act
        user_id = UserId.from_string(str(raw_id))

        # Assert
        assert user_id.value == raw_id


class TestEmail:
    """Email Value Object 테스트."""

    def test_valid_email(self) -> None:
        """유효한 이메일."""
        # Act
        email = Email(value="test@example.com")

        # Assert
        assert email.value == "test@example.com"
        assert email.domain == "example.com"

    def test_invalid_email_raises(self) -> None:
        """유효하지 않은 이메일은 에러."""
        from apps.auth.domain.exceptions.validation import InvalidEmailError

        # Act & Assert
        with pytest.raises(InvalidEmailError, match="Invalid email"):
            Email(value="invalid-email")


class TestTokenPayload:
    """TokenPayload Value Object 테스트."""

    def test_create_token_payload(self) -> None:
        """TokenPayload 생성."""
        # Arrange
        user_id = UserId.generate()
        now = int(time.time())

        # Act
        payload = TokenPayload(
            user_id=user_id,
            token_type=TokenType.ACCESS,
            jti="test-jti",
            iat=now,
            exp=now + 3600,
            provider="google",
        )

        # Assert
        assert payload.user_id == user_id
        assert payload.token_type == TokenType.ACCESS
        assert payload.jti == "test-jti"
        assert payload.provider == "google"

    def test_token_payload_is_immutable(self) -> None:
        """TokenPayload는 불변."""
        # Arrange
        now = int(time.time())
        payload = TokenPayload(
            user_id=UserId.generate(),
            token_type=TokenType.ACCESS,
            jti="test-jti",
            iat=now,
            exp=now + 3600,
            provider="kakao",
        )

        # Act & Assert
        with pytest.raises(AttributeError):
            payload.jti = "new-jti"  # type: ignore

    def test_is_expired(self) -> None:
        """토큰 만료 여부 확인."""
        # Arrange
        now = int(time.time())
        expired_payload = TokenPayload(
            user_id=UserId.generate(),
            token_type=TokenType.ACCESS,
            jti="expired-jti",
            iat=now - 7200,
            exp=now - 3600,  # 1시간 전 만료
            provider="naver",
        )
        valid_payload = TokenPayload(
            user_id=UserId.generate(),
            token_type=TokenType.ACCESS,
            jti="valid-jti",
            iat=now,
            exp=now + 3600,  # 1시간 후 만료
            provider="naver",
        )

        # Assert
        assert expired_payload.is_expired is True
        assert valid_payload.is_expired is False

    def test_from_dict(self) -> None:
        """딕셔너리에서 TokenPayload 생성."""
        # Arrange
        user_id = uuid.uuid4()
        now = int(time.time())
        data = {
            "sub": str(user_id),
            "jti": "test-jti",
            "type": "access",
            "exp": now + 3600,
            "iat": now,
            "provider": "google",
        }

        # Act
        payload = TokenPayload.from_dict(data)

        # Assert
        assert payload.user_id.value == user_id
        assert payload.jti == "test-jti"
        assert payload.token_type == TokenType.ACCESS
