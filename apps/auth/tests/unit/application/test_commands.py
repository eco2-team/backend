"""Application Command Tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from apps.auth.application.commands.logout import LogoutInteractor
from apps.auth.application.common.dto.auth import LogoutRequest


class TestLogoutInteractor:
    """LogoutInteractor 테스트."""

    @pytest.fixture
    def mock_token_service(self) -> MagicMock:
        """Mock TokenService."""
        mock = MagicMock()
        mock.decode = MagicMock(return_value=MagicMock())
        mock.ensure_type = MagicMock()
        return mock

    @pytest.fixture
    def mock_blacklist_publisher(self) -> AsyncMock:
        """Mock BlacklistEventPublisher."""
        return AsyncMock()

    @pytest.fixture
    def interactor(
        self,
        mock_token_service: MagicMock,
        mock_blacklist_publisher: AsyncMock,
    ) -> LogoutInteractor:
        """LogoutInteractor 인스턴스."""
        mock_user_token_store = AsyncMock()
        mock_transaction_manager = AsyncMock()

        return LogoutInteractor(
            token_service=mock_token_service,
            blacklist_publisher=mock_blacklist_publisher,
            user_token_store=mock_user_token_store,
            transaction_manager=mock_transaction_manager,
        )

    @pytest.mark.asyncio
    async def test_logout_with_tokens(
        self,
        interactor: LogoutInteractor,
    ) -> None:
        """액세스 토큰과 리프레시 토큰으로 로그아웃."""
        # Arrange
        request = LogoutRequest(
            access_token="access-token",
            refresh_token="refresh-token",
        )

        # Act
        await interactor.execute(request)

        # Assert - 예외 없이 완료되면 성공

    @pytest.mark.asyncio
    async def test_logout_without_tokens(
        self,
        interactor: LogoutInteractor,
    ) -> None:
        """토큰 없이 로그아웃 (쿠키 삭제만)."""
        # Arrange
        request = LogoutRequest()

        # Act
        await interactor.execute(request)

        # Assert - 예외 없이 완료되면 성공

    @pytest.mark.asyncio
    async def test_logout_with_invalid_token(
        self,
        interactor: LogoutInteractor,
        mock_token_service: MagicMock,
    ) -> None:
        """유효하지 않은 토큰으로 로그아웃 (에러 무시)."""
        # Arrange
        mock_token_service.decode.side_effect = Exception("Invalid token")
        request = LogoutRequest(access_token="invalid-token")

        # Act - 예외가 발생하지 않아야 함
        await interactor.execute(request)

        # Assert - 예외 없이 완료되면 성공
