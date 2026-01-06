"""GetCharactersQuery 단위 테스트."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from apps.users.application.character.queries import GetCharactersQuery

pytestmark = pytest.mark.asyncio


@pytest.fixture
def mock_character_gateway() -> AsyncMock:
    """UserCharacterQueryGateway mock."""
    gateway = AsyncMock()
    gateway.list_by_user_id = AsyncMock()
    return gateway


@pytest.fixture
def mock_default_publisher() -> MagicMock:
    """DefaultCharacterPublisher mock."""
    publisher = MagicMock()
    publisher.publish = MagicMock()
    return publisher


@pytest.fixture
def mock_settings() -> MagicMock:
    """Settings mock."""
    settings = MagicMock()
    settings.default_character_id = str(uuid4())
    settings.default_character_code = "char-eco"
    settings.default_character_name = "이코"
    settings.default_character_type = "기본"
    settings.default_character_dialog = "안녕! 나는 이코야!"
    return settings


@pytest.fixture
def sample_characters() -> list:
    """테스트용 캐릭터 목록 (DB 엔티티 mock)."""
    from unittest.mock import MagicMock

    from apps.users.domain.enums import UserCharacterStatus

    char1 = MagicMock()
    char1.id = uuid4()
    char1.character_id = uuid4()
    char1.character_code = "char-eco"
    char1.character_name = "이코"
    char1.character_type = "기본"
    char1.character_dialog = "안녕!"
    char1.source = "default"
    char1.status = UserCharacterStatus.OWNED.value  # "owned"
    char1.acquired_at = datetime.now(timezone.utc)

    char2 = MagicMock()
    char2.id = uuid4()
    char2.character_id = uuid4()
    char2.character_code = "char-pet"
    char2.character_name = "페트"
    char2.character_type = "재활용"
    char2.character_dialog = "나는 페트!"
    char2.source = "scan"
    char2.status = UserCharacterStatus.OWNED.value  # "owned"
    char2.acquired_at = datetime.now(timezone.utc)

    return [char1, char2]


class TestGetCharactersQuery:
    """GetCharactersQuery 테스트."""

    async def test_returns_existing_characters(
        self,
        mock_character_gateway: AsyncMock,
        mock_default_publisher: MagicMock,
        mock_settings: MagicMock,
        sample_characters: list,
    ) -> None:
        """캐릭터가 있으면 해당 목록을 반환."""
        mock_character_gateway.list_by_user_id.return_value = sample_characters

        query = GetCharactersQuery(
            character_gateway=mock_character_gateway,
            default_publisher=mock_default_publisher,
            settings=mock_settings,
        )
        user_id = uuid4()
        result = await query.execute(user_id)

        assert len(result) == 2
        assert result[0].character_name == "이코"
        assert result[1].character_name == "페트"
        mock_character_gateway.list_by_user_id.assert_called_once_with(user_id)
        mock_default_publisher.publish.assert_not_called()

    async def test_returns_default_character_when_empty(
        self,
        mock_character_gateway: AsyncMock,
        mock_default_publisher: MagicMock,
        mock_settings: MagicMock,
    ) -> None:
        """캐릭터가 없으면 기본 캐릭터를 반환하고 이벤트 발행."""
        mock_character_gateway.list_by_user_id.return_value = []

        query = GetCharactersQuery(
            character_gateway=mock_character_gateway,
            default_publisher=mock_default_publisher,
            settings=mock_settings,
        )
        user_id = uuid4()
        result = await query.execute(user_id)

        assert len(result) == 1
        assert result[0].character_code == "char-eco"
        assert result[0].character_name == "이코"
        assert result[0].source == "default-onboard"
        mock_default_publisher.publish.assert_called_once_with(user_id)

    async def test_default_character_without_publisher(
        self,
        mock_character_gateway: AsyncMock,
        mock_settings: MagicMock,
    ) -> None:
        """publisher 없이도 기본 캐릭터 반환 가능."""
        mock_character_gateway.list_by_user_id.return_value = []

        query = GetCharactersQuery(
            character_gateway=mock_character_gateway,
            default_publisher=None,
            settings=mock_settings,
        )
        user_id = uuid4()
        result = await query.execute(user_id)

        assert len(result) == 1
        assert result[0].character_code == "char-eco"

    async def test_default_character_without_settings(
        self,
        mock_character_gateway: AsyncMock,
        mock_default_publisher: MagicMock,
    ) -> None:
        """settings 없이도 하드코딩 폴백으로 기본 캐릭터 반환."""
        mock_character_gateway.list_by_user_id.return_value = []

        query = GetCharactersQuery(
            character_gateway=mock_character_gateway,
            default_publisher=mock_default_publisher,
            settings=None,
        )
        user_id = uuid4()
        result = await query.execute(user_id)

        assert len(result) == 1
        # Fallback 값 확인
        assert result[0].character_code == "char-eco"
        assert result[0].character_name == "이코"
