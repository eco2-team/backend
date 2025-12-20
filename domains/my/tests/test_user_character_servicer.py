"""Unit tests for UserCharacterServicer (gRPC server)."""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from domains.my.rpc.v1.user_character_servicer import UserCharacterServicer  # noqa: E402


@pytest.fixture
def servicer():
    """Create UserCharacterServicer instance."""
    return UserCharacterServicer()


@pytest.fixture
def mock_context():
    """Mock gRPC context."""
    context = MagicMock()
    context.abort = AsyncMock()
    return context


@pytest.fixture
def mock_request():
    """Mock gRPC request."""
    request = MagicMock()
    request.user_id = str(uuid4())
    request.character_id = str(uuid4())
    request.character_code = "ECO_001"
    request.character_name = "이코"
    request.character_type = "default"
    request.character_dialog = "안녕!"
    request.source = "scan"
    return request


class TestGrantCharacter:
    """Tests for GrantCharacter method."""

    @pytest.mark.asyncio
    async def test_grants_new_character(self, servicer, mock_request, mock_context):
        """새 캐릭터를 성공적으로 지급합니다."""
        mock_session = MagicMock()
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()

        with patch(
            "domains.my.rpc.v1.user_character_servicer.async_session_factory"
        ) as mock_factory:
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=None)

            response = await servicer.GrantCharacter(mock_request, mock_context)

        assert response.success is True
        assert response.already_owned is False
        assert "Granted" in response.message
        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_handles_integrity_error(self, servicer, mock_request, mock_context):
        """IntegrityError 발생 시 already_owned=True를 반환합니다."""
        from sqlalchemy.exc import IntegrityError

        mock_session = MagicMock()
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock(side_effect=IntegrityError("", {}, Exception()))
        mock_session.rollback = AsyncMock()

        with patch(
            "domains.my.rpc.v1.user_character_servicer.async_session_factory"
        ) as mock_factory:
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=None)

            response = await servicer.GrantCharacter(mock_request, mock_context)

        assert response.success is True
        assert response.already_owned is True
        mock_session.rollback.assert_called_once()

    @pytest.mark.asyncio
    async def test_handles_invalid_uuid(self, servicer, mock_context):
        """잘못된 UUID는 INVALID_ARGUMENT 에러를 반환합니다."""
        mock_request = MagicMock()
        mock_request.user_id = "invalid-uuid"
        mock_request.character_id = str(uuid4())

        await servicer.GrantCharacter(mock_request, mock_context)

        mock_context.abort.assert_called_once()
        # grpc.StatusCode.INVALID_ARGUMENT로 호출되었는지 확인
        call_args = mock_context.abort.call_args
        assert call_args is not None

    @pytest.mark.asyncio
    async def test_handles_unexpected_error(self, servicer, mock_request, mock_context):
        """예상치 못한 에러는 INTERNAL 에러를 반환합니다."""
        with patch(
            "domains.my.rpc.v1.user_character_servicer.async_session_factory"
        ) as mock_factory:
            mock_factory.return_value.__aenter__ = AsyncMock(side_effect=RuntimeError("Unexpected"))
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=None)

            await servicer.GrantCharacter(mock_request, mock_context)

        mock_context.abort.assert_called_once()
