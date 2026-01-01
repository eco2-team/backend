"""ValidateTokenQueryService 단위 테스트."""

import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from apps.auth.application.queries.validate_token import ValidateTokenQueryService
from apps.auth.domain.entities.user import User
from apps.auth.domain.enums.token_type import TokenType
from apps.auth.domain.exceptions.auth import TokenRevokedError
from apps.auth.domain.exceptions.user import UserNotFoundError
from apps.auth.domain.value_objects.token_payload import TokenPayload
from apps.auth.domain.value_objects.user_id import UserId


class TestValidateTokenQueryService:
    """ValidateTokenQueryService 테스트."""

    @pytest.fixture
    def mock_token_issuer(self) -> MagicMock:
        return MagicMock()

    @pytest.fixture
    def mock_token_blacklist(self) -> AsyncMock:
        blacklist = AsyncMock()
        blacklist.contains.return_value = False
        return blacklist

    @pytest.fixture
    def mock_user_query_gateway(self) -> AsyncMock:
        return AsyncMock()

    @pytest.fixture
    def query_service(
        self,
        mock_token_issuer: MagicMock,
        mock_token_blacklist: AsyncMock,
        mock_user_query_gateway: AsyncMock,
    ) -> ValidateTokenQueryService:
        return ValidateTokenQueryService(
            token_issuer=mock_token_issuer,
            token_blacklist=mock_token_blacklist,
            user_query_gateway=mock_user_query_gateway,
        )

    @pytest.fixture
    def sample_user(self) -> User:
        from datetime import datetime, timezone

        return User(
            id_=UserId.generate(),
            nickname="testuser",
            profile_image_url=None,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

    @pytest.fixture
    def valid_token_payload(self, sample_user: User) -> TokenPayload:
        now = int(time.time())
        return TokenPayload(
            user_id=sample_user.id_,
            token_type=TokenType.ACCESS,
            jti="test-jti-123",
            iat=now,
            exp=now + 3600,
            provider="google",
        )

    @pytest.mark.asyncio
    async def test_validate_valid_token(
        self,
        query_service: ValidateTokenQueryService,
        mock_token_issuer: MagicMock,
        mock_token_blacklist: AsyncMock,
        mock_user_query_gateway: AsyncMock,
        sample_user: User,
        valid_token_payload: TokenPayload,
    ) -> None:
        """유효한 토큰 검증 테스트."""
        # Arrange
        mock_token_issuer.decode.return_value = valid_token_payload
        mock_token_issuer.ensure_type.return_value = None
        mock_user_query_gateway.get_by_id.return_value = sample_user

        # Act
        result = await query_service.execute("valid-access-token")

        # Assert
        assert result.user_id == sample_user.id_.value
        assert result.provider == "google"
        mock_token_issuer.decode.assert_called_once_with("valid-access-token")
        mock_token_blacklist.contains.assert_called_once_with("test-jti-123")

    @pytest.mark.asyncio
    async def test_validate_blacklisted_token(
        self,
        query_service: ValidateTokenQueryService,
        mock_token_issuer: MagicMock,
        mock_token_blacklist: AsyncMock,
        valid_token_payload: TokenPayload,
    ) -> None:
        """블랙리스트된 토큰 검증 실패 테스트."""
        # Arrange
        mock_token_issuer.decode.return_value = valid_token_payload
        mock_token_blacklist.contains.return_value = True

        # Act & Assert
        with pytest.raises(TokenRevokedError):
            await query_service.execute("blacklisted-token")

    @pytest.mark.asyncio
    async def test_validate_user_not_found(
        self,
        query_service: ValidateTokenQueryService,
        mock_token_issuer: MagicMock,
        mock_token_blacklist: AsyncMock,
        mock_user_query_gateway: AsyncMock,
        valid_token_payload: TokenPayload,
    ) -> None:
        """사용자를 찾을 수 없는 경우 테스트."""
        # Arrange
        mock_token_issuer.decode.return_value = valid_token_payload
        mock_user_query_gateway.get_by_id.return_value = None

        # Act & Assert
        with pytest.raises(UserNotFoundError):
            await query_service.execute("valid-token-but-no-user")
