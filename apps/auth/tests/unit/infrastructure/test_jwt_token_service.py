"""JWT Token Service 단위 테스트.

JwtTokenService의 토큰 발급/검증 로직을 테스트합니다.
외부 의존성 없이 순수 로직만 테스트합니다.
"""

from uuid import uuid4

import pytest

from apps.auth.domain.enums.token_type import TokenType
from apps.auth.domain.exceptions.auth import (
    InvalidTokenError,
    TokenTypeMismatchError,
)
from apps.auth.infrastructure.security.jwt_token_service import JwtTokenService


class TestJwtTokenService:
    """JwtTokenService 테스트."""

    @pytest.fixture
    def token_service(self) -> JwtTokenService:
        # 충분한 만료 시간 설정 (60분)
        return JwtTokenService(
            secret_key="test-secret-key-12345",
            algorithm="HS256",
            issuer="test-issuer",
            audience="test-audience",
            access_token_expire_minutes=60,  # 1시간
            refresh_token_expire_minutes=10080,  # 7일
        )

    def test_issue_pair(self, token_service: JwtTokenService) -> None:
        """토큰 쌍 발급 테스트."""
        # Arrange
        user_id = uuid4()

        # Act
        pair = token_service.issue_pair(user_id=user_id, provider="google")

        # Assert
        assert pair.access_token is not None
        assert pair.refresh_token is not None
        assert pair.access_jti is not None
        assert pair.refresh_jti is not None
        assert pair.access_jti != pair.refresh_jti  # 서로 다른 JTI
        assert pair.access_expires_at < pair.refresh_expires_at  # refresh가 더 오래 유효

    def test_decode_valid_access_token(self, token_service: JwtTokenService) -> None:
        """유효한 Access 토큰 디코딩 테스트."""
        # Arrange
        user_id = uuid4()
        pair = token_service.issue_pair(user_id=user_id, provider="kakao")

        # Act
        payload = token_service.decode(pair.access_token)

        # Assert
        assert payload.user_id.value == user_id
        assert payload.token_type == TokenType.ACCESS
        assert payload.jti == pair.access_jti
        assert payload.provider == "kakao"

    def test_decode_valid_refresh_token(self, token_service: JwtTokenService) -> None:
        """유효한 Refresh 토큰 디코딩 테스트."""
        # Arrange
        user_id = uuid4()
        pair = token_service.issue_pair(user_id=user_id, provider="naver")

        # Act
        payload = token_service.decode(pair.refresh_token)

        # Assert
        assert payload.user_id.value == user_id
        assert payload.token_type == TokenType.REFRESH
        assert payload.jti == pair.refresh_jti
        assert payload.provider == "naver"

    def test_decode_invalid_token(self, token_service: JwtTokenService) -> None:
        """유효하지 않은 토큰 디코딩 실패 테스트."""
        # Act & Assert
        with pytest.raises(InvalidTokenError):
            token_service.decode("invalid-token-string")

    def test_decode_tampered_token(self, token_service: JwtTokenService) -> None:
        """변조된 토큰 디코딩 실패 테스트."""
        # Arrange
        user_id = uuid4()
        pair = token_service.issue_pair(user_id=user_id, provider="google")

        # 토큰 변조 (시그니처 부분을 완전히 다른 값으로 변경)
        parts = pair.access_token.split(".")
        if len(parts) == 3:
            # 시그니처 부분을 변조
            tampered_token = f"{parts[0]}.{parts[1]}.tampered_signature_abc123"
        else:
            tampered_token = "completely.invalid.token"

        # Act & Assert
        with pytest.raises(InvalidTokenError):
            token_service.decode(tampered_token)

    def test_decode_wrong_secret_key(self, token_service: JwtTokenService) -> None:
        """다른 Secret Key로 서명된 토큰 디코딩 실패 테스트."""
        # Arrange
        user_id = uuid4()
        pair = token_service.issue_pair(user_id=user_id, provider="google")

        # 다른 Secret Key를 사용하는 서비스
        other_service = JwtTokenService(
            secret_key="different-secret-key",
            issuer="test-issuer",
            audience="test-audience",
            access_token_expire_minutes=60,
        )

        # Act & Assert
        with pytest.raises(InvalidTokenError):
            other_service.decode(pair.access_token)

    def test_ensure_type_correct(self, token_service: JwtTokenService) -> None:
        """올바른 토큰 타입 검증 테스트."""
        # Arrange
        user_id = uuid4()
        pair = token_service.issue_pair(user_id=user_id, provider="google")
        access_payload = token_service.decode(pair.access_token)
        refresh_payload = token_service.decode(pair.refresh_token)

        # Act & Assert - 예외 발생하지 않음
        token_service.ensure_type(access_payload, TokenType.ACCESS)
        token_service.ensure_type(refresh_payload, TokenType.REFRESH)

    def test_ensure_type_mismatch(self, token_service: JwtTokenService) -> None:
        """토큰 타입 불일치 테스트."""
        # Arrange
        user_id = uuid4()
        pair = token_service.issue_pair(user_id=user_id, provider="google")
        access_payload = token_service.decode(pair.access_token)

        # Act & Assert
        with pytest.raises(TokenTypeMismatchError) as exc_info:
            token_service.ensure_type(access_payload, TokenType.REFRESH)

        assert "access" in str(exc_info.value).lower()
        assert "refresh" in str(exc_info.value).lower()

    def test_token_contains_all_claims(self, token_service: JwtTokenService) -> None:
        """토큰에 모든 클레임이 포함되어 있는지 테스트."""
        # Arrange
        user_id = uuid4()

        # Act
        pair = token_service.issue_pair(user_id=user_id, provider="google")
        payload = token_service.decode(pair.access_token)

        # Assert
        assert payload.user_id is not None
        assert payload.jti is not None
        assert payload.token_type is not None
        assert payload.exp is not None
        assert payload.iat is not None
        assert payload.provider is not None

    def test_different_users_get_different_tokens(self, token_service: JwtTokenService) -> None:
        """다른 사용자는 다른 토큰을 받는지 테스트."""
        # Arrange
        user_id_1 = uuid4()
        user_id_2 = uuid4()

        # Act
        pair_1 = token_service.issue_pair(user_id=user_id_1, provider="google")
        pair_2 = token_service.issue_pair(user_id=user_id_2, provider="google")

        # Assert
        assert pair_1.access_token != pair_2.access_token
        assert pair_1.refresh_token != pair_2.refresh_token
        assert pair_1.access_jti != pair_2.access_jti
        assert pair_1.refresh_jti != pair_2.refresh_jti


class TestJwtTokenServiceEdgeCases:
    """JwtTokenService 엣지 케이스 테스트."""

    def test_multiple_token_pairs_unique_jti(self) -> None:
        """여러 토큰 쌍의 JTI 고유성 테스트."""
        # Arrange
        service = JwtTokenService(
            secret_key="test-secret",
            issuer="test",
            audience="test",
            access_token_expire_minutes=60,
        )
        user_id = uuid4()

        # Act
        pairs = [service.issue_pair(user_id=user_id, provider="google") for _ in range(10)]

        # Assert
        all_jtis = [p.access_jti for p in pairs] + [p.refresh_jti for p in pairs]
        assert len(all_jtis) == len(set(all_jtis))  # 모두 고유

    def test_provider_preserved_in_token(self) -> None:
        """Provider 정보가 토큰에 보존되는지 테스트."""
        # Arrange
        service = JwtTokenService(
            secret_key="test-secret",
            issuer="test",
            audience="test",
            access_token_expire_minutes=60,
        )
        user_id = uuid4()

        # Act & Assert
        for provider in ["google", "kakao", "naver"]:
            pair = service.issue_pair(user_id=user_id, provider=provider)
            payload = service.decode(pair.access_token)
            assert payload.provider == provider

    def test_token_pair_expiration_order(self) -> None:
        """Access와 Refresh 토큰의 만료 순서 테스트."""
        # Arrange
        service = JwtTokenService(
            secret_key="test-secret",
            issuer="test",
            audience="test",
            access_token_expire_minutes=15,
            refresh_token_expire_minutes=10080,
        )
        user_id = uuid4()

        # Act
        pair = service.issue_pair(user_id=user_id, provider="google")

        # Assert
        # Refresh 토큰은 Access 토큰보다 훨씬 오래 유효
        diff = pair.refresh_expires_at - pair.access_expires_at
        assert diff > 0  # Refresh가 더 늦게 만료
        assert diff > 60 * 60 * 24  # 최소 1일 이상 차이
