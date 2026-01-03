"""GetCatalogQuery 단위 테스트."""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from apps.character.application.catalog.queries.get_catalog import GetCatalogQuery
from apps.character.domain.entities import Character

pytestmark = pytest.mark.asyncio


@pytest.fixture
def mock_reader() -> AsyncMock:
    """CatalogReader mock."""
    reader = AsyncMock()
    reader.list_all = AsyncMock()
    return reader


@pytest.fixture
def sample_characters() -> list[Character]:
    """테스트용 캐릭터 목록."""
    return [
        Character(
            id=uuid4(),
            code="char-eco",
            name="이코",
            type_label="기본",
            dialog="안녕! 나는 이코야!",
            match_label=None,
            description="기본 캐릭터",
        ),
        Character(
            id=uuid4(),
            code="char-pet",
            name="페트",
            type_label="재활용",
            dialog="안녕! 나는 페트야!",
            match_label="무색페트병",
            description="페트병 캐릭터",
        ),
        Character(
            id=uuid4(),
            code="char-can",
            name="캔",
            type_label="재활용",
            dialog="안녕! 나는 캔이야!",
            match_label="알루미늄캔",
            description="캔 캐릭터",
        ),
    ]


class TestGetCatalogQuery:
    """GetCatalogQuery 테스트."""

    async def test_empty_catalog(self, mock_reader: AsyncMock) -> None:
        """빈 카탈로그 반환."""
        mock_reader.list_all.return_value = []

        query = GetCatalogQuery(mock_reader)
        result = await query.execute()

        assert result.total == 0
        assert len(result.items) == 0

    async def test_catalog_with_characters(
        self,
        mock_reader: AsyncMock,
        sample_characters: list[Character],
    ) -> None:
        """캐릭터가 있는 카탈로그 반환."""
        mock_reader.list_all.return_value = sample_characters

        query = GetCatalogQuery(mock_reader)
        result = await query.execute()

        assert result.total == 3
        assert len(result.items) == 3

        # 첫 번째 캐릭터 검증
        eco = result.items[0]
        assert eco.code == "char-eco"
        assert eco.name == "이코"
        assert eco.type_label == "기본"

        # 두 번째 캐릭터 검증
        pet = result.items[1]
        assert pet.code == "char-pet"
        assert pet.name == "페트"
        assert pet.match_label == "무색페트병"

    async def test_dialog_fallback_to_description(
        self,
        mock_reader: AsyncMock,
    ) -> None:
        """dialog가 없으면 description으로 폴백."""
        character = Character(
            id=uuid4(),
            code="char-test",
            name="테스트",
            type_label="테스트",
            dialog=None,  # dialog 없음
            match_label=None,
            description="설명입니다",
        )
        mock_reader.list_all.return_value = [character]

        query = GetCatalogQuery(mock_reader)
        result = await query.execute()

        assert result.items[0].dialog == "설명입니다"

    async def test_dialog_fallback_to_empty_string(
        self,
        mock_reader: AsyncMock,
    ) -> None:
        """dialog와 description 모두 없으면 빈 문자열."""
        character = Character(
            id=uuid4(),
            code="char-test",
            name="테스트",
            type_label="테스트",
            dialog=None,
            match_label=None,
            description=None,
        )
        mock_reader.list_all.return_value = [character]

        query = GetCatalogQuery(mock_reader)
        result = await query.execute()

        assert result.items[0].dialog == ""
