"""Tests for CharacterService business logic.

These tests mock the database layer to test service logic in isolation.
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

# 상수 직접 정의 (테스트 독립성)
DEFAULT_CHARACTER_NAME = "이코"
MATCH_REASON_UNDEFINED = "미정의"
RECYCLABLE_WASTE_CATEGORY = "재활용폐기물"
REWARD_SOURCE_SCAN = "scan-reward"


# Mock database session module before importing CharacterService
@pytest.fixture(autouse=True)
def mock_db_session():
    """Mock database session for all tests."""
    with patch("domains.character.services.character.get_db_session"):
        yield


class TestBuildMatchReason:
    """Tests for _build_match_reason static method."""

    def test_middle_and_minor(self):
        """middle_category와 minor_category가 있을 때."""
        from domains.character.schemas.reward import ClassificationSummary
        from domains.character.services.character import CharacterService

        classification = ClassificationSummary(
            major_category="재활용폐기물",
            middle_category="플라스틱",
            minor_category="페트병",
        )
        result = CharacterService._build_match_reason(classification)
        assert result == "플라스틱>페트병"

    def test_middle_only(self):
        """middle_category만 있을 때."""
        from domains.character.schemas.reward import ClassificationSummary
        from domains.character.services.character import CharacterService

        classification = ClassificationSummary(
            major_category="재활용폐기물",
            middle_category="유리",
            minor_category=None,
        )
        result = CharacterService._build_match_reason(classification)
        assert result == "유리"

    def test_major_only(self):
        """major_category만 유효하고 middle은 공백일 때."""
        from domains.character.schemas.reward import ClassificationSummary
        from domains.character.services.character import CharacterService

        classification = ClassificationSummary(
            major_category="일반폐기물",
            middle_category=" ",  # 공백 문자 (strip 후 빈 문자열)
            minor_category=None,
        )
        result = CharacterService._build_match_reason(classification)
        assert result == "일반폐기물"

    def test_whitespace_categories(self):
        """모든 카테고리가 공백일 때 (min_length=1 제약으로 빈 문자열 불가)."""
        from domains.character.schemas.reward import ClassificationSummary
        from domains.character.services.character import CharacterService

        classification = ClassificationSummary(
            major_category=" ",  # 공백 문자 (strip 후 빈 문자열)
            middle_category=" ",  # 공백 문자
            minor_category=None,
        )
        result = CharacterService._build_match_reason(classification)
        assert result == MATCH_REASON_UNDEFINED


class TestResolveMatchLabel:
    """Tests for _resolve_match_label static method."""

    def test_recyclable_waste_returns_middle(self):
        """재활용폐기물일 때 middle_category 반환."""
        from domains.character.schemas.reward import ClassificationSummary
        from domains.character.services.character import CharacterService

        classification = ClassificationSummary(
            major_category=RECYCLABLE_WASTE_CATEGORY,
            middle_category="플라스틱",
        )
        result = CharacterService._resolve_match_label(classification)
        assert result == "플라스틱"

    def test_recyclable_waste_no_middle(self):
        """재활용폐기물인데 middle_category가 공백일 때."""
        from domains.character.schemas.reward import ClassificationSummary
        from domains.character.services.character import CharacterService

        classification = ClassificationSummary(
            major_category=RECYCLABLE_WASTE_CATEGORY,
            middle_category=" ",  # 공백 문자 (strip 후 빈 문자열)
        )
        result = CharacterService._resolve_match_label(classification)
        assert result is None

    def test_non_recyclable_returns_middle_or_major(self):
        """재활용폐기물이 아닐 때 middle 또는 major 반환."""
        from domains.character.schemas.reward import ClassificationSummary
        from domains.character.services.character import CharacterService

        classification = ClassificationSummary(
            major_category="일반폐기물",
            middle_category="음식물",
        )
        result = CharacterService._resolve_match_label(classification)
        assert result == "음식물"

    def test_non_recyclable_no_middle(self):
        """재활용폐기물이 아니고 middle도 공백일 때."""
        from domains.character.schemas.reward import ClassificationSummary
        from domains.character.services.character import CharacterService

        classification = ClassificationSummary(
            major_category="대형폐기물",
            middle_category=" ",  # 공백 문자 (strip 후 빈 문자열)
        )
        result = CharacterService._resolve_match_label(classification)
        assert result == "대형폐기물"


class TestCatalog:
    """Tests for catalog method."""

    @pytest.fixture
    def mock_session(self):
        return AsyncMock()

    @pytest.fixture
    def service(self, mock_session):
        from domains.character.services.character import CharacterService

        service = CharacterService.__new__(CharacterService)
        service.session = mock_session
        service.character_repo = MagicMock()
        service.ownership_repo = MagicMock()
        return service

    @pytest.mark.asyncio
    async def test_catalog_returns_profiles(self, service):
        """캐릭터 목록이 있을 때 프로필 리스트 반환."""
        mock_character = MagicMock()
        mock_character.name = "이코"
        mock_character.type_label = "기본"
        mock_character.dialog = "안녕!"
        mock_character.description = None
        mock_character.match_label = "플라스틱"

        service.character_repo.list_all = AsyncMock(return_value=[mock_character])

        result = await service.catalog()

        assert len(result) == 1
        assert result[0].name == "이코"
        assert result[0].type == "기본"
        assert result[0].dialog == "안녕!"

    @pytest.mark.asyncio
    async def test_catalog_empty_raises_error(self, service):
        """캐릭터가 없을 때 CatalogEmptyError 발생."""
        from domains.character.exceptions import CatalogEmptyError

        service.character_repo.list_all = AsyncMock(return_value=[])

        with pytest.raises(CatalogEmptyError):
            await service.catalog()


class TestGetDefaultCharacter:
    """Tests for get_default_character method."""

    @pytest.fixture
    def mock_session(self):
        return AsyncMock()

    @pytest.fixture
    def service(self, mock_session):
        from domains.character.services.character import CharacterService

        service = CharacterService.__new__(CharacterService)
        service.session = mock_session
        service.character_repo = MagicMock()
        service.ownership_repo = MagicMock()
        return service

    @pytest.mark.asyncio
    async def test_returns_default_character(self, service):
        """기본 캐릭터 반환."""
        mock_character = MagicMock()
        mock_character.name = DEFAULT_CHARACTER_NAME

        service.character_repo.get_by_name = AsyncMock(return_value=mock_character)

        result = await service.get_default_character()

        assert result == mock_character
        service.character_repo.get_by_name.assert_called_once_with(DEFAULT_CHARACTER_NAME)

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self, service):
        """기본 캐릭터가 없을 때 None 반환."""
        service.character_repo.get_by_name = AsyncMock(return_value=None)

        result = await service.get_default_character()

        assert result is None


class TestEvaluateReward:
    """Tests for evaluate_reward method."""

    @pytest.fixture
    def mock_session(self):
        return AsyncMock()

    @pytest.fixture
    def service(self, mock_session):
        from domains.character.services.character import CharacterService

        service = CharacterService.__new__(CharacterService)
        service.session = mock_session
        service.character_repo = MagicMock()
        service.ownership_repo = MagicMock()
        return service

    @pytest.mark.asyncio
    async def test_skips_when_not_recyclable(self, service):
        """재활용폐기물이 아닐 때 skip."""
        from domains.character.schemas.reward import (
            CharacterRewardRequest,
            CharacterRewardSource,
            ClassificationSummary,
        )

        payload = CharacterRewardRequest(
            source=CharacterRewardSource.SCAN,
            user_id=uuid4(),
            task_id="task-123",
            classification=ClassificationSummary(
                major_category="일반폐기물",
                middle_category="음식물",
            ),
            disposal_rules_present=True,
            insufficiencies_present=False,
        )

        result = await service.evaluate_reward(payload)

        assert result.received is False
        assert result.already_owned is False
        assert result.name is None

    @pytest.mark.asyncio
    async def test_skips_when_insufficiencies_present(self, service):
        """부족한 정보가 있을 때 skip."""
        from domains.character.schemas.reward import (
            CharacterRewardRequest,
            CharacterRewardSource,
            ClassificationSummary,
        )

        payload = CharacterRewardRequest(
            source=CharacterRewardSource.SCAN,
            user_id=uuid4(),
            task_id="task-123",
            classification=ClassificationSummary(
                major_category=RECYCLABLE_WASTE_CATEGORY,
                middle_category="플라스틱",
            ),
            disposal_rules_present=True,
            insufficiencies_present=True,
        )

        result = await service.evaluate_reward(payload)

        assert result.received is False

    @pytest.mark.asyncio
    async def test_skips_when_no_disposal_rules(self, service):
        """분리배출 규칙이 없을 때 skip."""
        from domains.character.schemas.reward import (
            CharacterRewardRequest,
            CharacterRewardSource,
            ClassificationSummary,
        )

        payload = CharacterRewardRequest(
            source=CharacterRewardSource.SCAN,
            user_id=uuid4(),
            task_id="task-123",
            classification=ClassificationSummary(
                major_category=RECYCLABLE_WASTE_CATEGORY,
                middle_category="플라스틱",
            ),
            disposal_rules_present=False,
            insufficiencies_present=False,
        )

        result = await service.evaluate_reward(payload)

        assert result.received is False

    @pytest.mark.asyncio
    async def test_no_match_when_no_characters(self, service):
        """매칭되는 캐릭터가 없을 때."""
        from domains.character.schemas.reward import (
            CharacterRewardRequest,
            CharacterRewardSource,
            ClassificationSummary,
        )

        payload = CharacterRewardRequest(
            source=CharacterRewardSource.SCAN,
            user_id=uuid4(),
            task_id="task-123",
            classification=ClassificationSummary(
                major_category=RECYCLABLE_WASTE_CATEGORY,
                middle_category="플라스틱",
            ),
            disposal_rules_present=True,
            insufficiencies_present=False,
        )

        service.character_repo.list_by_match_label = AsyncMock(return_value=[])

        result = await service.evaluate_reward(payload)

        assert result.received is False
        assert result.name is None

    @pytest.mark.asyncio
    async def test_grants_reward_when_conditions_met(self, service):
        """조건 충족 시 리워드 지급."""
        from domains.character.schemas.reward import (
            CharacterRewardRequest,
            CharacterRewardSource,
            ClassificationSummary,
        )

        user_id = uuid4()
        mock_character = MagicMock()
        mock_character.id = uuid4()
        mock_character.name = "플라봇"
        mock_character.type_label = "플라스틱"
        mock_character.dialog = "플라스틱을 분리해줘서 고마워!"
        mock_character.description = None
        mock_character.match_label = "플라스틱"
        mock_character.code = "PLASTIC001"

        payload = CharacterRewardRequest(
            source=CharacterRewardSource.SCAN,
            user_id=user_id,
            task_id="task-123",
            classification=ClassificationSummary(
                major_category=RECYCLABLE_WASTE_CATEGORY,
                middle_category="플라스틱",
            ),
            disposal_rules_present=True,
            insufficiencies_present=False,
        )

        service.character_repo.list_by_match_label = AsyncMock(return_value=[mock_character])
        service.ownership_repo.get_by_user_and_character = AsyncMock(return_value=None)
        service._grant_and_sync = AsyncMock()

        result = await service.evaluate_reward(payload)

        assert result.received is True
        assert result.name == "플라봇"
        assert result.dialog == "플라스틱을 분리해줘서 고마워!"
        service._grant_and_sync.assert_called_once()

    @pytest.mark.asyncio
    async def test_already_owned_when_exists(self, service):
        """이미 소유한 캐릭터일 때."""
        from domains.character.schemas.reward import (
            CharacterRewardRequest,
            CharacterRewardSource,
            ClassificationSummary,
        )

        user_id = uuid4()
        mock_character = MagicMock()
        mock_character.id = uuid4()
        mock_character.name = "플라봇"
        mock_character.type_label = "플라스틱"
        mock_character.dialog = "플라스틱을 분리해줘서 고마워!"
        mock_character.description = None
        mock_character.match_label = "플라스틱"

        mock_ownership = MagicMock()

        payload = CharacterRewardRequest(
            source=CharacterRewardSource.SCAN,
            user_id=user_id,
            task_id="task-123",
            classification=ClassificationSummary(
                major_category=RECYCLABLE_WASTE_CATEGORY,
                middle_category="플라스틱",
            ),
            disposal_rules_present=True,
            insufficiencies_present=False,
        )

        service.character_repo.list_by_match_label = AsyncMock(return_value=[mock_character])
        service.ownership_repo.get_by_user_and_character = AsyncMock(return_value=mock_ownership)

        result = await service.evaluate_reward(payload)

        assert result.received is False
        assert result.already_owned is True
        assert result.name == "플라봇"


class TestApplyRewardRaceCondition:
    """Tests for race condition handling in _apply_reward."""

    @pytest.fixture
    def mock_session(self):
        return AsyncMock()

    @pytest.fixture
    def service(self, mock_session):
        from domains.character.services.character import CharacterService

        service = CharacterService.__new__(CharacterService)
        service.session = mock_session
        service.character_repo = MagicMock()
        service.ownership_repo = MagicMock()
        return service

    @pytest.mark.asyncio
    async def test_integrity_error_returns_already_owned(self, service):
        """IntegrityError 발생 시 already_owned=True 반환."""
        from sqlalchemy.exc import IntegrityError

        user_id = uuid4()
        mock_character = MagicMock()
        mock_character.id = uuid4()
        mock_character.name = "플라봇"
        mock_character.type_label = "플라스틱"
        mock_character.dialog = "플라스틱!"
        mock_character.description = None
        mock_character.match_label = "플라스틱"

        service.ownership_repo.get_by_user_and_character = AsyncMock(return_value=None)
        service._grant_and_sync = AsyncMock(side_effect=IntegrityError("duplicate", {}, None))

        result = await service._apply_reward(user_id, [mock_character])

        profile, already_owned, failure = result
        assert profile.name == "플라봇"
        assert already_owned is True
        assert failure is None
        service.session.rollback.assert_called_once()


class TestSyncToMyDomain:
    """Tests for _sync_to_my_domain method."""

    @pytest.fixture
    def mock_session(self):
        return AsyncMock()

    @pytest.fixture
    def service(self, mock_session):
        from domains.character.services.character import CharacterService

        service = CharacterService.__new__(CharacterService)
        service.session = mock_session
        service.character_repo = MagicMock()
        service.ownership_repo = MagicMock()
        return service

    @pytest.mark.asyncio
    async def test_sync_success(self, service):
        """gRPC 동기화 성공 시 로그 남김."""
        user_id = uuid4()
        mock_character = MagicMock()
        mock_character.id = uuid4()
        mock_character.name = "이코"
        mock_character.code = "ECO001"
        mock_character.type_label = "기본"
        mock_character.dialog = "안녕!"

        mock_client = AsyncMock()
        mock_client.grant_character = AsyncMock(return_value=(True, False))

        with patch(
            "domains.character.services.character.get_my_client",
            return_value=mock_client,
        ):
            await service._sync_to_my_domain(
                user_id=user_id, character=mock_character, source="test"
            )

        mock_client.grant_character.assert_called_once()

    @pytest.mark.asyncio
    async def test_sync_failure_does_not_raise(self, service):
        """gRPC 동기화 실패해도 예외 발생 안함 (eventual consistency)."""
        user_id = uuid4()
        mock_character = MagicMock()
        mock_character.id = uuid4()
        mock_character.name = "이코"
        mock_character.code = "ECO001"
        mock_character.type_label = "기본"
        mock_character.dialog = "안녕!"

        mock_client = AsyncMock()
        mock_client.grant_character = AsyncMock(side_effect=Exception("gRPC error"))

        with patch(
            "domains.character.services.character.get_my_client",
            return_value=mock_client,
        ):
            # 예외가 발생하지 않아야 함
            await service._sync_to_my_domain(
                user_id=user_id, character=mock_character, source="test"
            )

    @pytest.mark.asyncio
    async def test_sync_returns_false_logged(self, service):
        """gRPC 동기화가 False 반환 시 warning 로그."""
        user_id = uuid4()
        mock_character = MagicMock()
        mock_character.id = uuid4()
        mock_character.name = "이코"
        mock_character.code = "ECO001"
        mock_character.type_label = "기본"
        mock_character.dialog = "안녕!"

        mock_client = AsyncMock()
        mock_client.grant_character = AsyncMock(return_value=(False, False))

        with patch(
            "domains.character.services.character.get_my_client",
            return_value=mock_client,
        ):
            # 예외 없이 완료
            await service._sync_to_my_domain(
                user_id=user_id, character=mock_character, source="test"
            )
