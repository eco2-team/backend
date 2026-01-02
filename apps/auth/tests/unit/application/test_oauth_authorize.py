"""OAuthAuthorizeInteractor 단위 테스트."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from apps.auth.application.oauth.commands.authorize import OAuthAuthorizeInteractor
from apps.auth.application.oauth.dto import OAuthAuthorizeRequest


class TestOAuthAuthorizeInteractor:
    """OAuthAuthorizeInteractor 테스트."""

    @pytest.fixture
    def mock_oauth_service(self) -> MagicMock:
        """Mock OAuthFlowService."""
        service = MagicMock()
        service.save_state = AsyncMock()
        service.get_authorization_url.return_value = "https://accounts.google.com/oauth?..."
        return service

    @pytest.fixture
    def interactor(
        self,
        mock_oauth_service: MagicMock,
    ) -> OAuthAuthorizeInteractor:
        return OAuthAuthorizeInteractor(oauth_service=mock_oauth_service)

    @pytest.mark.asyncio
    async def test_execute_creates_state_and_returns_url(
        self,
        interactor: OAuthAuthorizeInteractor,
        mock_oauth_service: MagicMock,
    ) -> None:
        """인증 URL 생성 및 state 저장 테스트."""
        # Arrange
        request = OAuthAuthorizeRequest(
            provider="google",
            redirect_uri="http://localhost:8000/callback",
            frontend_origin="http://localhost:3000",
        )

        # Act
        result = await interactor.execute(request)

        # Assert
        assert result.authorization_url == "https://accounts.google.com/oauth?..."
        assert result.state is not None
        assert len(result.state) > 20  # state는 충분히 긴 랜덤 문자열

        # oauth_service.save_state가 호출되었는지 확인
        mock_oauth_service.save_state.assert_called_once()
        call_kwargs = mock_oauth_service.save_state.call_args[1]

        assert call_kwargs["provider"] == "google"
        assert call_kwargs["redirect_uri"] == "http://localhost:8000/callback"
        assert call_kwargs["frontend_origin"] == "http://localhost:3000"
        assert "code_verifier" in call_kwargs

    @pytest.mark.asyncio
    async def test_execute_with_custom_state(
        self,
        interactor: OAuthAuthorizeInteractor,
        mock_oauth_service: MagicMock,
    ) -> None:
        """커스텀 state 사용 테스트."""
        # Arrange
        custom_state = "my-custom-state-12345"
        request = OAuthAuthorizeRequest(
            provider="kakao",
            state=custom_state,
        )

        # Act
        result = await interactor.execute(request)

        # Assert
        assert result.state == custom_state

    @pytest.mark.asyncio
    async def test_execute_with_device_id(
        self,
        interactor: OAuthAuthorizeInteractor,
        mock_oauth_service: MagicMock,
    ) -> None:
        """device_id 저장 테스트."""
        # Arrange
        request = OAuthAuthorizeRequest(
            provider="naver",
            device_id="device-abc-123",
        )

        # Act
        await interactor.execute(request)

        # Assert
        call_kwargs = mock_oauth_service.save_state.call_args[1]
        assert call_kwargs["device_id"] == "device-abc-123"

    @pytest.mark.asyncio
    async def test_execute_calls_oauth_service_with_correct_params(
        self,
        interactor: OAuthAuthorizeInteractor,
        mock_oauth_service: MagicMock,
    ) -> None:
        """OAuthFlowService에 올바른 파라미터 전달 테스트."""
        # Arrange
        request = OAuthAuthorizeRequest(
            provider="google",
            redirect_uri="http://localhost:8000/callback",
        )

        # Act
        result = await interactor.execute(request)

        # Assert
        mock_oauth_service.get_authorization_url.assert_called_once()
        call_args = mock_oauth_service.get_authorization_url.call_args

        assert call_args[0][0] == "google"  # provider
        assert call_args[1]["redirect_uri"] == "http://localhost:8000/callback"
        assert call_args[1]["state"] == result.state
        assert "code_verifier" in call_args[1]
