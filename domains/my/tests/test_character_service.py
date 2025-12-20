"""Unit tests for UserCharacterService."""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from domains.my.services.characters import UserCharacterService  # noqa: E402


class TestListOwned:
    """Tests for list_owned method."""

    @pytest.mark.asyncio
    async def test_returns_owned_characters(self, mock_session, mock_character_repo):
        """소유한 캐릭터 목록을 반환합니다."""
        user_id = uuid4()
        mock_character = MagicMock()
        mock_character.character_id = uuid4()
        mock_character.character_code = "ECO_001"
        mock_character.character_name = "이코"
        mock_character.character_type = "default"
        mock_character.character_dialog = "안녕!"
        mock_character.acquired_at = MagicMock()

        mock_character_repo.list_by_user = AsyncMock(return_value=[mock_character])

        service = UserCharacterService.__new__(UserCharacterService)
        service.session = mock_session
        service.repo = mock_character_repo

        result = await service.list_owned(user_id)

        assert len(result) == 1
        assert result[0].code == "ECO_001"
        mock_character_repo.list_by_user.assert_called_once_with(user_id)

    @pytest.mark.asyncio
    async def test_grants_default_character_when_empty(
        self, mock_session, mock_character_repo, mock_character_client
    ):
        """캐릭터가 없으면 기본 캐릭터를 지급합니다."""
        user_id = uuid4()

        # 첫 번째 호출: 빈 목록, 두 번째 호출: 지급 후 목록
        mock_character = MagicMock()
        mock_character.character_id = uuid4()
        mock_character.character_code = "ECO_001"
        mock_character.character_name = "이코"
        mock_character.character_type = "default"
        mock_character.character_dialog = "안녕!"
        mock_character.acquired_at = MagicMock()

        mock_character_repo.list_by_user = AsyncMock(side_effect=[[], [mock_character]])

        # 기본 캐릭터 정보 mock
        default_char = MagicMock()
        default_char.character_id = uuid4()
        default_char.character_code = "ECO_001"
        default_char.character_name = "이코"
        default_char.character_type = "default"
        default_char.character_dialog = "안녕!"
        mock_character_client.get_default_character = AsyncMock(return_value=default_char)

        service = UserCharacterService.__new__(UserCharacterService)
        service.session = mock_session
        service.repo = mock_character_repo

        with patch(
            "domains.my.services.characters.get_character_client",
            return_value=mock_character_client,
        ):
            result = await service.list_owned(user_id)

        assert len(result) == 1
        assert mock_character_repo.list_by_user.call_count == 2


class TestEnsureDefaultCharacter:
    """Tests for _ensure_default_character method."""

    @pytest.mark.asyncio
    async def test_returns_false_when_no_default_character(
        self, mock_session, mock_character_repo, mock_character_client
    ):
        """기본 캐릭터를 찾을 수 없으면 False를 반환합니다."""
        user_id = uuid4()
        mock_character_client.get_default_character = AsyncMock(return_value=None)

        service = UserCharacterService.__new__(UserCharacterService)
        service.session = mock_session
        service.repo = mock_character_repo

        with patch(
            "domains.my.services.characters.get_character_client",
            return_value=mock_character_client,
        ):
            result = await service._ensure_default_character(user_id)

        assert result is False

    @pytest.mark.asyncio
    async def test_grants_character_successfully(
        self, mock_session, mock_character_repo, mock_character_client
    ):
        """기본 캐릭터를 성공적으로 지급합니다."""
        user_id = uuid4()

        default_char = MagicMock()
        default_char.character_id = uuid4()
        default_char.character_code = "ECO_001"
        default_char.character_name = "이코"
        default_char.character_type = "default"
        default_char.character_dialog = "안녕!"
        mock_character_client.get_default_character = AsyncMock(return_value=default_char)

        service = UserCharacterService.__new__(UserCharacterService)
        service.session = mock_session
        service.repo = mock_character_repo

        with patch(
            "domains.my.services.characters.get_character_client",
            return_value=mock_character_client,
        ):
            result = await service._ensure_default_character(user_id)

        assert result is True
        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_handles_integrity_error_gracefully(
        self, mock_session, mock_character_repo, mock_character_client
    ):
        """IntegrityError 발생 시 True를 반환합니다 (이미 소유)."""
        from sqlalchemy.exc import IntegrityError

        user_id = uuid4()

        default_char = MagicMock()
        default_char.character_id = uuid4()
        default_char.character_code = "ECO_001"
        default_char.character_name = "이코"
        default_char.character_type = "default"
        default_char.character_dialog = "안녕!"
        mock_character_client.get_default_character = AsyncMock(return_value=default_char)

        # IntegrityError 발생
        mock_session.commit = AsyncMock(side_effect=IntegrityError("", {}, Exception()))

        service = UserCharacterService.__new__(UserCharacterService)
        service.session = mock_session
        service.repo = mock_character_repo

        with patch(
            "domains.my.services.characters.get_character_client",
            return_value=mock_character_client,
        ):
            result = await service._ensure_default_character(user_id)

        assert result is True
        mock_session.rollback.assert_called_once()


class TestOwnsCharacter:
    """Tests for owns_character method."""

    @pytest.mark.asyncio
    async def test_returns_true_when_owned(self, mock_session, mock_character_repo):
        """캐릭터를 소유하고 있으면 True를 반환합니다."""
        user_id = uuid4()
        mock_character_repo.owns_character_by_name = AsyncMock(return_value=True)

        service = UserCharacterService.__new__(UserCharacterService)
        service.session = mock_session
        service.repo = mock_character_repo

        result = await service.owns_character(user_id, "이코")

        assert result is True
        mock_character_repo.owns_character_by_name.assert_called_once_with(user_id, "이코")

    @pytest.mark.asyncio
    async def test_returns_false_when_not_owned(self, mock_session, mock_character_repo):
        """캐릭터를 소유하지 않으면 False를 반환합니다."""
        user_id = uuid4()
        mock_character_repo.owns_character_by_name = AsyncMock(return_value=False)

        service = UserCharacterService.__new__(UserCharacterService)
        service.session = mock_session
        service.repo = mock_character_repo

        result = await service.owns_character(user_id, "이코")

        assert result is False

    @pytest.mark.asyncio
    async def test_raises_error_for_empty_name(self, mock_session, mock_character_repo):
        """빈 캐릭터 이름은 에러를 발생시킵니다."""
        from fastapi import HTTPException

        user_id = uuid4()

        service = UserCharacterService.__new__(UserCharacterService)
        service.session = mock_session
        service.repo = mock_character_repo

        with pytest.raises(HTTPException) as exc_info:
            await service.owns_character(user_id, "   ")

        assert exc_info.value.status_code == 422
