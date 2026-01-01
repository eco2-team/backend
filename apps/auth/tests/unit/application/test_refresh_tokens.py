"""RefreshTokensInteractor 단위 테스트."""

import time
from unittest.mock import AsyncMock, MagicMock
import pytest

from apps.auth.application.commands.refresh_tokens import RefreshTokensInteractor
from apps.auth.application.common.dto.auth import RefreshTokensRequest
from apps.auth.domain.enums.token_type import TokenType
from apps.auth.domain.value_objects.token_payload import TokenPayload
from apps.auth.domain.value_objects.user_id import UserId
from apps.auth.domain.entities.user import User
from apps.auth.domain.exceptions.auth import TokenRevokedError
from apps.auth.domain.exceptions.user import UserNotFoundError


class TestRefreshTokensInteractor:
    """RefreshTokensInteractor 테스트."""

    @pytest.fixture
    def mock_token_service(self) -> MagicMock:
        service = MagicMock()
        # issue_pair 반환값 설정
        service.issue_pair.return_value = MagicMock(
            access_token="new-access-token",
            refresh_token="new-refresh-token",
            access_jti="new-access-jti",
            refresh_jti="new-refresh-jti",
            access_expires_at=int(time.time()) + 900,
            refresh_expires_at=int(time.time()) + 604800,
        )
        return service

    @pytest.fixture
    def mock_token_blacklist(self) -> AsyncMock:
        blacklist = AsyncMock()
        blacklist.contains.return_value = False
        return blacklist

    @pytest.fixture
    def mock_blacklist_publisher(self) -> AsyncMock:
        """Mock BlacklistEventPublisher."""
        return AsyncMock()

    @pytest.fixture
    def mock_user_token_store(self) -> AsyncMock:
        store = AsyncMock()
        store.contains.return_value = True
        store.get_metadata.return_value = MagicMock(
            device_id="test-device",
            user_agent="test-agent",
        )
        return store

    @pytest.fixture
    def mock_user_query_gateway(self) -> AsyncMock:
        return AsyncMock()

    @pytest.fixture
    def mock_transaction_manager(self) -> AsyncMock:
        return AsyncMock()

    @pytest.fixture
    def interactor(
        self,
        mock_token_service: MagicMock,
        mock_token_blacklist: AsyncMock,
        mock_blacklist_publisher: AsyncMock,
        mock_user_token_store: AsyncMock,
        mock_user_query_gateway: AsyncMock,
        mock_transaction_manager: AsyncMock,
    ) -> RefreshTokensInteractor:
        return RefreshTokensInteractor(
            token_service=mock_token_service,
            token_blacklist=mock_token_blacklist,
            blacklist_publisher=mock_blacklist_publisher,
            user_token_store=mock_user_token_store,
            user_query_gateway=mock_user_query_gateway,
            transaction_manager=mock_transaction_manager,
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
    def valid_refresh_payload(self, sample_user: User) -> TokenPayload:
        now = int(time.time())
        return TokenPayload(
            user_id=sample_user.id_,
            token_type=TokenType.REFRESH,
            jti="old-refresh-jti",
            iat=now - 3600,
            exp=now + 604800,
            provider="google",
        )

    @pytest.mark.asyncio
    async def test_refresh_success(
        self,
        interactor: RefreshTokensInteractor,
        mock_token_service: MagicMock,
        mock_blacklist_publisher: AsyncMock,
        mock_user_token_store: AsyncMock,
        mock_user_query_gateway: AsyncMock,
        sample_user: User,
        valid_refresh_payload: TokenPayload,
    ) -> None:
        """정상적인 토큰 갱신 테스트."""
        # Arrange
        mock_token_service.decode.return_value = valid_refresh_payload
        mock_token_service.ensure_type.return_value = None
        mock_user_query_gateway.get_by_id.return_value = sample_user

        request = RefreshTokensRequest(refresh_token="old-refresh-token")

        # Act
        result = await interactor.execute(request)

        # Assert
        assert result.access_token == "new-access-token"
        assert result.refresh_token == "new-refresh-token"
        assert result.user_id == sample_user.id_.value

        # 기존 토큰 블랙리스트 이벤트 발행 확인
        mock_blacklist_publisher.publish_add.assert_called()

        # 새 토큰 저장 확인
        mock_user_token_store.register.assert_called_once()

    @pytest.mark.asyncio
    async def test_refresh_with_blacklisted_token(
        self,
        interactor: RefreshTokensInteractor,
        mock_token_service: MagicMock,
        mock_token_blacklist: AsyncMock,
        valid_refresh_payload: TokenPayload,
    ) -> None:
        """블랙리스트된 토큰으로 갱신 시도 실패 테스트."""
        # Arrange
        mock_token_service.decode.return_value = valid_refresh_payload
        mock_token_blacklist.contains.return_value = True

        request = RefreshTokensRequest(refresh_token="blacklisted-refresh-token")

        # Act & Assert
        with pytest.raises(TokenRevokedError):
            await interactor.execute(request)

    @pytest.mark.asyncio
    async def test_refresh_user_not_found(
        self,
        interactor: RefreshTokensInteractor,
        mock_token_service: MagicMock,
        mock_token_blacklist: AsyncMock,
        mock_user_token_store: AsyncMock,
        mock_user_query_gateway: AsyncMock,
        valid_refresh_payload: TokenPayload,
    ) -> None:
        """사용자를 찾을 수 없는 경우 테스트."""
        # Arrange
        mock_token_service.decode.return_value = valid_refresh_payload
        mock_user_query_gateway.get_by_id.return_value = None

        request = RefreshTokensRequest(refresh_token="valid-but-deleted-user")

        # Act & Assert
        with pytest.raises(UserNotFoundError):
            await interactor.execute(request)

    @pytest.mark.asyncio
    async def test_refresh_token_not_in_store(
        self,
        interactor: RefreshTokensInteractor,
        mock_token_service: MagicMock,
        mock_token_blacklist: AsyncMock,
        mock_user_token_store: AsyncMock,
        valid_refresh_payload: TokenPayload,
    ) -> None:
        """토큰 스토어에 없는 토큰으로 갱신 시도 테스트."""
        # Arrange
        mock_token_service.decode.return_value = valid_refresh_payload
        mock_user_token_store.contains.return_value = False  # 스토어에 없음

        request = RefreshTokensRequest(refresh_token="not-in-store-token")

        # Act & Assert
        with pytest.raises(TokenRevokedError):
            await interactor.execute(request)
