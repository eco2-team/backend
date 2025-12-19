"""Tests for CharacterServicer gRPC handler."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest


class TestGetCharacterReward:
    """Tests for GetCharacterReward gRPC method."""

    @pytest.fixture
    def mock_context(self):
        context = AsyncMock()
        context.abort = AsyncMock()
        return context

    @pytest.fixture
    def mock_request(self):
        request = MagicMock()
        request.source = "scan"
        request.user_id = str(uuid4())
        request.task_id = "task-123"
        request.classification.major_category = "재활용폐기물"
        request.classification.middle_category = "플라스틱"
        request.classification.HasField = MagicMock(return_value=False)
        request.situation_tags = []
        request.disposal_rules_present = True
        request.insufficiencies_present = False
        return request

    @pytest.mark.asyncio
    async def test_returns_reward_response(self, mock_request, mock_context):
        """정상 요청 시 RewardResponse 반환."""
        from domains.character.rpc.v1.character_servicer import CharacterServicer

        mock_result = MagicMock()
        mock_result.received = True
        mock_result.already_owned = False
        mock_result.name = "플라봇"
        mock_result.dialog = "안녕!"
        mock_result.match_reason = "플라스틱"
        mock_result.character_type = "플라스틱"
        mock_result.type = "플라스틱"

        with (
            patch(
                "domains.character.rpc.v1.character_servicer.async_session_factory"
            ) as mock_session_factory,
            patch(
                "domains.character.rpc.v1.character_servicer.CharacterService"
            ) as mock_service_class,
        ):
            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            mock_session_factory.return_value = mock_session

            mock_service = AsyncMock()
            mock_service.evaluate_reward = AsyncMock(return_value=mock_result)
            mock_service_class.return_value = mock_service

            servicer = CharacterServicer()
            response = await servicer.GetCharacterReward(mock_request, mock_context)

            assert response.received is True
            assert response.name == "플라봇"

    @pytest.mark.asyncio
    async def test_invalid_uuid_aborts(self, mock_request, mock_context):
        """잘못된 UUID 시 INVALID_ARGUMENT abort."""
        from domains.character.rpc.v1.character_servicer import CharacterServicer

        mock_request.user_id = "invalid-uuid"

        with patch("domains.character.rpc.v1.character_servicer.async_session_factory"):
            servicer = CharacterServicer()
            await servicer.GetCharacterReward(mock_request, mock_context)

            mock_context.abort.assert_called_once()
            call_args = mock_context.abort.call_args
            assert call_args[0][0].name == "INVALID_ARGUMENT"


class TestGetDefaultCharacter:
    """Tests for GetDefaultCharacter gRPC method."""

    @pytest.fixture
    def mock_context(self):
        context = AsyncMock()
        context.abort = AsyncMock()
        return context

    @pytest.fixture
    def mock_request(self):
        return MagicMock()

    @pytest.mark.asyncio
    async def test_returns_default_character(self, mock_request, mock_context):
        """기본 캐릭터 존재 시 정보 반환."""
        from domains.character.rpc.v1.character_servicer import CharacterServicer

        mock_character = MagicMock()
        mock_character.id = uuid4()
        mock_character.code = "ECO001"
        mock_character.name = "이코"
        mock_character.type_label = "기본"
        mock_character.dialog = "안녕!"

        with (
            patch(
                "domains.character.rpc.v1.character_servicer.async_session_factory"
            ) as mock_session_factory,
            patch(
                "domains.character.rpc.v1.character_servicer.CharacterService"
            ) as mock_service_class,
        ):
            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            mock_session_factory.return_value = mock_session

            mock_service = AsyncMock()
            mock_service.get_default_character = AsyncMock(return_value=mock_character)
            mock_service_class.return_value = mock_service

            servicer = CharacterServicer()
            response = await servicer.GetDefaultCharacter(mock_request, mock_context)

            assert response.found is True
            assert response.character_name == "이코"

    @pytest.mark.asyncio
    async def test_returns_not_found(self, mock_request, mock_context):
        """기본 캐릭터 없을 시 found=False."""
        from domains.character.rpc.v1.character_servicer import CharacterServicer

        with (
            patch(
                "domains.character.rpc.v1.character_servicer.async_session_factory"
            ) as mock_session_factory,
            patch(
                "domains.character.rpc.v1.character_servicer.CharacterService"
            ) as mock_service_class,
        ):
            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            mock_session_factory.return_value = mock_session

            mock_service = AsyncMock()
            mock_service.get_default_character = AsyncMock(return_value=None)
            mock_service_class.return_value = mock_service

            servicer = CharacterServicer()
            response = await servicer.GetDefaultCharacter(mock_request, mock_context)

            assert response.found is False
